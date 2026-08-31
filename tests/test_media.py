"""Product imagery: what the catalog points at, and what it admits is missing.

Three properties, and they are the three that were quietly untrue before.

The catalog has always carried a ``uri`` for every asset it holds, and nothing
resolved it: there were no image files anywhere in the repository and no route
that would have served one. The staging page rendered the *role* as a grey pill
where the photograph goes, so a product with its imagery and a product without
looked identical on the last surface anybody sees before a launch.

The route matters as much as the files. Mounted after the SPA catch-all, a
request for a missing image is answered with ``index.html``, which a browser
renders as a broken-image glyph - so "the imaging system never delivered this"
becomes indistinguishable from "this page is malfunctioning", and those need
different people to fix them.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("DB_PATH", "data/test_media.db")

from fastapi.testclient import TestClient  # noqa: E402

from sc import db  # noqa: E402
from sc.readiness import checks as checks_mod  # noqa: E402
from sc.readiness import record as record_mod  # noqa: E402
from sc.state import baseline as baseline_mod  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
MEDIA = ROOT / "data" / "media"


@pytest.fixture(autouse=True)
def fresh():
    db.init_db(drop=True)
    baseline_mod.get.cache_clear()
    yield
    db.close()


@pytest.fixture
def client():
    from sc.main import app

    return TestClient(app)


needs_media = pytest.mark.skipif(
    not MEDIA.is_dir(),
    reason="no imagery on disk; run scripts/generate_data.py")


# ---------------------------------------------------------------------------
# What the catalog points at exists
# ---------------------------------------------------------------------------


@needs_media
def test_every_asset_the_catalog_holds_has_a_file_behind_it():
    """A record pointing at an image nobody can fetch is worse than one holding
    no image, because the page looks complete."""
    base = baseline_mod.get()
    assets = [a for assets in base.media_by_entity.values() for a in assets]
    assert assets, "the catalog holds no media at all"

    missing = [a.id for a in assets
               if not (ROOT / "data" / a.uri.lstrip("/")).is_file()]
    assert not missing, f"{len(missing)} asset(s) point at no file, e.g. {missing[:3]}"


@needs_media
def test_the_deliberate_gaps_have_no_file_either():
    """The seeded absences are absences on disk as well as in the catalog.

    Otherwise a page could quietly render an image for a role the record says
    was never delivered - which would make the finding beside it look wrong.
    """
    base = baseline_mod.get()
    for entity_id, role in (("VAR-02B", "INGREDIENT_PANEL"), ("VAR-06A", "IN_SITU")):
        held = {str(a.role) for a in base.media_by_entity.get(entity_id, [])}
        assert role not in held, f"{entity_id} unexpectedly holds a {role}"
        assert not (MEDIA / f"{entity_id.lower()}-{role.lower()}.svg").is_file()


# ---------------------------------------------------------------------------
# The route
# ---------------------------------------------------------------------------


@needs_media
def test_a_held_image_is_served_as_an_image(client):
    base = baseline_mod.get()
    asset = base.media_by_entity["VAR-01A"][0]

    response = client.get(asset.uri)

    assert response.status_code == 200
    assert "svg" in response.headers["content-type"]


def test_a_missing_image_is_a_404_and_not_the_application_shell(client):
    """The specific failure this route exists to prevent.

    The SPA catch-all answers any unmatched path with index.html. Reached by an
    <img> tag that is HTML, not an image, so the browser draws its broken-image
    glyph - and a reviewer cannot tell a supplier who never sent a photograph
    from a page that is falling over.
    """
    response = client.get("/media/no-such-asset.svg")

    assert response.status_code == 404
    assert "<!doctype html" not in response.text.lower()


# ---------------------------------------------------------------------------
# What the page is told
# ---------------------------------------------------------------------------


def test_the_media_strip_reports_the_gap_the_finding_reports():
    """One table, read twice. A strip that could disagree with the finding
    beside it would be a second opinion about what this product needs."""
    base = baseline_mod.get()
    record = record_mod.build("VAR-02B")
    assert record is not None

    slots = checks_mod.media_status(record, base)
    findings = checks_mod.required_media(record, base)

    missing_slots = {s["role"] for s in slots if s["required"] and not s["held"]}
    flagged = {f.subject for f in findings}
    assert missing_slots == flagged, "the strip and the finding disagree"
    assert "INGREDIENT_PANEL" in flagged


def test_a_missing_slot_names_who_owes_it():
    """"Media incomplete" is not something anybody can act on. "The imaging
    system has not delivered an ingredient panel" is."""
    base = baseline_mod.get()
    record = record_mod.build("VAR-02B")
    slot = next(s for s in checks_mod.media_status(record, base)
                if s["role"] == "INGREDIENT_PANEL")

    assert slot["required"] is True
    assert slot["held"] is False
    assert slot["system"], "a gap that names nobody is a gap nobody will fix"


def test_a_category_that_needs_no_imagery_is_not_reported_as_missing_it():
    """"Has media" and "has the media it needs" are different questions, and a
    strip full of shrugs is a strip nobody reads."""
    base = baseline_mod.get()
    for entity_id in sorted(base.variants):
        record = record_mod.build(entity_id)
        for slot in checks_mod.media_status(record, base):
            if not slot["required"]:
                continue
            # The effective table, not the module fallback: which imagery a
            # category needs comes from the catalog's own profile, and a test
            # grading against the fallback would pass on a pack whose branches
            # the checks had never heard of.
            required = checks_mod.required_media_for(base)
            prefix_matches = any(record.category.startswith(prefix)
                                 for prefix in required)
            assert prefix_matches, (
                f"{entity_id} is {record.category}, which no rule in the "
                f"catalog's required-media table covers, yet {slot['role']} "
                f"is marked required")
