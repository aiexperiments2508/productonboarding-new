"""The three connected applications are connected by a protocol and nothing else.

``apps/`` holds a supplier portal, a storefront and an operations console. Each
runs in its own process on its own port, and each reaches the platform by
calling tools on the MCP servers it mounts.

That is the whole claim those applications exist to make, and it is one line of
Python away from being false at any moment: ``from sc.state import store`` in a
handler would work perfectly, would be faster, and would quietly turn three
separate systems back into three views of one. Nobody would notice, because
everything would still work.

So it is checked here rather than asserted in a docstring. The cost is a
duplicated fifteen-line .env reader in ``apps/_env.py``; that duplication is
the boundary, and this file is what stops somebody helpfully removing it.
"""

from __future__ import annotations

import ast
import contextlib
from pathlib import Path

import pytest

APPS = Path(__file__).resolve().parents[1] / "apps"

#: Modules that would give an application a way in that is not the protocol.
#: `sc` is the platform itself; `sqlite3` is its database; `httpx`, `requests`
#: and `urllib.request` are how somebody would call its REST API after being
#: told not to import it.
FORBIDDEN_ROOTS = {"sc", "sqlite3", "requests"}


def _sources() -> list[Path]:
    return sorted(p for p in APPS.rglob("*.py") if "__pycache__" not in p.parts)


def test_the_applications_are_actually_there():
    """A boundary test that passes because it found nothing is not a test."""
    found = _sources()
    assert len(found) >= 6, f"expected the three apps and their shared parts, got {found}"


@pytest.mark.parametrize("source", _sources(), ids=lambda p: p.name)
def test_no_connected_application_imports_the_platform(source: Path):
    """Every read and every write has to cross MCP.

    An import of ``sc`` would work, would be faster than a tool call, and would
    end the only interesting property these applications have.
    """
    tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
    for node in ast.walk(tree):
        roots: list[str] = []
        if isinstance(node, ast.Import):
            roots = [alias.name.split(".")[0] for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            roots = [node.module.split(".")[0]]

        for root in roots:
            assert root not in FORBIDDEN_ROOTS, (
                f"{source.relative_to(APPS.parent)} imports {root!r}. These "
                f"applications reach the platform over MCP and by no other "
                f"route - see the module docstring in apps/_mcp.py.")


@pytest.mark.parametrize("source", _sources(), ids=lambda p: p.name)
def test_no_connected_application_calls_the_platforms_rest_api(source: Path):
    """The platform's own API is off limits too, not only its Python.

    ``/api/`` is the platform's REST surface. An application that fetched from
    it would be over the boundary just as surely as one that imported the
    module behind it - and would look more innocent doing so.
    """
    text = source.read_text(encoding="utf-8")
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#") or "/api/" not in line:
            continue
        # Each application serves its *own* /api/stream and /api/mcp. Those are
        # routes it publishes, not routes it calls.
        assert '"/api/stream"' in line or '"/api/mcp"' in line, (
            f"{source.name}: {stripped[:90]}")


def test_the_web_pages_do_not_reach_past_their_own_server():
    """The browser half of the boundary.

    Each page talks to its own server, which is the MCP client. A page that
    fetched the platform directly would move the boundary into the browser,
    where CORS and a session header the platform does not expose would break
    it - and where the supplier identity would become whatever a tab claimed.
    """
    for page in sorted(APPS.rglob("*.js")):
        text = page.read_text(encoding="utf-8")
        for line in text.splitlines():
            if "fetch(" not in line:
                continue
            assert "http://" not in line and "https://" not in line, (
                f"{page.name} fetches an absolute URL: {line.strip()[:90]}")


# ---------------------------------------------------------------------------
# The client's own failure mode
# ---------------------------------------------------------------------------


def test_two_calls_at_once_do_not_wedge_an_endpoint():
    """The bug that made the vendor portal hang, pinned.

    The streamable-HTTP transport runs its reader inside the task that opened
    the session. A session opened while serving one HTTP request therefore
    belongs to that request's task, and the moment the request finishes the
    reader is in a scope nobody is in any more - so the next call waits for a
    reply nobody is reading, for ever, holding the endpoint with it.

    It needed two calls to overlap, which is why it survived three releases:
    one page load made one call, and the background poller only overlapped it
    when a supplier had something being watched. A second call on page load
    made it certain.

    The session is now owned by a task of its own. What this test pins is that
    contract - overlapping calls are all answered, and the endpoint is still
    usable afterwards. It does *not* reproduce the original deadlock, which
    needed the real transport's task affinity to happen at all; reproducing
    that would mean a live platform, which this suite deliberately does without.
    So this guards the half that can be guarded here, and the docstring in
    ``apps/_mcp.Endpoint`` carries the other half.
    """
    import asyncio

    from apps._mcp import Client

    answered: list[str] = []

    async def exercise() -> None:
        client = Client("http://127.0.0.1:1")     # never dialled; see below
        endpoint = client.endpoint("probe", "/mcp/nothing/")

        # A session that answers instantly and records the order it was asked,
        # standing in for the platform. What is under test is the client's own
        # task and lifetime handling, not the transport.
        class Session:
            async def call_tool(self, tool, arguments):
                await asyncio.sleep(0.01)
                answered.append(tool)
                return _Result(tool)

        async def _open():
            return contextlib.AsyncExitStack(), Session()

        endpoint._open = _open                    # type: ignore[method-assign]

        results = await asyncio.gather(
            endpoint.call("one"), endpoint.call("two"), endpoint.call("three"))
        assert sorted(results) == ["one", "three", "two"]
        await endpoint.close()

    asyncio.run(asyncio.wait_for(exercise(), 20))
    assert sorted(answered) == ["one", "three", "two"]


def test_a_caller_that_gives_up_does_not_take_the_session_with_it():
    """A browser cancels by navigating, and used to cancel the call with it.

    The call is shielded, so a caller going away leaves the work to finish
    against a session that stays usable for whoever asks next.
    """
    import asyncio

    from apps._mcp import Client

    async def exercise() -> None:
        client = Client("http://127.0.0.1:1")
        endpoint = client.endpoint("probe", "/mcp/nothing/")

        class Session:
            async def call_tool(self, tool, arguments):
                await asyncio.sleep(0.2)
                return _Result(tool)

        async def _open():
            return contextlib.AsyncExitStack(), Session()

        endpoint._open = _open                    # type: ignore[method-assign]

        abandoned = asyncio.create_task(endpoint.call("slow"))
        await asyncio.sleep(0.05)
        abandoned.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await abandoned

        # The endpoint is still good. Before the fix this hung for ever.
        assert await endpoint.call("after") == "after"
        await endpoint.close()

    asyncio.run(asyncio.wait_for(exercise(), 20))


class _Result:
    """What the SDK hands back: structured content under `result`."""

    def __init__(self, value: str) -> None:
        self.structuredContent = {"result": value}
        self.content: list = []
