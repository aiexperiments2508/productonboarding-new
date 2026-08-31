"""What a supplier can send in, and what happens to it.

The estate so far is about what the retailer *reads*. Every system in
``manifest`` is read-only into the catalog, and the docstring in ``server.py``
argues for that at some length: a supplier system that could write to the
retailer's catalog is not a supplier system, it is a compromise waiting to
happen.

That argument survives here intact, because this module does not write to the
catalog either. It appends **events**, and the platform's own ingestion then
judges them under its own rules - the same precedence policy, the same
materiality threshold, the same safety override, the same refusal to guess at a
document's contents. A submission that contradicts a better-attested document
loses, and it loses in exactly the way a taped one would.

Four things are worth reading before changing anything here.

**A specification change is a SPEC_DOC, never a SUPPLIER_FEED.** A feed row is
recorded as a value, valid from the instant the event carries - so a feed
cannot say "effective from the sixteenth", which is the whole point of a late
change. A document version can. It also produces the invariant for free: a
SPEC_DOC records only *which version of which document is in force*, as
RECORDED. The value it asserts becomes a fact only when the graph reads the
document and writes back through ``record_attribute``, stamped INFERRED with a
confidence, and therefore under the fail-closed safety gate. The provenance
taxonomy does the enforcing; there is no permission check to route around.

**A new document id would lose every contest.** ``baseline.precedence`` returns
zero for a document the seed pack does not know, and ingestion refuses to
record below the held precedence. A portal that minted a fresh id per
submission would produce a SOURCE_CONFLICT every single time and never correct
anything. So a submission mints a new *version* of the supplier's existing
document, which is also what a real portal does.

**Identity here is a pair, and it is not authentication.** The system half is
bound by the endpoint the call arrived at and cannot be spoofed by an argument.
The supplier half is an argument, validated against the suppliers the catalog
knows. That gives scoping and attribution and nothing else - this system has no
identity provider, no session and no password anywhere, and the same is already
true and said out loud of the staging preview. What makes it defensible is
architectural rather than cryptographic: the vendor portal is a process with a
server side, and it holds the supplier identity there, so the value never comes
from a browser.

**A supplier is not a system.** ``Product.supplier`` is SUP-01..SUP-18; the
manifest's systems are pipes. Every supplier uses the portal. Ownership is
therefore resolved through the supplier id, never through the endpoint.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import re
import uuid
from datetime import datetime
from pathlib import Path

from sc import db
from sc.contracts import EventType, MediaRole
from sc.tools.planning import idempotent

#: The largest file a tool call will accept, measured on the decoded bytes.
#:
#: Uploads travel as base64 inside a tool argument, which keeps the whole
#: transaction inside one MCP call - the property this surface exists to
#: demonstrate. The cost is real and worth naming: the payload is buffered and
#: JSON-parsed in the process that also serves the UI and runs the graph, at
#: about a third again in size. Two megabytes is generous for a spec sheet or a
#: pack shot and small enough that a mistake is not a memory event. A real
#: deployment would hand out a presigned URL and take a link instead.
MAX_UPLOAD_BYTES = 2 * 1024 * 1024

#: Where submitted files land. Deliberately not ``data/media``: that directory
#: is rewritten wholesale by the seed pack builder, so an upload written there
#: would survive exactly until the next regeneration.
#:
#: It is served, under ``/inbox`` rather than ``/media``. A reviewer deciding
#: whether a replacement pack shot fixes a finding has to be able to look at
#: it. Keeping it on its own path is what stops "a supplier sent us this" and
#: "this is catalog imagery" being the same statement.
INBOX = "inbox"

#: What a submission can be. Kept as strings rather than an enum because they
#: are written to a column and read back by three processes.
SPEC_CHANGE = "SPEC_CHANGE"
DOCUMENT = "DOCUMENT"
IMAGE = "IMAGE"
PRODUCT_DRAFT = "PRODUCT_DRAFT"
DATA_PACK = "DATA_PACK"

_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


# ---------------------------------------------------------------------------
# Scoping
# ---------------------------------------------------------------------------


def _base():
    from sc.state import baseline as baseline_mod

    return baseline_mod.get()


def known_suppliers(base=None) -> set[str]:
    """The suppliers the catalog knows. Derived, because there is no table."""
    base = base or _base()
    return {p.supplier for p in base.products.values()}


def _refuse(reason: str, **detail) -> dict:
    return {"error": reason, "accepted": False, **detail}


def _check_supplier(supplier: str, base) -> dict | None:
    if supplier not in known_suppliers(base):
        return _refuse(f"no supplier {supplier!r} in this catalog")
    return None


def product_of(entity_id: str, base) -> str | None:
    """The product an id names, whether it names a product or a variant."""
    if entity_id in base.products:
        return entity_id
    return base.product_of_variant.get(entity_id)


def _owned(entity_id: str, supplier: str, base) -> dict | None:
    """Refuse an entity this supplier does not own.

    The analogue of the estate's rule that a system will not hand over another
    system's payload. A portal where every supplier can read every other one's
    specifications is one catalog with eighteen front doors.
    """
    product_id = product_of(entity_id, base)
    product = base.products.get(product_id or "")
    if product is None:
        return _refuse(f"no product or variant {entity_id!r}")
    if product.supplier != supplier:
        return _refuse(f"{entity_id} does not belong to {supplier}")
    return None


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------


def list_my_products(supplier: str, system_id: str, q: str = "",
                     limit: int = 50, offset: int = 0) -> dict:
    """The products this supplier owns, with what it last sent about each."""
    base = _base()
    refusal = _check_supplier(supplier, base)
    if refusal:
        return refusal

    needle = (q or "").strip().lower()
    mine = [p for p in base.products.values() if p.supplier == supplier]
    if needle:
        mine = [p for p in mine
                if needle in p.name.lower() or needle in p.id.lower()
                or any(needle in (base.variants[v].sku or "").lower()
                       for v in base.variants_of.get(p.id, []))]
    mine.sort(key=lambda p: p.id)

    page = mine[max(0, offset):max(0, offset) + max(1, limit)]
    sent = _last_sent(supplier)
    return {
        "supplier": supplier,
        "system": system_id,
        "total": len(mine),
        "products": [{
            "product_id": p.id,
            "name": p.name,
            "category": p.category,
            "regulated": p.regulated,
            "variants": [{"variant_id": v, "sku": base.variants[v].sku,
                          "name": base.variants[v].name,
                          "is_base": base.variants[v].is_base}
                         for v in base.variants_of.get(p.id, [])],
            "last_sent": sent.get(p.id),
            "documents": base.docs_by_supplier.get(supplier, []),
        } for p in page],
    }


def _last_sent(supplier: str) -> dict[str, dict]:
    """The newest event this supplier is named in, per product. Both lanes.

    Read from the event log rather than from a column, so it stays true of the
    recording as well as of what the portal has sent since.
    """
    found: dict[str, dict] = {}
    base = _base()
    for row in db.query(
            "SELECT id, ts, payload, lane FROM events"
            " WHERE payload LIKE ? ORDER BY ts DESC LIMIT 400",
            (f'%"{supplier}"%',)):
        payload = db.loads(row["payload"])
        if payload.get("supplier") != supplier:
            continue
        for entity in _entities_in(payload):
            product_id = product_of(entity, base)
            if product_id and product_id not in found:
                found[product_id] = {
                    "event_id": row["id"], "at": row["ts"],
                    "lane": row["lane"],
                    "doc_ref": _doc_ref(payload),
                }
    return found


def _entities_in(payload: dict) -> list[str]:
    out = list(payload.get("entities") or [])
    if payload.get("entity_id"):
        out.append(str(payload["entity_id"]))
    for row in payload.get("rows") or []:
        if isinstance(row, dict) and row.get("entity_id"):
            out.append(str(row["entity_id"]))
    return out


def _doc_ref(payload: dict) -> str:
    doc_id = payload.get("doc_id")
    return f"{doc_id}:{payload.get('doc_version', '')}" if doc_id else ""


def get_product_spec(supplier: str, product_id: str,
                     as_of: str | None = None) -> dict:
    """What is held against this product, and how much of it this supplier said.

    Delegates to the same reads the catalog route uses rather than assembling
    a second account of one product. Two implementations of one read become two
    accounts of the same product the first time either is edited, and a
    supplier arguing about a number they did not send is the worst place for
    that to happen.

    ``mine`` is the column that makes this screen worth opening: it separates
    "what you told us" from "what we currently believe", which are different
    things precisely when somebody is about to complain.
    """
    base = _base()
    refusal = _check_supplier(supplier, base) or _owned(product_id, supplier, base)
    if refusal:
        return refusal

    from sc.tools import network as network_tools

    diff = network_tools.variant_diff(product_id, as_of)
    if diff.get("error"):
        return _refuse(diff["error"])

    mine = set(base.docs_by_supplier.get(supplier, []))
    attributes = []
    for row in diff["attributes"]:
        definition = base.attr_defs.get(row["path"])
        cells = {}
        for variant_id, cell in (row.get("values") or {}).items():
            doc = (cell or {}).get("doc") or ""
            cells[variant_id] = {
                **(cell or {}),
                # Whether the value in force came from a document of this
                # supplier's, as opposed to artwork, the data pool or a notice.
                "mine": doc.split(":")[0] in mine,
            }
        attributes.append({
            "path": row["path"],
            "label": getattr(definition, "label", row["path"]),
            "unit": getattr(definition, "unit", None),
            "dtype": getattr(definition, "dtype", "str"),
            "safety_class": bool(getattr(definition, "safety_class", False)),
            "differs": row["differs"],
            "values": cells,
        })

    return {
        "supplier": supplier,
        "product": diff["product"],
        "variants": diff["variants"],
        "attributes": attributes,
        "documents": sorted(mine),
    }


# ---------------------------------------------------------------------------
# Writes
# ---------------------------------------------------------------------------


def _submission_id() -> str:
    return f"SUB-{uuid.uuid4().hex[:12]}"


def _record_submission(*, submission_id: str, supplier: str, system_id: str,
                       kind: str, event_ids: list[str], entity_ids: list[str],
                       doc_ref: str = "", files: list[dict] | None = None,
                       note: str = "", effective_from: str | None = None,
                       idempotency_key: str | None = None) -> None:
    from sc.replay import tape

    with db.transaction() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO submissions (id, supplier_id, system_id,"
            " kind, submitted_at, wall_at, event_ids, entity_ids, doc_ref,"
            " files, note, effective_from, idempotency_key)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (submission_id, supplier, system_id, kind,
             tape.sim_now().isoformat(), datetime.now().isoformat(),
             db.dumps(event_ids), db.dumps(entity_ids), doc_ref,
             db.dumps(files or []), note, effective_from, idempotency_key))


def _next_version(base, doc_id: str) -> str:
    """The next version of a document, counting what has already been sent.

    Reads the highest version anybody has asserted rather than the seed pack's,
    so a second submission against one document does not re-mint v2.
    """
    held = {str(getattr(base.source_docs.get(doc_id), "version", "") or "v1")}
    for row in db.query("SELECT payload FROM events WHERE payload LIKE ?",
                        (f'%"{doc_id}"%',)):
        payload = db.loads(row["payload"])
        if payload.get("doc_id") == doc_id and payload.get("doc_version"):
            held.add(str(payload["doc_version"]))
    numbers = [int(v[1:]) for v in held if v.startswith("v") and v[1:].isdigit()]
    return f"v{max(numbers or [1]) + 1}"


def _default_doc(base, supplier: str, entity_id: str = "",
                 path: str = "") -> str:
    """The document a submission from this supplier is a new version of.

    Never a fresh identifier. A document the seed pack does not know carries
    precedence zero and loses every contest it enters, so a portal that minted
    one per submission would raise a conflict every time and correct nothing.

    Where the value being corrected is already in force, the document that
    asserted it is the one to revise - a supplier correcting a figure is
    reissuing the sheet that figure came off, not writing an unrelated one. A
    supplier's active document is the fallback for a value nobody has asserted
    yet.
    """
    docs = base.docs_by_supplier.get(supplier) or []
    if entity_id and path:
        cell = _held_cell(base, entity_id, path)
        source = str((cell or {}).get("doc") or "").split(":")[0]
        if source in docs:
            return source

    for doc_id in docs:
        doc = base.source_docs.get(doc_id)
        if doc is not None and doc.status == "ACTIVE":
            return doc_id
    return docs[0] if docs else ""


def _coerce(value: object, dtype: str) -> tuple[object, str | None]:
    """Check a submitted value against the attribute's declared type."""
    try:
        if dtype == "int":
            return int(value), None  # type: ignore[arg-type]
        if dtype == "float":
            return float(value), None  # type: ignore[arg-type]
        if dtype == "bool":
            return bool(value), None
        if dtype == "list[str]":
            if isinstance(value, str):
                return [v.strip() for v in value.split(",") if v.strip()], None
            if isinstance(value, (list, tuple)):
                return [str(v) for v in value], None
            return None, "expected a list"
        return str(value), None
    except (TypeError, ValueError):
        return None, f"expected {dtype}"


def _narrate(base, path: str, old: object, new: object, unit: str,
             effective_from: str, note: str) -> str:
    """A plain-language rendition of the change, for the extraction node.

    A restatement of the structured fields and never invented content. The
    graph reads document bodies, and a document with no body is a document it
    can only record the arrival of - so the portal writes down what the form
    said, in a sentence, and nothing that was not on the form.
    """
    definition = base.attr_defs.get(path)
    label = getattr(definition, "label", path)
    suffix = f" {unit}" if unit else ""
    lines = [
        f"Revised specification: {label} is {new}{suffix}."
        if old is None else
        f"Revised specification: {label} changes from {old}{suffix} to "
        f"{new}{suffix}.",
    ]
    if effective_from:
        lines.append(f"This applies with effect from {effective_from}.")
    if note:
        lines.append(f"Supplier note: {note}")
    return " ".join(lines)


@idempotent("intake.submit_specification_change")
def submit_specification_change(*, supplier: str, system_id: str,
                                entity_id: str, attribute_path: str,
                                new_value: object, unit: str = "",
                                effective_from: str = "", note: str = "",
                                doc_id: str = "") -> dict:
    """Send a corrected specification. Appends one document version.

    Refuses rather than guesses. An unparseable effective date, a value that is
    not the type the attribute declares, a path nobody has defined, an entity
    somebody else owns, or a safety-class change with no explanation are all
    answered with a reason rather than recorded and sorted out later.
    """
    from sc.replay import tape

    base = _base()
    refusal = (_check_supplier(supplier, base)
               or _owned(entity_id, supplier, base))
    if refusal:
        return refusal

    definition = base.attr_defs.get(attribute_path)
    if definition is None:
        return _refuse(f"no attribute {attribute_path!r} is defined")

    value, problem = _coerce(new_value, definition.dtype)
    if problem:
        return _refuse(f"{attribute_path}: {problem}, got {new_value!r}")

    if definition.safety_class and not (note or "").strip():
        return _refuse(
            f"{attribute_path} is a safety-class declaration; a note saying "
            f"what changed and why is required before it can be submitted")

    now = tape.sim_now()
    if effective_from:
        try:
            effective = datetime.fromisoformat(effective_from)
        except ValueError:
            return _refuse(f"cannot read {effective_from!r} as a date")
        if effective.date() < now.date():
            return _refuse(
                f"{effective_from} is in the past; a correction cannot take "
                f"effect before it was sent")

    document = doc_id or _default_doc(base, supplier, entity_id,
                                      attribute_path)
    if not document:
        return _refuse(f"{supplier} has no document to revise")
    version = _next_version(base, document)

    held = (_held_cell(base, entity_id, attribute_path) or {}).get("value")
    submission_id = _submission_id()
    payload = {
        "doc_id": document, "doc_version": version,
        "supplier": supplier, "kind": "PORTAL_FEED",
        "product": product_of(entity_id, base),
        "entities": [entity_id], "applies_to":
            "VARIANT" if entity_id in base.variants else "PRODUCT",
        "attribute_path": attribute_path,
        "old_value": held, "new_value": value, "unit": unit or definition.unit,
        "is_correction": True, "material_hint": True,
        "effective_from": effective_from,
        "changes": [{"path": attribute_path, "value": value,
                     "unit": unit or definition.unit,
                     "entity_id": entity_id}],
        "summary": note, "submission_id": submission_id,
    }

    event = tape.append_live(
        EventType.SPEC_DOC, "VENDOR_PORTAL", payload, system_id=system_id,
        body=_narrate(base, attribute_path, held, value,
                      unit or definition.unit or "", effective_from, note))

    _record_submission(submission_id=submission_id, supplier=supplier,
                       system_id=system_id, kind=SPEC_CHANGE,
                       event_ids=[event.id], entity_ids=[entity_id],
                       doc_ref=f"{document}:{version}", note=note,
                       effective_from=effective_from or None)

    return {
        "accepted": True,
        "submission_id": submission_id,
        "event_id": event.id,
        "seq": event.seq,
        "doc_ref": f"{document}:{version}",
        "recorded_at": event.ts.isoformat(),
        "effective_from": effective_from or event.ts.date().isoformat(),
        "carried_by": system_id,
        "note": ("recorded as a document version. The value it asserts is read "
                 "and judged by the platform's own extraction - this call does "
                 "not write it into the catalog"),
    }


def _held_cell(base, entity_id: str, path: str) -> dict | None:
    """The assertion in force for this attribute, with the document behind it.

    Read through ``variant_diff`` rather than straight from the fact store,
    because the fact store is only half the answer: a value nobody has
    corrected yet lives in the seed pack and has no fact row at all. Asking the
    store directly returns None for every untouched attribute, which would make
    a first correction look like a first assertion - and send it out under the
    wrong document.

    The document is the half that matters here. A supplier correcting a figure
    is reissuing the sheet that figure came off, not writing an unrelated one.
    """
    from sc.tools import network as network_tools

    product_id = product_of(entity_id, base)
    if not product_id:
        return None
    diff = network_tools.variant_diff(product_id)
    if diff.get("error"):
        return None
    for row in diff["attributes"]:
        if row["path"] != path:
            continue
        values = row.get("values") or {}
        return values.get(entity_id) or next(iter(values.values()), None)
    return None


# ---------------------------------------------------------------------------
# Uploads
# ---------------------------------------------------------------------------


def _decode(content_base64: str, *, limit: int = MAX_UPLOAD_BYTES,
            ) -> tuple[bytes | None, str | None]:
    """The attachment's bytes, or the reason they are not usable.

    The limit is a parameter because a bundle is not an attachment: two
    megabytes is the right size for one photograph and the wrong size for a
    spreadsheet with forty of them. One function and one message template, so
    the two doors cannot describe the same refusal differently.
    """
    try:
        raw = base64.b64decode(content_base64 or "", validate=True)
    except (binascii.Error, ValueError):
        return None, "the attachment is not valid base64"
    if not raw:
        return None, "the attachment is empty"
    if len(raw) > limit:
        return None, (f"the attachment is {len(raw)} bytes; this endpoint "
                      f"accepts up to {limit}")
    return raw, None


def _write(supplier: str, subdir: str, filename: str, raw: bytes) -> dict:
    from sc.state import baseline as baseline_mod

    safe = _SAFE_NAME.sub("-", filename or "upload").strip("-") or "upload"
    directory = baseline_mod.data_dir() / INBOX / supplier / subdir
    directory.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(raw).hexdigest()
    path = directory / f"{digest[:10]}-{safe}"
    path.write_bytes(raw)
    # Forward slashes, always. This string is recorded against the submission
    # and is read back by three processes and rendered into a URL - and a
    # Windows separator is neither portable nor a path a browser can follow.
    return {"path": f"{INBOX}/{supplier}/{subdir}/{path.name}",
            "bytes": len(raw), "sha256": digest, "filename": safe}


@idempotent("intake.upload_document")
def upload_document(*, supplier: str, system_id: str, product_id: str,
                    filename: str, content_base64: str, media_type: str = "",
                    text: str = "", doc_id: str = "", note: str = "") -> dict:
    """Send a document. Its contents are read only if you render them.

    There is no PDF parser in this system and there is deliberately not going
    to be one here. With a text rendition the body reaches the extraction node
    and the document can be read; without one this records that the document
    *arrived*, which is a true and useful thing to record, and says so rather
    than implying the contents were understood. Recording an arrival and
    declining to guess at what it says is the same split ingestion already
    makes for every document on the tape.
    """
    from sc.replay import tape

    base = _base()
    refusal = (_check_supplier(supplier, base)
               or _owned(product_id, supplier, base))
    if refusal:
        return refusal

    raw, problem = _decode(content_base64)
    if problem:
        return _refuse(problem)

    document = doc_id or _default_doc(base, supplier)
    if not document:
        return _refuse(f"{supplier} has no document to revise")
    version = _next_version(base, document)
    stored = _write(supplier, "docs", filename, raw)
    submission_id = _submission_id()

    event = tape.append_live(
        EventType.SPEC_DOC, "VENDOR_PORTAL",
        {"doc_id": document, "doc_version": version, "supplier": supplier,
         "kind": "SPEC_SHEET", "product": product_id,
         "entities": [product_id], "applies_to": "PRODUCT",
         "filename": stored["filename"], "media_type": media_type,
         "sha256": stored["sha256"], "bytes": stored["bytes"],
         "summary": note, "submission_id": submission_id},
        system_id=system_id, body=text or None)

    _record_submission(submission_id=submission_id, supplier=supplier,
                       system_id=system_id, kind=DOCUMENT,
                       event_ids=[event.id], entity_ids=[product_id],
                       doc_ref=f"{document}:{version}", files=[stored],
                       note=note)

    return {
        "accepted": True,
        "submission_id": submission_id,
        "event_id": event.id,
        "doc_ref": f"{document}:{version}",
        "stored": stored,
        "extractable": bool(text),
        "reason": None if text else (
            "no text rendition was supplied, so the platform has recorded that "
            "this document arrived and has not guessed at its contents"),
    }


@idempotent("intake.upload_image")
def upload_image(*, supplier: str, system_id: str, entity_id: str, role: str,
                 filename: str, content_base64: str, media_type: str = "",
                 alt_text: str = "") -> dict:
    """Send an image against a variant, in one of the declared roles.

    Roles are a closed set because the requirement is per role: "the category
    needs an ingredient panel and none arrived" is only checkable if roles come
    from a list. Free text would make a missing pack shot indistinguishable
    from one filed under a name nobody checks.
    """
    from sc.replay import tape

    base = _base()
    refusal = (_check_supplier(supplier, base)
               or _owned(entity_id, supplier, base))
    if refusal:
        return refusal

    try:
        media_role = MediaRole(str(role).upper())
    except ValueError:
        return _refuse(f"{role!r} is not an image role; expected one of "
                       f"{', '.join(r.value for r in MediaRole)}")

    raw, problem = _decode(content_base64)
    if problem:
        return _refuse(problem)

    stored = _write(supplier, "media", filename, raw)
    submission_id = _submission_id()
    uri = f"/{INBOX}/{supplier}/media/{Path(stored['path']).name}"

    event = tape.append_live(
        EventType.CATALOG_UPDATE, "VENDOR_PORTAL",
        {"kind": "MEDIA", "supplier": supplier, "entity_id": entity_id,
         "entities": [entity_id],
         "media": {"entity_id": entity_id, "role": str(media_role),
                   "uri": uri, "alt_text": alt_text,
                   "system": system_id, "sha256": stored["sha256"]},
         "submission_id": submission_id},
        system_id=system_id)

    _record_submission(submission_id=submission_id, supplier=supplier,
                       system_id=system_id, kind=IMAGE,
                       event_ids=[event.id], entity_ids=[entity_id],
                       files=[{**stored, "role": str(media_role)}],
                       note=alt_text)

    return {"accepted": True, "submission_id": submission_id,
            "event_id": event.id, "role": str(media_role), "uri": uri,
            "stored": stored}


@idempotent("intake.create_product_draft")
def create_product_draft(*, supplier: str, system_id: str, name: str,
                         category: str, attributes: dict | None = None,
                         note: str = "") -> dict:
    """Propose a product the retailer does not have yet.

    A draft is not a product, and this returns saying so. The catalog is loaded
    from the seed pack and ingestion drops any entity that pack does not name -
    so a draft that claimed to be in the catalog would be a claim the very next
    screen disproves. It is held as a draft until a reviewer accepts it, which
    is a decision with a person's name on it rather than a side effect of
    somebody filling in a form.
    """
    from sc.replay import tape

    base = _base()
    refusal = _check_supplier(supplier, base)
    if refusal:
        return refusal
    if not (name or "").strip():
        return _refuse("a draft needs a name")
    if not (category or "").strip():
        return _refuse("a draft needs a category")

    submission_id = _submission_id()
    draft_id = f"PRD-D{uuid.uuid4().hex[:6].upper()}"
    document = f"DOC-D{uuid.uuid4().hex[:6].upper()}"

    event = tape.append_live(
        EventType.SPEC_DOC, "VENDOR_PORTAL",
        {"doc_id": document, "doc_version": "v1", "supplier": supplier,
         "kind": "PORTAL_FEED", "draft": True, "product": draft_id,
         "entities": [draft_id], "applies_to": "PRODUCT",
         "name": name, "category": category,
         "attributes": dict(attributes or {}),
         "summary": note, "submission_id": submission_id},
        system_id=system_id,
        body=f"New line proposed by {supplier}: {name} ({category}). {note}")

    _record_submission(submission_id=submission_id, supplier=supplier,
                       system_id=system_id, kind=PRODUCT_DRAFT,
                       event_ids=[event.id], entity_ids=[draft_id],
                       doc_ref=f"{document}:v1", note=note)

    return {
        "accepted": True,
        "submission_id": submission_id,
        "draft_id": draft_id,
        "event_id": event.id,
        "in_catalog": False,
        "status": "DRAFT_RECEIVED",
        "note": ("held as a draft. The retailer's catalog does not take a new "
                 "line until a reviewer accepts it, and that decision is "
                 "recorded against the person who makes it"),
    }


# ---------------------------------------------------------------------------
# Bundles
# ---------------------------------------------------------------------------


@idempotent("intake.submit_product_feed")
def submit_product_feed(*, supplier: str, system_id: str, filename: str,
                        content_base64: str, note: str = "") -> dict:
    """Send a whole product feed: one archive of rows and photographs.

    The bulk door. The four tools above each say one thing about one product,
    which is the right shape for a correction and the wrong shape for the
    question a retailer asks first - a supplier has forty new lines, how many
    of them are fit to sell.

    Nothing here is a new kind of authority. Every row becomes an event on the
    live lane and is judged by the platform's own ingestion under the same
    precedence policy, the same materiality threshold and the same safety
    override as a taped one. A row that contradicts a better-attested document
    loses. A SKU this supplier does not own is refused. A row naming a product
    the catalog does not have is held as a draft, exactly as
    ``create_product_draft`` holds one, because the catalog does not take a new
    line without a reviewer.

    **The document matters.** Rows are asserted against a new version of the
    supplier's own existing document, never a freshly minted id - a document
    the seed pack does not know carries precedence zero and loses every contest
    it enters, so a bundle minting its own would raise forty conflicts and
    correct nothing. Same rule, same helper, as the single-attribute form.

    Parsing lives in ``sc.datapack.read``. This function owns who may send
    what, on whose authority, and what is written down; it does not own the
    difference between a comma and a pipe.
    """
    from sc.datapack import read as read_mod
    from sc.estate.manifest import SYSTEMS
    from sc.replay import tape

    base = _base()
    refusal = _check_supplier(supplier, base)
    if refusal:
        return refusal

    raw, why = _decode(content_base64, limit=read_mod.MAX_BUNDLE_BYTES)
    if why:
        return _refuse(why)

    # Imagery is accepted only where the manifest says this system takes it.
    # Derived rather than declared, so narrowing a system removes its ability
    # to carry photographs with no code change here - the same property the
    # tool list has.
    system = next((s for s in SYSTEMS if s.id == system_id), None)
    accepts_images = "CATALOG_UPDATE" in set(getattr(system, "accepts", ()) or ())

    bundle = read_mod.read(raw, supplier=supplier, base=base,
                           accepts_images=accepts_images)
    if not bundle.accepted:
        return _refuse(bundle.refusal, **bundle.detail)
    if not bundle.rows:
        return _refuse("no row in the bundle could be read",
                       rows=bundle.summary())

    submission_id = _submission_id()
    stored = _write(supplier, "packs", filename or "bundle.zip", raw)
    files = [stored]

    document = _default_doc(base, supplier)
    if not document:
        return _refuse(f"{supplier} has no document to revise")
    version = _next_version(base, document)
    doc_ref = f"{document}:{version}"

    prepared, entity_ids, drafts = _bundle_events(
        bundle, supplier=supplier, system_id=system_id,
        submission_id=submission_id, document=document, version=version,
        base=base, note=note, accepts_images=accepts_images, files=files)

    events = tape.append_live_many(prepared, system_id=system_id)

    _record_submission(submission_id=submission_id, supplier=supplier,
                       system_id=system_id, kind=DATA_PACK,
                       event_ids=[e.id for e in events],
                       entity_ids=entity_ids, doc_ref=doc_ref, files=files,
                       note=note)
    _record_bundle_drafts(events, drafts, supplier=supplier,
                          system_id=system_id, batch_id=submission_id)

    images = bundle.image_summary()
    if not accepts_images and any(r.images for r in bundle.rows):
        images["refused"] = (
            f"{system_id} does not accept imagery, so the photographs in this "
            f"bundle were not taken. Its manifest entry declares what it "
            f"accepts, and imagery is not on it")

    return {
        "accepted": True,
        "submission_id": submission_id,
        "batch_id": submission_id,
        "doc_ref": doc_ref,
        "stored": stored,
        "rows": bundle.summary(),
        "images": images,
        "drafts": drafts,
        "entities": entity_ids,
        "events": [e.id for e in events],
        "carried_by": system_id,
        "recorded_at": events[0].ts.isoformat() if events else "",
        "note": ("recorded as supplier feed rows against a new version of "
                 f"{document}. Nothing here writes a value into the catalog by "
                 "itself: the platform's own ingestion judges every row under "
                 "the same precedence policy as the recording, and a row that "
                 "contradicts a better-attested document loses. Rows naming a "
                 "product we do not have are held as drafts until a reviewer "
                 "accepts them"),
    }


def _bundle_events(bundle, *, supplier: str, system_id: str,
                   submission_id: str, document: str, version: str, base,
                   note: str, accepts_images: bool, files: list[dict],
                   ) -> tuple[list[tuple], list[str], list[dict]]:
    """The whole bundle as events, in the order the supplier's file listed them.

    One opener, one event per row, one per photograph, one closer.

    **Every event carries a top-level ``entities``**, and that is load bearing
    rather than tidy: the map's highlight engine reads a fixed allowlist of
    top-level payload keys, so a row whose entity is buried inside its ``rows``
    array arrives correctly, records correctly, and lights nothing. The feed
    would fill and the catalog map would stay dark.

    The opener and closer deliberately carry no ``rows``, so ingestion reads
    them as markers and records nothing from them. They exist to give the feed
    a beginning and an end, and to give the batch an identity to be reported
    against - one line saying a supplier sent forty products is worth two
    events.
    """
    from sc.contracts import EventType

    prepared: list[tuple] = []
    drafts: list[dict] = []
    envelope = {"supplier": supplier, "submission_id": submission_id,
                "batch_id": submission_id, "kind": "PORTAL_FEED"}

    entity_ids = [r.entity_id for r in bundle.rows if r.entity_id]
    counts = bundle.summary()

    prepared.append((
        EventType.SUPPLIER_FEED, "VENDOR_PORTAL",
        {**envelope, "feed_stage": "DATA_PACK_OPENED",
         "filename": bundle.filename, "rows_read": bundle.read,
         "rows_accepted": len(bundle.rows), "entities": entity_ids,
         "doc_id": document, "doc_version": version,
         "summary": note or f"{supplier} sent {len(bundle.rows)} products"},
        f"{supplier} sent a product feed: {bundle.filename}, "
        f"{len(bundle.rows)} rows."))

    for row in bundle.rows:
        if row.draft:
            draft_id = f"PRD-D{uuid.uuid4().hex[:6].upper()}"
            name = row.product_name or row.variant_name or row.sku
            drafts.append({"draft_id": draft_id, "sku": row.sku,
                           "name": name, "category": row.category})
            prepared.append((
                EventType.SPEC_DOC, "VENDOR_PORTAL",
                {**envelope, "feed_stage": "DATA_PACK_DRAFT",
                 "doc_id": f"DOC-D{uuid.uuid4().hex[:6].upper()}",
                 "doc_version": "v1", "draft": True, "product": draft_id,
                 "entities": [draft_id], "applies_to": "PRODUCT",
                 "name": name, "category": row.category, "sku": row.sku,
                 "attributes": dict(row.values),
                 "summary": f"new line proposed: {row.sku}"},
                f"New line proposed by {supplier}: {name} "
                f"({row.category})."))
            continue

        rows = [{"entity_id": row.entity_id, "path": path, "value": value,
                 "unit": getattr(base.attr_defs.get(path), "unit", None)}
                for path, value in sorted(row.values.items())]
        prepared.append((
            EventType.SUPPLIER_FEED, "VENDOR_PORTAL",
            {**envelope, "feed_stage": "DATA_PACK_ROW",
             "doc_id": document, "doc_version": version,
             "product": product_of(row.entity_id, base),
             # Top level, and read by the map. See the docstring.
             "entities": [row.entity_id],
             "entity_id": row.entity_id, "sku": row.sku,
             "attribute_paths": sorted(row.values),
             "rows": rows,
             "summary": f"{row.sku}: {len(rows)} attributes"},
            f"{supplier} sent {len(rows)} attributes for {row.sku}."))

        if not accepts_images:
            continue
        for role, name in sorted(row.images.items()):
            payload = bundle.images.get(name)
            if payload is None:
                continue
            held = _write(supplier, "media", name, payload)
            files.append(held)
            uri = f"/{INBOX}/{supplier}/media/{Path(held['path']).name}"
            prepared.append((
                EventType.CATALOG_UPDATE, "VENDOR_PORTAL",
                {**envelope, "feed_stage": "DATA_PACK_IMAGE",
                 "entities": [row.entity_id], "entity_id": row.entity_id,
                 # The carrier is whichever endpoint accepted the upload. Read
                 # from the caller rather than written down: a system named in
                 # code is a system nobody can add.
                 "media": [{"entity_id": row.entity_id, "role": role,
                            "uri": uri, "alt_text": row.product_name,
                            "system": system_id}],
                 "summary": f"{role.lower()} for {row.sku}"},
                f"{supplier} sent a photograph for {row.sku}."))

    prepared.append((
        EventType.SUPPLIER_FEED, "VENDOR_PORTAL",
        {**envelope, "feed_stage": "DATA_PACK_CLOSED",
         "entities": entity_ids,
         "rows_accepted": len(bundle.rows), "drafts": len(drafts),
         "rejected_rows": counts["rejected_rows"],
         "rejected_cells": counts["rejected_cells"],
         "summary": f"{supplier} finished sending {bundle.filename}"},
        f"{supplier} finished sending {bundle.filename}: "
        f"{len(bundle.rows)} rows accepted, {len(drafts)} held as drafts."))
    return prepared, entity_ids, drafts


def feed_branches() -> dict:
    """The parts of the assortment a template can be asked for.

    Read off the catalog, so a retailer that does not trade a branch does not
    offer a template for it.
    """
    from sc.datapack import formats, schema

    base = _base()
    pack = schema.build(base)
    return {
        "fascia": pack.fascia,
        "formats": formats(),
        "branches": [
            {"id": sheet.branch, "label": sheet.label,
             "regulated": sheet.regulated,
             "categories": len(sheet.leaves),
             "attributes": sum(1 for c in sheet.columns
                               if c.kind == "attribute"),
             "required_media": [c.name.split(".", 1)[1] for c in sheet.columns
                                if c.kind == "image" and c.required]}
            for sheet in pack.sheets
        ],
    }


def fetch_feed_template(*, branch: str, fmt: str = "csv",
                        filled: bool = False) -> dict:
    """The template for one branch, as bytes a supplier can save.

    Handed over base64 through the protocol rather than as a URL, and that is
    the whole reason this tool exists. The vendor portal reaches this platform
    over MCP and by no other route - a page there that linked straight to a
    file on this host would move the boundary into the browser, where the
    supplier identity becomes whatever a tab claims. So the template travels
    the same way an uploaded document travels, in the other direction.

    Generated on demand from the catalog, never read off disk: a template
    cached on a filesystem is a template that keeps saying what the registry
    used to say.
    """
    import base64 as b64

    from sc.datapack import schema
    from sc.datapack.writers import csv_txt, jsonschema, specdoc, workbook

    base = _base()
    pack = schema.build(base)
    sheet = pack.sheet(branch)

    if fmt in ("docx", "json"):
        pass  # whole-pack formats; no branch needed
    elif sheet is None:
        return _refuse(
            f"no part of the assortment called {branch!r}",
            branches=[s.branch for s in pack.sheets])

    example = None
    if filled and sheet is not None:
        from sc.datapack import sample as sample_mod

        example = sample_mod.build(sheet, base)

    stem = f"{branch}-example" if filled else branch
    if fmt == "csv":
        payload = csv_txt.write_csv(sheet, example).encode("utf-8-sig")
        name, media = f"{stem}.csv", "text/csv"
    elif fmt == "txt":
        payload = csv_txt.write_txt(sheet, example).encode("utf-8-sig")
        name, media = f"{stem}.txt", "text/plain"
    elif fmt == "json":
        import json as json_mod

        payload = (json_mod.dumps(jsonschema.write(pack), indent=2)
                   + "\n").encode("utf-8")
        name, media = "supplier-feed.schema.json", "application/schema+json"
    elif fmt == "docx":
        payload = specdoc.write(pack)
        name = "supplier-specification.docx"
        media = ("application/vnd.openxmlformats-officedocument."
                 "wordprocessingml.document")
    elif fmt == "xlsx":
        if not workbook.available():
            return _refuse(
                "this installation cannot produce the workbook: openpyxl is "
                "not installed. The same columns are in the .csv, which is "
                "written with the standard library")
        from sc.datapack import sample as sample_mod

        examples = {s.branch: sample_mod.build(s, base) for s in pack.sheets}
        payload = workbook.write(pack, examples)
        name = "supplier-feed.xlsx"
        media = ("application/vnd.openxmlformats-officedocument."
                 "spreadsheetml.sheet")
    else:
        return _refuse(f"no template format called {fmt!r}",
                       formats=["csv", "txt", "xlsx", "docx", "json"])

    return {
        "accepted": True,
        "filename": name,
        "media_type": media,
        "bytes": len(payload),
        "content_base64": b64.b64encode(payload).decode("ascii"),
        "note": ("generated from the retailer's attribute registry and "
                 "assortment at the moment you asked. Every column is one a "
                 "check reads"),
    }


def _record_bundle_drafts(events, drafts: list[dict], *, supplier: str,
                          system_id: str, batch_id: str) -> None:
    """Give every proposed line its own submission.

    A bundle proposing five new lines is five proposals, not one. Each gets a
    ``PRODUCT_DRAFT`` submission of its own, which is what the reviewer
    surfaces read - so a line arriving inside an archive appears in the drafts
    lane beside one typed into the form, and is accepted through the same
    ``drafts.accept`` with the same decision recorded against the same person.

    Recorded *beside* the batch rather than instead of it. The batch is what
    arrived; the proposals are what somebody has to decide. Folding them
    together would mean either a batch a reviewer can accept in one click - a
    reviewer approving forty lines they have not read - or five proposals with
    no record that they came in together.
    """
    by_draft = {}
    for event in events:
        if event.payload.get("feed_stage") == "DATA_PACK_DRAFT":
            by_draft[event.payload.get("product")] = event

    for draft in drafts:
        event = by_draft.get(draft["draft_id"])
        if event is None:
            continue
        _record_submission(
            submission_id=_submission_id(), supplier=supplier,
            system_id=system_id, kind=PRODUCT_DRAFT,
            event_ids=[event.id], entity_ids=[draft["draft_id"]],
            doc_ref=f"{event.payload.get('doc_id', '')}:v1",
            note=f"proposed in {batch_id}")
