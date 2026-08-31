"""A supplier sends a whole range in one archive.

The bulk door does not relax a single rule the single-attribute door enforces,
and most of this file is that claim tested one rule at a time: a supplier still
cannot assert against another supplier's SKU, a row still becomes an event
rather than a value, and a new line is still held as a draft rather than
appearing in the catalog because somebody filled in a spreadsheet.

Three properties here are load bearing beyond their own subject:

*   **Every row event carries a top-level ``entities``.** The map's highlight
    engine reads a fixed allowlist of top-level payload keys, so a row whose
    entity is buried inside its ``rows`` array arrives correctly, records
    correctly, and lights nothing. The feed would fill and the map would stay
    dark, and no assertion anywhere else would notice.

*   **The document is a new version of the supplier's own.** A freshly minted
    document id carries precedence zero and loses every contest it enters, so a
    bundle that minted one would raise a conflict per row and correct nothing -
    while reporting success.

*   **A bad cell loses the cell, not the row.** The opposite is worse than it
    looks: twelve good values discarded to punish one typo, and a bundle of
    forty reported as a bundle of thirty-nine with no explanation.
"""

from __future__ import annotations

import base64
import io
import os
import zipfile

import pytest

os.environ.setdefault("DB_PATH", "data/test_bundle.db")

from sc import db  # noqa: E402
from sc.datapack import read as read_mod  # noqa: E402
from sc.datapack import sample as sample_mod  # noqa: E402
from sc.datapack import schema  # noqa: E402
from sc.datapack.writers import csv_txt  # noqa: E402
from sc.estate import intake, intake_server, submissions  # noqa: E402
from sc.estate.manifest import SYSTEMS  # noqa: E402
from sc.replay import ingest, tape  # noqa: E402
from sc.state import baseline as baseline_mod  # noqa: E402

PORTAL = "supplier-portal"
PIM = "supplier-pim"
POOL = "gdsn-pool"

SVG = b'<svg xmlns="http://www.w3.org/2000/svg" width="8" height="8"/>'

#: What the flat formats end a line with. Named because a test that writes
#: one has to write the same one the reader expects.
NEWLINE = chr(13) + chr(10)


@pytest.fixture(autouse=True)
def fresh():
    db.init_db(drop=True)
    tape.load_tape(reset=True)
    yield
    db.close()


@pytest.fixture
def base():
    return baseline_mod.get()


@pytest.fixture
def example(base):
    """One branch's worked example, and the supplier it belongs to."""
    pack = schema.build(base)
    sheet = pack.sheet("food")
    return sheet, sample_mod.build(sheet, base)


def _zip(members: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, payload in members.items():
            archive.writestr(name, payload)
    return buffer.getvalue()


def _bundle(sheet, example, *, rows=None, images=True) -> bytes:
    body = example
    if rows is not None:
        body = sample_mod.Example(branch=example.branch,
                                  supplier=example.supplier, rows=rows,
                                  images=example.images)
    members = {f"{sheet.branch}.csv":
               csv_txt.write_csv(sheet, body).encode("utf-8-sig")}
    if images:
        for name in body.images:
            members[f"images/{name}"] = SVG
    return _zip(members)


def _send(sheet, example, *, system_id=PORTAL, supplier=None, **kwargs):
    payload = kwargs.pop("payload", None) or _bundle(sheet, example, **kwargs)
    return intake.submit_product_feed(
        supplier=supplier or example.supplier, system_id=system_id,
        filename=f"{sheet.branch}.zip",
        content_base64=base64.b64encode(payload).decode())


# ---------------------------------------------------------------------------
# The surface is derived from the manifest
# ---------------------------------------------------------------------------


def test_only_a_system_that_takes_rows_and_images_gets_the_bulk_door():
    """A product feed is both, and an endpoint that cannot take both has no
    real-world equivalent of one."""
    by_id = {s.id: s for s in SYSTEMS}
    assert "submit_product_feed" in intake_server.tools_for(by_id[PORTAL])
    assert "submit_product_feed" not in intake_server.tools_for(by_id[PIM])
    assert "submit_product_feed" not in intake_server.tools_for(by_id[POOL])


def test_the_bulk_door_is_declared_mutating():
    assert "submit_product_feed" in intake_server.MUTATING


def test_every_endpoint_can_read_the_template():
    """Knowing what we ask for is not a privilege that depends on how you are
    allowed to send it."""
    for system in intake_server.vendor_facing():
        assert "fetch_feed_template" in intake_server.tools_for(system)


def test_a_template_is_offered_where_a_bundle_is_not_taken(base):
    """Two different questions, and the answer to the second is no on two of
    the three endpoints. A portal that inferred one from the other would offer
    an upload form that answers every knock with a refusal."""
    branches = intake.feed_branches()
    assert branches["branches"], "every retailer that trades something has one"
    by_id = {s.id: s for s in SYSTEMS}
    assert "submit_product_feed" not in intake_server.tools_for(by_id[POOL])
    assert "fetch_feed_template" in intake_server.tools_for(by_id[POOL])


def test_a_template_is_generated_rather_than_read_off_disk(base):
    """A template cached on a filesystem keeps saying what the registry used
    to say."""
    result = intake.fetch_feed_template(branch="food", fmt="csv")
    assert result["accepted"]
    assert result["filename"] == "food.csv"
    assert result["bytes"] > 0
    refused = intake.fetch_feed_template(branch="not-a-branch", fmt="csv")
    assert refused.get("error")


# ---------------------------------------------------------------------------
# A well-formed bundle
# ---------------------------------------------------------------------------


def test_a_bundle_lands_as_events_on_the_live_lane(example):
    sheet, body = example
    result = _send(sheet, body)
    assert result["accepted"], result.get("error")

    events = tape.live_events(200)
    assert len(events) == len(result["events"])
    stages = [e.payload.get("feed_stage") for e in events]
    assert stages.count("DATA_PACK_OPENED") == 1
    assert stages.count("DATA_PACK_CLOSED") == 1
    assert stages.count("DATA_PACK_ROW") >= 1
    # One batch id across the whole submission, so the feed groups without a
    # join and the report has something to scope to.
    assert {e.payload.get("batch_id") for e in events} == {result["batch_id"]}


def test_every_row_event_carries_a_top_level_entities(example):
    """The map contract. See the module docstring - this is the test that
    stops a refactor going dark."""
    sheet, body = example
    _send(sheet, body)
    rows = [e for e in tape.live_events(200)
            if e.payload.get("feed_stage") in ("DATA_PACK_ROW",
                                               "DATA_PACK_IMAGE")]
    assert rows
    for event in rows:
        entities = event.payload.get("entities")
        assert isinstance(entities, list) and entities, event.id
        assert all(isinstance(e, str) for e in entities)


def test_the_opener_and_closer_record_nothing(example):
    """Markers, not assertions. Ingestion already ignores an event with no
    rows, and giving them rows would double-count the batch."""
    sheet, body = example
    _send(sheet, body)
    for event in tape.live_events(200):
        if event.payload.get("feed_stage") in ("DATA_PACK_OPENED",
                                               "DATA_PACK_CLOSED"):
            assert ingest._raw_rows(event.payload) == []


def test_the_rows_become_facts_carried_by_the_portal(example, base):
    sheet, body = example
    result = _send(sheet, body)
    rows = db.query(
        "SELECT entity_id, attr, provenance FROM facts WHERE entity_id IN "
        f"({','.join('?' * len(result['entities']))})", tuple(result["entities"]))
    assert rows
    for row in rows:
        provenance = db.loads(row["provenance"])
        assert provenance["kind"] == "RECORDED"
        assert provenance["system"] == PORTAL


def test_the_document_is_a_new_version_of_the_suppliers_own(example, base):
    """A fresh id carries precedence zero and loses every contest it enters."""
    sheet, body = example
    result = _send(sheet, body)
    document, _, version = result["doc_ref"].partition(":")
    assert document in (base.docs_by_supplier.get(body.supplier) or [])
    assert version != "v1"


def test_one_upload_is_one_arrival_batch(example):
    """It arrived once. Forty-four delivery batches would be a false statement
    about what happened, not merely a noisy one."""
    sheet, body = example
    result = _send(sheet, body)
    batches = {row["batch_id"] for row in db.query(
        "SELECT batch_id FROM arrivals WHERE event_id IN "
        f"({','.join('?' * len(result['events']))})", tuple(result["events"]))}
    assert len(batches) == 1


def test_the_submission_records_the_batch_and_the_archive(example):
    sheet, body = example
    result = _send(sheet, body)
    status = submissions.status(body.supplier, result["submission_id"])
    assert status["kind"] == intake.DATA_PACK
    assert set(status["entities"]) == set(result["entities"])
    assert "received" in status["reached"]
    assert result["stored"]["path"].startswith(f"inbox/{body.supplier}/packs/")


def test_images_land_in_the_inbox_and_never_in_the_catalogs_media(example):
    sheet, body = example
    result = _send(sheet, body)
    assert result["images"]["matched"] > 0
    for event in tape.live_events(200):
        for asset in event.payload.get("media") or []:
            assert asset["uri"].startswith(f"/inbox/{body.supplier}/media/")


# ---------------------------------------------------------------------------
# Refusals, at three different scales
# ---------------------------------------------------------------------------


def test_a_path_that_leaves_the_archive_refuses_the_whole_bundle(example):
    sheet, body = example
    payload = _zip({f"{sheet.branch}.csv": csv_txt.write_csv(sheet, body).encode(),
                    "../escape.svg": SVG})
    result = _send(sheet, body, payload=payload)
    assert not result.get("accepted")
    assert "leaves the archive" in result["error"]


def test_a_declared_bomb_is_refused_without_inflating_it(example):
    """On the directory's own word, before anything is decompressed."""
    sheet, body = example
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(f"{sheet.branch}.csv",
                         csv_txt.write_csv(sheet, body).encode())
        archive.writestr("images/big.svg",
                         b"0" * (read_mod.MAX_BUNDLE_UNCOMPRESSED_BYTES + 1))
    result = _send(sheet, body, payload=buffer.getvalue())
    assert not result.get("accepted")
    assert "uncompressed" in result["error"]


def test_two_data_files_are_named_rather_than_guessed_between(example):
    sheet, body = example
    text = csv_txt.write_csv(sheet, body).encode()
    result = _send(sheet, body, payload=_zip({f"{sheet.branch}.csv": text,
                                              "also.csv": text}))
    assert not result.get("accepted")
    assert "also.csv" in result["error"]


def test_an_archive_with_no_data_file_says_so(example):
    sheet, body = example
    result = _send(sheet, body, payload=_zip({"images/a.svg": SVG}))
    assert not result.get("accepted")
    assert "no data file" in result["error"]


def test_something_that_is_not_a_zip_is_refused_as_such(example):
    sheet, body = example
    result = _send(sheet, body, payload=b"this is a spreadsheet, honestly")
    assert not result.get("accepted")
    assert "not a zip" in result["error"]


def test_another_suppliers_sku_is_rejected_by_row(example, base):
    """The rest of the bundle still lands. One bad row is not a bad bundle."""
    sheet, body = example
    other = next(v for v in base.variants.values()
                 if v.sku and base.products[v.product_id].supplier != body.supplier)
    rows = list(body.rows)
    trespass = dict(rows[0])
    trespass["sku"] = other.sku
    rows.append(trespass)

    result = _send(sheet, body, rows=rows)
    assert result["accepted"]
    reasons = [r["why"] for r in result["rows"]["rejected"]]
    assert any("another supplier" in why for why in reasons)
    assert result["rows"]["accepted"] >= len(body.rows)


def test_a_bad_cell_loses_the_cell_and_not_the_row(example, base):
    sheet, body = example
    rows = [dict(r) for r in body.rows]
    rows[0]["food.net_weight_g"] = "forty grams"
    result = _send(sheet, body, rows=rows)

    assert result["accepted"]
    assert result["rows"]["accepted"] == len(rows)
    assert result["rows"]["rejected_cells"] >= 1
    assert any(r["column"] == "food.net_weight_g"
               for r in result["rows"]["rejected"])


def test_an_unknown_column_is_reported_and_does_not_fail_the_bundle(example):
    """A typo in a header is a supplier about to lose a mandatory declaration.

    Reported loudly and never fatally: refusing two hundred good rows over one
    spare column is how a portal stops being used. The column is added to the
    file itself rather than to the row dicts, because the writer only emits
    columns the sheet declares - which is the point of it.
    """
    sheet, body = example
    lines = csv_txt.write_csv(sheet, body).splitlines()
    # `food.allergen.contains`, singular: the typo that silently drops an
    # allergen declaration if nobody says anything about it.
    header, *body_lines = lines
    doctored = [header + ",food.allergen.contains"]
    doctored += [line + ",nuts" for line in body_lines]
    text = "".join(line + NEWLINE for line in doctored)
    payload = _zip({f"{sheet.branch}.csv": text.encode("utf-8-sig")})

    result = _send(sheet, body, payload=payload)
    assert result["accepted"]
    assert "food.allergen.contains" in result["rows"]["unknown_columns"]
    assert "food.allergens.contains" not in result["rows"]["unknown_columns"]


def test_the_packs_own_echo_columns_are_ignored_rather_than_unknown(example):
    sheet, body = example
    result = _send(sheet, body)
    assert sample_mod.NOTE_COLUMN in result["rows"]["ignored_columns"]
    assert sample_mod.NOTE_COLUMN not in result["rows"]["unknown_columns"]


def test_a_row_with_no_sku_is_refused_by_name(example):
    sheet, body = example
    rows = list(body.rows) + [{**body.rows[0], "sku": ""}]
    result = _send(sheet, body, rows=rows)
    assert any(r["column"] == "sku" for r in result["rows"]["rejected"])


def test_a_sku_we_do_not_have_is_held_as_a_draft(example):
    """The catalog does not take a new line because somebody filled in a
    spreadsheet. Same rule as the single-product form."""
    sheet, body = example
    rows = list(body.rows)
    proposed = dict(rows[0])
    proposed["sku"] = "BRAND-NEW-0001"
    rows.append(proposed)

    result = _send(sheet, body, rows=rows)
    assert any(d["sku"] == "BRAND-NEW-0001" for d in result["drafts"])
    assert "BRAND-NEW-0001" not in str(result["entities"])
    drafts = [e for e in tape.live_events(200)
              if e.payload.get("feed_stage") == "DATA_PACK_DRAFT"]
    assert all(e.payload.get("draft") is True for e in drafts)


def test_a_new_line_with_no_category_is_refused_rather_than_guessed(example):
    sheet, body = example
    rows = list(body.rows)
    rows.append({**rows[0], "sku": "NO-CATEGORY-1", "category": ""})
    result = _send(sheet, body, rows=rows)
    assert any("needs a category" in r["why"]
               for r in result["rows"]["rejected"])


def test_an_unknown_supplier_is_refused_before_anything_is_parsed(example):
    sheet, body = example
    result = _send(sheet, body, supplier="SUP-NOBODY")
    assert not result.get("accepted")
    assert tape.live_events(10) == []


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


def test_the_same_bundle_twice_appends_once(example):
    sheet, body = example
    payload = _bundle(sheet, body)
    encoded = base64.b64encode(payload).decode()
    key = "a-supplier-clicked-twice"

    first = intake.submit_product_feed(
        supplier=body.supplier, system_id=PORTAL, filename="food.zip",
        content_base64=encoded, idempotency_key=key)
    count = len(tape.live_events(300))
    second = intake.submit_product_feed(
        supplier=body.supplier, system_id=PORTAL, filename="food.zip",
        content_base64=encoded, idempotency_key=key)

    assert second.get("idempotent_replay") is True
    assert second["submission_id"] == first["submission_id"]
    assert len(tape.live_events(300)) == count
