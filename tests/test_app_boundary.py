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
