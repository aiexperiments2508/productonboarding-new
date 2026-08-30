"""Single-command launcher.

    python run.py

Replaces docker-compose. Serves the API and the built UI from one uvicorn
process, and takes care of the model gateway either way:

* LITELLM_BASE_URL set - a gateway is already running under its own config.
  Attach to it and start nothing.
* otherwise - start LiteLLM as a child process from litellm/config.yaml, wait
  for it to become ready, and stop it again on Ctrl-C.

There is no container anywhere in this stack: SQLite is a file, the vector
index is a numpy array, and the event plane is a table. The lab needs Python
and nothing else - the frontend ships pre-built in frontend/dist.

Useful flags:
    --no-gateway    assume LiteLLM is already running (or you are offline and
                    working entirely from the LLM response cache)
    --reset         drop and recreate the database, then reload the seed pack
    --port 8000     API port
"""

from __future__ import annotations

import argparse
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent
GATEWAY_CONFIG = ROOT / "litellm" / "config.yaml"
GATEWAY_READY_TIMEOUT = 90.0


def load_env() -> None:
    """Read .env. The loader itself lives in sc.bootstrap, so that every other
    front door - Studio, the MCP server, the scripts - gets the same one."""
    from sc import bootstrap

    if not bootstrap.load_env():
        print("  ! no .env found - copy .env.example to .env and point it at "
              "a model gateway", file=sys.stderr)


def port_in_use(port: int) -> bool:
    import socket

    with socket.socket() as sock:
        sock.settimeout(0.5)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def external_gateway() -> str | None:
    """The address of a gateway that is not ours to start.

    Setting LITELLM_BASE_URL says the proxy is already running under someone
    else's config - a shared instance, or one started by hand with its own
    provider credentials. Starting a second one would leave the app calling
    that address while we nursed an unused child process on our own port, and
    the child would fail anyway because the provider key lives in the other
    gateway's environment rather than ours.
    """
    return os.environ.get("LITELLM_BASE_URL", "").strip().rstrip("/") or None


def _auth_headers() -> dict[str, str]:
    key = os.environ.get("LITELLM_API_KEY", "").strip()
    return {"Authorization": f"Bearer {key}"} if key else {}


def start_gateway(port: int) -> subprocess.Popen | None:
    if not GATEWAY_CONFIG.exists():
        raise SystemExit(f"missing gateway config: {GATEWAY_CONFIG}")

    # Something already listening is almost never our gateway - it is another
    # project's proxy. Attaching to it silently would send our traffic to
    # someone else's model config, so say so and attach deliberately.
    if port_in_use(port):
        print(f"  ! port {port} is already in use - attaching to whatever is "
              f"listening there.", file=sys.stderr)
        print(f"    If that is not our gateway, set LITELLM_PORT to a free "
              f"port in .env.", file=sys.stderr)
        return None

    print(f"  starting LiteLLM gateway on port {port} ...")
    log = ROOT / "gateway.log"
    return subprocess.Popen(
        _gateway_command(port),
        cwd=str(ROOT),
        stdout=log.open("w", encoding="utf-8"),
        stderr=subprocess.STDOUT,
    )


def _gateway_command(port: int) -> list[str]:
    """How to launch the proxy.

    ``python -m litellm`` does not work - the package has no ``__main__``. The
    console script is preferred when the install put one on PATH; otherwise the
    proxy CLI module is invoked directly, which works from any environment
    including one where scripts were not linked.
    """
    args = ["--config", str(GATEWAY_CONFIG), "--port", str(port)]
    script = shutil.which("litellm")
    if script:
        return [script, *args]
    return [sys.executable, "-m", "litellm.proxy.proxy_cli", *args]


def wait_for_gateway(base: str, process: subprocess.Popen | None,
                     timeout: float = GATEWAY_READY_TIMEOUT) -> bool:
    """Poll readiness rather than sleeping a fixed interval.

    Returns False rather than raising: the system is still useful offline when
    every model call the demo makes is already in the response cache.

    Any HTTP answer counts as ready, including a 401. We are asking whether
    something is listening, not whether our key is right - and a gateway that
    refuses an unauthenticated probe is still a gateway.
    """
    url = f"{base.rstrip('/')}/health/readiness"
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        if process is not None and process.poll() is not None:
            print("  ! gateway exited early - continuing from the LLM cache",
                  file=sys.stderr)
            return False
        try:
            httpx.get(url, headers=_auth_headers(), timeout=2.0)
            print("  gateway ready")
            return True
        except Exception:
            pass
        time.sleep(1.0)

    print(f"  ! {base} did not answer in time - continuing from the LLM cache",
          file=sys.stderr)
    return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the recovery engine.")
    parser.add_argument("--port", type=int, default=None, help="API port")
    parser.add_argument("--gateway-port", type=int, default=None)
    parser.add_argument("--no-gateway", action="store_true",
                        help="do not start LiteLLM (already running, or offline)")
    parser.add_argument("--reset", action="store_true",
                        help="drop the database and reload the seed pack")
    parser.add_argument("--reload", action="store_true", help="uvicorn autoreload")
    args = parser.parse_args()

    load_env()
    api_port = args.port or int(os.environ.get("API_PORT", "8000"))
    # Publish the port the server is actually on, not the one .env defaults to.
    # The A2A peers advertise an absolute URL in their Agent Cards and the graph
    # calls itself through it, so a --port override that did not reach the
    # environment would leave every peer advertising an address nothing answers.
    os.environ["API_PORT"] = str(api_port)
    gateway_port = args.gateway_port or int(os.environ.get("LITELLM_PORT", "4010"))

    print("Autonomous Product Intelligence Factory")

    if args.reset:
        from sc import db
        from sc.state import baseline

        print("  resetting database ...")
        db.init_db(drop=True)
        baseline.get.cache_clear()

    gateway: subprocess.Popen | None = None
    external = external_gateway()
    if args.no_gateway:
        print("  skipping gateway (--no-gateway)")
    elif external:
        print(f"  using the LiteLLM gateway at {external}")
        wait_for_gateway(external, None, timeout=15.0)
    else:
        gateway = start_gateway(gateway_port)
        wait_for_gateway(f"http://127.0.0.1:{gateway_port}", gateway)

    try:
        import uvicorn

        # Report the URL the app will actually call, not the port we would have
        # started a gateway on - those differ whenever LITELLM_BASE_URL points
        # at a gateway running elsewhere, and printing the wrong one sends
        # anyone debugging a model error to the wrong place.
        gateway_url = external or (
            f"http://{os.environ.get('LITELLM_HOST', '127.0.0.1')}:{gateway_port}")
        attached = external is not None or args.no_gateway

        print(f"\n  UI and API:  http://127.0.0.1:{api_port}")
        print(f"  gateway:     {gateway_url}"
              f"{'  (attached)' if attached else ''}")
        print("  Ctrl-C to stop\n")
        uvicorn.run("sc.main:app", host=os.environ.get("API_HOST", "127.0.0.1"),
                    port=api_port, reload=args.reload, log_level="info")
    except KeyboardInterrupt:
        pass
    finally:
        if gateway is not None and gateway.poll() is None:
            print("\n  stopping gateway ...")
            if os.name == "nt":
                gateway.send_signal(signal.CTRL_BREAK_EVENT)
            else:
                gateway.terminate()
            try:
                gateway.wait(timeout=10)
            except subprocess.TimeoutExpired:
                gateway.kill()


if __name__ == "__main__":
    main()
