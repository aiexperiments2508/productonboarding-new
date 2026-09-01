"""Fetch and unpack Neo4j Community, without Docker.

    python scripts/get_neo4j.py            # download, unpack, set the password
    python scripts/get_neo4j.py --zip X    # unpack a zip you already have
    python scripts/get_neo4j.py --where    # say where it is and stop

`startup.bat` says the only hard requirement is Python, and this keeps that
true. Neo4j Community is a zip with a batch file in it; on a machine with a JDK
it needs nothing else, and a container runtime is one more thing to install, to
be blocked on at work, and to explain in a README.

It lands in `neo4j/` beside `data/` - generated, git-ignored, and deletable.
`startup.bat` looks there, so unpacking it is the whole of the setup.

**Java is the one prerequisite this cannot supply.** Neo4j 5 needs a JDK 17 or
21; the script checks and says so rather than unpacking two hundred megabytes
that will not start. Two ways out if there is no JDK and no way to install one:

  * Neo4j Aura has a free tier. Set NEO4J_URI to the `neo4j+s://` address it
    gives you and nothing local is needed at all.
  * Or do nothing. The Knowledge Graph tab works with no Neo4j anywhere - the
    same projection is walked in process, and every response says so.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

#: 5.26 is the current LTS. Pinned rather than "latest" for the reason the
#: whole seed pack is pinned: a demo rehearsed on Friday has to behave the same
#: way on Sunday, and a database that silently moved a major version between
#: the two is not a rehearsal.
VERSION = "5.26.0"
URL = f"https://dist.neo4j.org/neo4j-community-{VERSION}-windows.zip"
UNIX_URL = f"https://dist.neo4j.org/neo4j-community-{VERSION}-unix.tar.gz"

HOME = ROOT / "neo4j"

#: What `.env.example` suggests, so the two agree without anybody checking.
DEFAULT_PASSWORD = "knowledge"


def java_version() -> int | None:
    """The major version of the JDK on PATH, or None if there is not one.

    `java -version` prints to stderr, which is worth knowing before spending
    an afternoon wondering why the check never matches anything.
    """
    java = shutil.which("java")
    if java is None:
        return None
    try:
        proc = subprocess.run([java, "-version"], capture_output=True,
                              text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    match = re.search(r'version "(\d+)', proc.stderr + proc.stdout)
    return int(match.group(1)) if match else None


def download(target: Path) -> Path:
    """Fetch the archive, reporting progress. Resumes nothing - it is one file."""
    url = URL if os.name == "nt" else UNIX_URL
    print(f"  Downloading {url}")
    target.parent.mkdir(parents=True, exist_ok=True)
    with urlopen(url) as response, target.open("wb") as out:
        total = int(response.headers.get("Content-Length") or 0)
        seen = 0
        while chunk := response.read(1 << 20):
            out.write(chunk)
            seen += len(chunk)
            if total:
                print(f"\r  {seen / 1e6:6.1f} / {total / 1e6:.1f} MB", end="")
    print()
    return target


def running() -> bool:
    """Is something already listening on Neo4j's bolt port?

    Asked before anything is deleted. It is not proof - the port could be
    somebody else's - but it turns the common case into a sentence instead of
    a filesystem error.
    """
    import socket

    with socket.socket() as probe:
        probe.settimeout(0.4)
        return probe.connect_ex(("127.0.0.1", 7687)) == 0


def clear_home() -> None:
    """Remove an existing install, or refuse - but never do half of it.

    ``shutil.rmtree`` deletes as it walks. On Windows, where a running JVM
    holds its jars open, that means it destroys an arbitrary prefix of the
    tree and *then* raises - and the prefix is alphabetical, so ``bin``,
    ``conf`` and ``data`` go before it reaches the locked file in ``lib``.
    This function has done exactly that to a running database once: the
    install was left unbootable and Neo4j panicked mid-transaction because its
    own Lucene lock file had been deleted underneath it.

    Renaming first makes the failure atomic. Windows will not rename a
    directory that has open files anywhere beneath it, so a running install is
    refused before a single byte is touched. Only once the rename has
    succeeded - which proves nothing holds the tree - is anything deleted.
    """
    if not HOME.exists():
        return

    if running():
        raise SystemExit(
            "  ! Something is already listening on 127.0.0.1:7687.\n"
            "    Stop Neo4j before replacing it - close its window, or:\n"
            "        neo4j\\bin\\neo4j stop")

    condemned = HOME.with_name(".neo4j-old")
    if condemned.exists():
        shutil.rmtree(condemned, ignore_errors=True)
    try:
        HOME.rename(condemned)
    except OSError as exc:
        raise SystemExit(
            f"  ! {HOME} is in use, so it cannot be replaced.\n"
            f"    Nothing was deleted. Stop Neo4j first - close its window,\n"
            f"    or: neo4j\\bin\\neo4j stop\n"
            f"    ({exc})") from exc
    shutil.rmtree(condemned, ignore_errors=True)


def unpack(archive: Path) -> Path:
    """Unpack into `neo4j/`, flattening the version directory the zip carries.

    Flattened on purpose: `NEO4J_HOME` should not have a version number in it,
    or every script that refers to it has to be edited to take an upgrade.
    """
    clear_home()
    staging = HOME.parent / ".neo4j-unpack"
    if staging.exists():
        shutil.rmtree(staging)

    print(f"  Unpacking into {HOME}")
    if archive.suffix == ".zip":
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(staging)
    else:
        import tarfile

        with tarfile.open(archive) as tf:
            tf.extractall(staging)

    inner = [p for p in staging.iterdir() if p.is_dir()]
    if len(inner) != 1:
        raise RuntimeError(f"expected one directory in the archive, got {inner}")
    inner[0].rename(HOME)
    shutil.rmtree(staging, ignore_errors=True)
    return HOME


def set_password(password: str) -> bool:
    """Set the initial password, so nobody has to visit the browser to do it.

    Neo4j refuses every connection until the default `neo4j/neo4j` is changed,
    which on a fresh unpack means the first thing the loader would report is an
    authentication failure that looks like a bug in the loader.
    """
    admin = HOME / "bin" / ("neo4j-admin.bat" if os.name == "nt" else "neo4j-admin")
    if not admin.exists():
        return False
    try:
        proc = subprocess.run(
            [str(admin), "dbms", "set-initial-password", password],
            capture_output=True, text=True, timeout=180, cwd=str(HOME))
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"  ! could not set the initial password: {exc}", file=sys.stderr)
        return False
    if proc.returncode != 0:
        print(f"  ! {proc.stderr.strip()[:300]}", file=sys.stderr)
        return False
    return True


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--zip", type=Path, default=None,
                        help="unpack an archive already on disk")
    parser.add_argument("--password", default=DEFAULT_PASSWORD)
    parser.add_argument("--force", action="store_true",
                        help="replace an install that is already there")
    parser.add_argument("--where", action="store_true",
                        help="report where it is, and whether it is usable")
    args = parser.parse_args()

    if args.where:
        print(f"  NEO4J_HOME would be {HOME}")
        print(f"  present: {(HOME / 'bin').exists()}")
        print(f"  java:    {java_version() or 'not on PATH'}")
        return

    major = java_version()
    if major is None or major < 17:
        print("  Neo4j 5 needs a JDK 17 or 21 and this machine has "
              f"{'none on PATH' if major is None else f'Java {major}'}.",
              file=sys.stderr)
        print(file=sys.stderr)
        print("  Two ways on without one:", file=sys.stderr)
        print("    * Neo4j Aura's free tier - set NEO4J_URI to the",
              file=sys.stderr)
        print("      neo4j+s:// address it gives you; nothing local needed.",
              file=sys.stderr)
        print("    * Or nothing at all. The Knowledge Graph tab works with no",
              file=sys.stderr)
        print("      Neo4j: the same projection is walked in process, and",
              file=sys.stderr)
        print("      every response says which engine answered.", file=sys.stderr)
        raise SystemExit(1)

    if HOME.exists() and not args.force:
        # Re-running setup must not destroy a working install. The commonest
        # reason to run this twice is having forgotten whether it was run
        # once, and the answer to that is a sentence, not a re-download.
        print(f"  Neo4j is already unpacked in {HOME}")
        print(f"  Java {major} will run it.")
        print()
        print("  --force replaces it. Stop Neo4j first: it refuses rather")
        print("  than replacing a running install, and refuses without")
        print("  deleting anything.")
        print()
        print("  Put this in .env:")
        print("      NEO4J_URI=bolt://127.0.0.1:7687")
        print("      NEO4J_USER=neo4j")
        print(f"      NEO4J_PASSWORD={args.password}")
        return

    archive = args.zip
    if archive is None:
        cache = ROOT / ".cache" / f"neo4j-community-{VERSION}.zip"
        archive = cache if cache.exists() else download(cache)
        if archive is cache and cache.exists():
            print(f"  Using the copy already at {cache}")
    if not archive.exists():
        print(f"  ! no such archive: {archive}", file=sys.stderr)
        raise SystemExit(1)

    unpack(archive)
    ok = set_password(args.password)

    print()
    print(f"  Neo4j {VERSION} is in {HOME}")
    print(f"  Java {major} will run it.")
    if ok:
        print(f"  Initial password set to {args.password!r}.")
    else:
        print("  ! The initial password was not set. Until it is, Neo4j",
              file=sys.stderr)
        print("    refuses every connection:", file=sys.stderr)
        print(f"      neo4j\\bin\\neo4j-admin dbms set-initial-password "
              f"{args.password}", file=sys.stderr)
    print()
    print("  Put this in .env:")
    print("      NEO4J_URI=bolt://127.0.0.1:7687")
    print("      NEO4J_USER=neo4j")
    print(f"      NEO4J_PASSWORD={args.password}")
    print()
    print("  Then `startup.bat` starts it alongside everything else, and:")
    print("      pip install -r requirements-graph.txt")
    print("      python scripts/load_graph.py")


if __name__ == "__main__":
    main()
