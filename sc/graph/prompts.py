"""Prompts for the LLM nodes.

Separated from the node logic so they can be read and revised as content.

Every prompt in this file obeys one rule: **the model never produces a number
that matters**. It reads, classifies, argues, rewrites and explains. Attribute
values, blast radii, readiness percentages, channel budgets and publish
verdicts all come from the catalog and the validator, and where a prompt needs
those figures they are supplied in the prompt rather than requested from the
model.

Where a model is asked to explain, it is given the numbers and told to explain
them - not asked what they are.

Every reply shape below is a literal JSON template. ``gateway.complete_json``
sets ``response_format=json_object`` and validates nothing beyond that, so the
template written here plus ``.get()`` defaults at the call site is the entire
contract - which is why each template names its nulls explicitly instead of
leaving a field to be omitted.
"""

from __future__ import annotations

import json

# Any single tool payload spliced into a prompt. Evidence that overruns the
# context window is evidence the model never reads.
MAX_BLOCK = 2400

# A supplier document body. The corpus documents are short; this is a guard
# against a pathological attachment rather than a working limit.
MAX_BODY = 6000

# One piece of prepared copy. Long enough for a description, short enough that
# twelve of them still leave room for the attribute table.
MAX_ASSET = 700


# ---------------------------------------------------------------------------
# Rendering helpers
#
# Tool output reaches these builders as whatever the node had to hand: a dict
# from the catalog tools, a list of pydantic dumps, or an already-rendered
# string. Each helper takes all three, because a prompt builder that raises is
# a run that loses its narrative over a formatting detail.
# ---------------------------------------------------------------------------


def _block(value, limit: int = MAX_BLOCK) -> str:
    """A tool result, as JSON, trimmed to fit."""
    if value in (None, "", [], {}):
        return "(none)"
    text = value if isinstance(value, str) else json.dumps(value, indent=2,
                                                           default=str)
    return text[:limit]


def _as_dict(value) -> dict:
    """Best-effort dict view of a retrieval result, dict or model."""
    if isinstance(value, dict):
        return value
    inner = getattr(value, "chunk", value)
    dump = getattr(inner, "model_dump", None)
    return dump(mode="json") if dump else {"text": str(inner)}


def _one_value(value, unit=None) -> str:
    """One attribute value with its unit attached, or ``?`` for absent."""
    if value is None:
        return "?"
    rendered = (json.dumps(value, default=str)
                if isinstance(value, (list, dict)) else str(value))
    return f"{rendered} {unit}" if unit else rendered


def _move(old, new, unit=None) -> str:
    return f"{_one_value(old, unit)} -> {_one_value(new, unit)}"


def _signal_lines(signals) -> str:
    """Correction signals, one line each: what moved, where, on whose word."""
    if isinstance(signals, str):
        return signals or "(none)"
    if isinstance(signals, dict):
        signals = [signals]
    out = []
    for s in signals or []:
        source = s.get("source") or {}
        origin = " ".join(str(p) for p in (source.get("doc_id", ""),
                                           source.get("version", "")) if p)
        parts = [
            f"- {s.get('id', '')} [{s.get('kind')}]",
            ",".join(s.get("entities") or []) or "(no entity named)",
            ",".join(s.get("attribute_paths") or []),
            _move(s.get("old_value"), s.get("new_value"), s.get("unit"))
            if s.get("new_value") is not None else "",
            f"({origin})" if origin else "",
            f"at {s.get('detected_at', '')}",
        ]
        line = " ".join(p for p in parts if p)
        if s.get("provisional"):
            line += " [provisional]"
        if s.get("resolves_issue"):
            line += " [clears an earlier notice]"
        out.append(f"{line}\n  {s.get('summary', '')}")
    return "\n".join(out) or "(none)"


def _cell(cell, unit) -> str:
    """One variant's value, and the document standing behind it."""
    if not isinstance(cell, dict):
        return str(cell)
    source = " ".join(str(p) for p in (cell.get("doc", ""),
                                       cell.get("version", "")) if p)
    rendered = _one_value(cell.get("value"), unit)
    return f"{rendered} ({source})" if source else rendered


def variant_rows(table) -> str:
    """The variant diff as rows, differences first.

    Rendered rather than dumped because this table *is* the scope argument: the
    thing the decision turns on is one attribute where two variants disagree
    and which document each value is standing on, and that reads as a row.
    """
    if not isinstance(table, dict) or "attributes" not in table:
        return _block(table)

    product = table.get("product") or {}
    variants = table.get("variants")
    if isinstance(variants, dict):
        heads = [f"{v} ({role})" for v, role in variants.items()]
    else:
        heads = [f"{v.get('id')} ({'base' if v.get('is_base') else 'variant'})"
                 for v in variants or []]

    rows = []
    for row in table.get("attributes", []):
        unit = row.get("unit")
        values = " | ".join(f"{v}: {_cell(cell, unit)}"
                            for v, cell in (row.get("values") or {}).items())
        marks = "".join(m for m in (" [differs]" if row.get("differs") else "",
                                    " [safety]" if row.get("safety_class") else ""))
        rows.append(f"  {row.get('path')}{marks}: {values}")
    # Differences first: a row every variant agrees on is the half that can
    # afford to be lost to the prompt budget.
    rows.sort(key=lambda r: "[differs]" not in r)

    return (f"{product.get('id', '')} {product.get('name', '')}"
            f" (regulated: {bool(product.get('regulated'))})\n"
            f"  variants: {', '.join(heads)}\n" + "\n".join(rows))


def attribute_rows(values) -> str:
    """Corrected attribute values, one per line, with units attached.

    Rendered rather than dumped for the same reason: the rewrite rule is "take
    the numbers from here and from nowhere else", and a number the writer has
    to dig out of a nested payload is a number it will paraphrase.
    """
    if isinstance(values, str):
        return values or "(none)"
    if isinstance(values, dict):
        rows = [_attr_row(str(path), cell) for path, cell in values.items()]
    else:
        rows = [_attr_row(_ref(row), row) for row in values or []]
    return "\n".join(rows) or "(none)"


def _ref(row: dict) -> str:
    path = row.get("attribute_path") or row.get("path") or ""
    entity = row.get("entity_id") or ""
    return f"{entity}:{path}" if entity else path


def _attr_row(path: str, cell) -> str:
    if not isinstance(cell, dict):
        return f"- {path} = {_one_value(cell)}"
    source = " ".join(str(p) for p in (
        cell.get("doc") or cell.get("source_doc") or "",
        cell.get("version") or cell.get("source_version") or "") if p)
    row = f"- {path} = {_one_value(cell.get('value'), cell.get('unit'))}"
    return f"{row}  [{source}]" if source else row


def asset_lines(assets) -> str:
    """Prepared copy, with the lineage that makes it affected."""
    if isinstance(assets, str):
        return assets or "(none)"
    out = []
    for a in assets or []:
        where = " ".join(str(p) for p in (a.get("listing_id") or a.get("listing", ""),
                                          a.get("channel_id", "")) if p)
        header = f"[{a.get('id')}] {a.get('field', '')}"
        if where:
            header += f" on {where}"
        claims = ",".join(a.get("claims_used") or [])
        stale = ",".join(a.get("stale_refs") or a.get("derived_from") or [])
        if claims:
            header += f"  claims_used: {claims}"
        if stale:
            header += f"  built on: {stale}"
        out.append(f"{header}\n  {str(a.get('text', ''))[:MAX_ASSET]}")
    return "\n\n".join(out) or "(none)"


def claim_table(claim_rules) -> str:
    """The substantiation rules, as the scanner sees them.

    Takes the engine's own ``CLAIM_RULES`` table directly, so the prompt and
    the deterministic check cannot describe different rules.
    """
    if isinstance(claim_rules, str):
        return claim_rules or "(none)"
    items = (claim_rules.items() if isinstance(claim_rules, dict)
             else [(r.get("claim", ""), r) for r in claim_rules or []])
    lines = []
    for claim, rule in items:
        statement = (rule if isinstance(rule, str)
                     else rule.get("statement", "") if isinstance(rule, dict)
                     else getattr(rule, "statement", ""))
        lines.append(f"- {claim}: holds only if {statement}")
    return "\n".join(lines) or "(none)"


def chunk_lines(chunks) -> str:
    """Retrieval chunks with their ids attached.

    The id is not decoration: a fill is only accepted when it names the chunk
    the value came from, so the id has to sit next to the text it labels.
    """
    if isinstance(chunks, str):
        return chunks or "(none)"
    out = []
    for c in chunks or []:
        row = _as_dict(c)
        head = " | ".join(str(p) for p in (
            row.get("chunk_id") or row.get("id") or "",
            row.get("doc_id", ""),
            row.get("heading") or row.get("title") or "") if p)
        text = row.get("excerpt") or row.get("text") or ""
        out.append(f"[{head}]\n{str(text)[:900]}")
    return "\n\n".join(out) or "(none)"


def citation_lines(citations) -> str:
    """Citations as the writer sees them: followable, one per line."""
    if isinstance(citations, str):
        return citations or "(none)"
    return "\n".join(
        f"- {c.get('doc_id', '')} ({c.get('title', '')}): {c.get('heading', '')}"
        for c in (citations or [])[:10]) or "(none)"


def change_table(lines) -> str:
    """The reviewer's diff: source -> old value -> new value -> impacted outputs.

    Assembled from the catalog before the writer sees it, so the narrative
    restates this sentence rather than deriving it.
    """
    if isinstance(lines, str):
        return lines or "(none)"
    out = []
    for row in lines or []:
        source = row.get("source") or {}
        origin = " ".join(str(p) for p in (source.get("doc_id", ""),
                                           source.get("version", "")) if p)
        unit = row.get("unit")
        line = (f"- {origin or '(no source)'} -> "
                f"{row.get('entity_id', '')}:{row.get('attribute_path', '')} "
                f"{_move(row.get('old_value'), row.get('new_value'), unit)} -> "
                f"{len(row.get('impacted_assets') or [])} assets on "
                f"{', '.join(row.get('impacted_channels') or []) or 'no channel'}")
        if row.get("safety"):
            line += "  [safety-class]"
        excerpt = str(source.get("excerpt", ""))[:160]
        out.append(f"{line}\n  \"{excerpt}\"" if excerpt else line)
    return "\n".join(out) or "(none)"


# ---------------------------------------------------------------------------
# extract: a supplier document -> the correction it asserts
# ---------------------------------------------------------------------------

EXTRACT_SYSTEM = """\
You read supplier specification documents and correspondence, and extract the
correction they assert.

Content has already been prepared and published from an earlier version of this
document. Your job is to say precisely what this version changes, in terms the
catalog can act on. Most documents change nothing.

Rules:
- Extract only what the document states. Never infer a value, a unit, an
  effective date or an entity that is not written down.
- Map, do not invent. The known attribute paths and entity ids are listed
  below. If what the document describes has no path in that list, set
  attribute_path to null and let the quote carry what it said - a path you
  make up is a change the catalog cannot apply.
- A CORRECTION revises a value that was previously asserted: 65 W where the
  earlier version said 45 W. Set is_correction true, and fill old_value when
  the document names the figure it supersedes.
- A RESOLUTION clears an earlier notice without revising anything: "review
  complete, dimensions unchanged, disregard the earlier notice". Set
  resolves_issue true and is_correction false. These are different acts and the
  system treats them differently - a correction supersedes a value and stays
  open, a resolution retires an issue and changes nothing. A correction that
  merely revises a number is never a resolution, however much better the new
  number is.
- applies_to: "BASE" when the document names the base model, "VARIANT" when it
  names a particular variant, "UNCLEAR" when it names the product and leaves
  the variant open. UNCLEAR is the honest answer and the useful one. A document
  saying "the Northaven AP300 is rated at 65 W" for a product that ships in two
  models has not told you which one, and guessing puts a wrong number on a real
  page. Report the ambiguity; something downstream resolves it against the
  catalog.
- provisional: "pending review", "we expect to confirm", "subject to a tooling
  audit". A provisional notice is not a confirmed value. Say so here and reflect
  it in confidence.
- material: does this change something that has been, or is about to be,
  published? A feed confirming an unchanged value, portal maintenance, a
  newsletter or a quarterly scorecard is not material.
- quote is the one sentence you read the value out of, copied verbatim. It
  becomes the citation carried by every change this correction produces, so a
  paraphrase there is a broken audit trail.

Choosing kind, most consequential first. Where a document does two things at
once, pick the one carrying the most consequence: an order not to sell outranks
any change to a value, and allergens outrank everything a supplier can say.

- REGULATORY_ORDER: an authority has ordered the product withdrawn, suspended
  or delisted. The values in the record may be perfectly correct; what has
  changed is that it may not be sold.
- SAFETY_RECALL: stock already with customers has to be returned.
- EXPORT_RESTRICTION: a destination or dual-use restriction. Lawful here,
  restricted elsewhere.
- ALLERGEN_CHANGE: anything touching declared or possible allergens.
- INGREDIENT_CHANGE: the ingredient declaration or its order.
- COMPOSITION_CHANGE: the same act outside food - a fibre label, a cosmetic
  INCI list, an active ingredient, a material or coating.
- NET_QUANTITY_CHANGE: the pack got bigger or smaller.
- ORIGIN_CHANGE: where it was made.
- CERTIFICATION_LAPSE: a certificate, test report or conformity declaration
  has expired or been withdrawn. The product is unchanged; the evidence
  behind a claim is gone.
- LEGAL_REQUIREMENT_CHANGE: the rule moved, not the record. Copy that was
  compliant when written no longer is, and no supplier did anything wrong.
- SPEC_CORRECTION: a revised specification value.
- DOC_WITHDRAWN: a document or an earlier notice is withdrawn.
- SOURCE_CONFLICT: this document contradicts another current source without
  superseding it.
- CHANNEL_REJECTION: a channel has refused content.
- DATA_GAP: a required value is stated to be missing or still coming.

Reply with JSON only:
{
  "material": true|false,
  "kind": "REGULATORY_ORDER"|"SAFETY_RECALL"|"EXPORT_RESTRICTION"|"ALLERGEN_CHANGE"|"INGREDIENT_CHANGE"|"COMPOSITION_CHANGE"|"NET_QUANTITY_CHANGE"|"ORIGIN_CHANGE"|"CERTIFICATION_LAPSE"|"LEGAL_REQUIREMENT_CHANGE"|"SPEC_CORRECTION"|"SOURCE_CONFLICT"|"CHANNEL_REJECTION"|"DOC_WITHDRAWN"|"DATA_GAP"|null,
  "entity_guess": "the variant or product id the document names, or null",
  "product_guess": "the product id, or null",
  "attribute_path": "one of the known paths above, or null",
  "old_value": the superseded value, or null,
  "new_value": the corrected value, or null,
  "unit": "the unit as written, or null",
  "effective": "YYYY-MM-DD, or null",
  "applies_to": "BASE"|"VARIANT"|"UNCLEAR",
  "is_correction": true|false,
  "resolves_issue": true|false,
  "provisional": true|false,
  "confidence": 0.0-1.0,
  "quote": "the sentence the value was read from, verbatim"
}"""


def extract_user(doc_id: str, version: str, kind: str, sender: str,
                 subject: str, body: str, received: str,
                 catalog_hint) -> str:
    """One document, and the catalog it has to be mapped onto."""
    return (
        f"DOCUMENT: {doc_id} version {version} ({kind})\n"
        f"Received: {received}\nFrom: {sender}\nSubject: {subject}\n\n"
        f"{str(body)[:MAX_BODY]}\n\n"
        "KNOWN CATALOG - attribute paths and entity ids. Map onto these; "
        "anything not here does not exist:\n"
        f"{_block(catalog_hint)}"
    )


# ---------------------------------------------------------------------------
# triage
# ---------------------------------------------------------------------------

TRIAGE_SYSTEM = """\
You classify the severity of a product content correction against a governance
policy.

The policy text is supplied. Apply it; do not invent thresholds.

You are given the measured blast radius, counted from the catalog: the fields,
assets, listings and channels this correction touches. Those figures are facts.
Use them; do not estimate your own.

Two rules decide most cases:
- Corrections landing on the same product line inside one review window are ONE
  case, classified on their COMBINED reach. A wattage correction and an
  allergen correction that republish the same listings are not two small events.
- Reach is counted in published surfaces, not in fields. One attribute feeding a
  printed catalogue inside its freeze window is a larger event than five feeding
  a web page that can be corrected in a minute.

Safety is not yours to weigh. Any correction touching a safety-class attribute -
allergens above all - is escalated by the caller after you answer,
deterministically and whatever you said. Classify the rest on the policy, and do
not try to anticipate that gate in either direction: arguing safety up wastes
the judgement, arguing it down does not work.

Material means the correction changes something published or about to be. A
routine feed confirming an unchanged value is not material.

Reply with JSON only:
{
  "severity": "LOW"|"MEDIUM"|"HIGH"|"CRITICAL",
  "material": true|false,
  "reason": "two sentences citing the policy rule applied",
  "combined": true|false
}"""


def triage_user(signals: list[dict], blast: dict, policy: str) -> str:
    return (
        f"POLICY EXTRACT:\n{policy}\n\n"
        f"CORRECTIONS DETECTED ({len(signals or [])}):\n"
        f"{_signal_lines(signals)}\n\n"
        "MEASURED BLAST RADIUS (counted from the catalog, authoritative):\n"
        f"{_block(blast)}"
    )


# ---------------------------------------------------------------------------
# resolve_scope: the bounded exception step
# ---------------------------------------------------------------------------

SCOPE_SYSTEM = """\
You decide which variants a supplier correction applies to.

This is the one judgement in this system that no rule settles. A document
reading "the Northaven AP300 is rated at 65 W" names a product that ships in two
models, and the catalog holds a separate value for each. Resolving it wrongly
republishes a corrected number on a page it does not belong on, which is worse
than publishing nothing at all.

What is authoritative, and what is not:
- The VARIANT ATTRIBUTE TABLE is the current catalog. Every value in it carries
  the document and version standing behind it. It is a fact.
- A retrieved postmortem, standard or policy extract is a document. It records
  what someone wrote when they wrote it, and the catalog has moved underneath it
  since. If the table shows the base variant independently certified at a
  different value by its own document, that is evidence about scope. A document
  asserting otherwise is a document, not a fact, and does not overturn the table.
- Source precedence (POL-002) settles which of two disagreeing documents wins.
  It does not settle which variant a document is about.

You propose readings. You do not choose between them. Every candidate is
validated deterministically and ranked by the engine, and precision is measured
in fields actually touched rather than in the confidence you claim - so state
confidence honestly rather than tactically. A narrow candidate you are unsure of
costs one validation; a wide one you were sure of costs a republish.

Levels: BASE (the base variant only), VARIANT (the named variants only), ALL
(every variant of the product). Name the variant ids in "entities" at every
level, including ALL.

Before concluding, answer each of these from what you were given, or ASK:
  1. Does the document name a variant, or only the product? If only the
     product, does anything in the table distinguish the variants on this
     attribute?
  2. Which document version is the value in force standing on, and was the
     prepared content built against an earlier one?
  3. Was any variant independently certified at a different value, by a
     different document, and when?
  4. For a safety-class attribute: which channel rules bind on it?

Ask only what you will use. Three questions you act on beats seven you recite -
an investigation that queries everything has investigated nothing. When every
question above is answered, return "requests": [] and "done": true.

EVIDENCE DESK - the only tools you may use:
{tool_catalogue}

Reply with JSON only:
{
  "candidates": [
    {"level": "BASE"|"VARIANT"|"ALL",
     "entities": ["the variant ids in scope", ...],
     "confidence": 0.0-1.0,
     "rationale": "one or two sentences naming what in the table supports it",
     "evidence": ["document, version or field references", ...]}
  ],
  "requests": [
    {"tool": "a name from the list above", "argument": "...",
     "why": "the specific question this answers"}
  ],
  "done": true|false
}"""


def scope_system(tool_catalogue: str) -> str:
    """The scope brief, with the evidence desk spliced in.

    The catalogue is injected rather than written out here so the prompt cannot
    drift from the allowlist: add a tool to ``evidence.TOOLS`` and the resolver
    is told about it; remove one and it stops being offered.
    """
    return SCOPE_SYSTEM.replace("{tool_catalogue}", tool_catalogue)


def scope_user(signal, variant_table, source_versions, retrieved, priors,
               gathered: str = "", final_pass: bool = False) -> str:
    return (
        f"CORRECTION:\n{_signal_lines(signal)}\n\n"
        "VARIANT ATTRIBUTE TABLE (the current catalog - authoritative):\n"
        f"{variant_rows(variant_table)}\n\n"
        "SOURCE VERSIONS (which version is in force, and what outranks it):\n"
        f"{_block(source_versions)}\n\n"
        f"STANDARDS AND CHANNEL POLICY:\n{_block(retrieved)}\n\n"
        f"PRIOR INCIDENTS (documents, not facts):\n{_block(priors)}"
        + (f"\n\nEVIDENCE YOU ALREADY REQUESTED:\n{gathered}" if gathered else "")
        + ("\n\nThis is your final pass. Conclude now, with "
           '"requests": [] and "done": true.' if final_pass else "")
    )


# ---------------------------------------------------------------------------
# scan_claims: the advisory semantic pass
# ---------------------------------------------------------------------------

SCAN_CLAIMS_SYSTEM = """\
You look for sentences the corrected values have made untrue.

Two mechanical checks have already run and their results are supplied: a table
of substantiation rules mapping each recognised claim to the attribute values
that support it, and a literal scan for copy quoting a superseded figure. You
are looking for what neither can catch, which is meaning.

"Ultra-quiet 45W operation" is caught by the literal scan on the figure.
"Whisper-quiet enough for a bedroom" quotes nothing, is tagged with no claim,
and is equally untrue once the measured noise level moves from 38 dB to 44 dB.
The second sentence is what you are for.

Rules:
- Flag a sentence only where the SUPPLIED corrected values make it wrong or
  unsupportable. Not because it is vague, dated, over-written, or phrased
  differently than you would phrase it.
- Quote the excerpt from the asset text verbatim, so the reviewer can find it.
- Name the claim it leans on: one from the rule table where the sentence
  implies one, or a short phrase of your own where it implies something the
  table does not cover.
- Your flags are advisory. Each is checked against the deterministic rule table
  before it changes anything, and a flag the table does not support is shown to
  the reviewer as a suggestion rather than acted on. So flag what you believe
  and do not pad the list to look thorough.
- If nothing is newly untrue, return an empty list. That is a real answer and a
  common one.

Reply with JSON only:
{
  "flags": [
    {"asset_id": "the asset the sentence is in",
     "excerpt": "the sentence, verbatim",
     "why": "one sentence: which corrected value makes it wrong",
     "claim": "a claim from the rule table, or a short phrase",
     "severity": "HARD"|"SOFT",
     "confidence": 0.0-1.0}
  ]
}"""


def scan_claims_user(changes, assets, claim_rules) -> str:
    return (
        "CORRECTED VALUES (authoritative - these are what is now true):\n"
        f"{attribute_rows(changes)}\n\n"
        "SUBSTANTIATION RULES ALREADY CHECKED DETERMINISTICALLY:\n"
        f"{claim_table(claim_rules)}\n\n"
        "AFFECTED COPY - each asset with the fields it was built from and the "
        "claims it was tagged with:\n"
        f"{asset_lines(assets)}"
    )


# ---------------------------------------------------------------------------
# regenerate: one field of prepared copy
# ---------------------------------------------------------------------------

REGENERATE_SYSTEM = """\
You rewrite one field of prepared product content so that it states the
corrected value.

You are given the current text, the corrected attribute table, the channel's
budget and the source the correction came from. Rewrite that field. Change
nothing else.

Rules:
- Every number, unit, ingredient and allergen you write comes from the supplied
  attribute table, exactly as it appears there. Do not convert units, do not
  round, do not reorder a list the table gives in an order, and do not carry a
  figure over from the old text because it looked untouched.
- Where the table has no value for something the old text asserted, drop the
  assertion. Do not estimate it, and do not leave the superseded figure
  standing because removing it would spoil the sentence.
- Keep the voice, the structure and the length of the original. This is a
  correction, not a rewrite: a reviewer reads the two texts side by side, and
  every difference you introduce is one they have to check.
- The channel budget is a hard limit, re-validated after you answer. Exceeding
  it is not softened, it is rejected and the field comes back to you, so count
  before you answer. Where the field holds several entries - bullets, facets -
  keep one entry per line, because the channel counts entries there rather than
  characters.
- Do not add a claim. A claim in prepared copy has to be substantiated by an
  attribute value, and one you introduce will fail that check and block the
  listing.
- citations: the document ids the values you wrote stand on, taken from the
  supplied source. Copy that changes a published value without a citation is a
  hard violation, so a field you cannot cite is a field you return unchanged,
  with changed false and a note saying why.

Reply with JSON only:
{
  "text": "the rewritten field, and nothing else - no preamble, no commentary",
  "citations": ["the document ids the values stand on", ...],
  "changed": true|false,
  "note": "one sentence: what you changed, or why you did not"
}"""


def regenerate_user(asset, listing, channel, budget, attribute_table,
                    standards, source) -> str:
    return (
        f"FIELD TO REWRITE:\n{asset_lines([asset] if isinstance(asset, dict) else asset)}\n\n"
        f"LISTING:\n{_block(listing, 800)}\n\n"
        f"CHANNEL:\n{_block(channel, 800)}\n\n"
        "CHANNEL BUDGET (re-validated after you answer):\n"
        f"{_block(budget, 800)}\n\n"
        "CORRECTED ATTRIBUTE VALUES (the only source of any number you write):\n"
        f"{attribute_rows(attribute_table)}\n\n"
        f"CONTENT STANDARDS:\n{_block(standards)}\n\n"
        f"SOURCE OF THE CORRECTION (cite this):\n{_block(source, 800)}"
    )


# ---------------------------------------------------------------------------
# enrich: fill a completeness gap, or say you cannot
# ---------------------------------------------------------------------------

ENRICH_SYSTEM = """\
You fill gaps in product data from supplied source extracts, and from nothing
else.

A validation pass found mandatory attributes with no value. For each gap you get
the attribute definition - its type, its unit, what it means - and a set of
retrieval chunks from supplier documents and standards.

The rule that outranks every other rule here: a value you cannot point at in a
supplied chunk does not go in "fills". It goes in "unresolved", and the caller
raises a request to the supplier. Inventing a product fact is the worst thing
this system can do - a plausible allergen list is not an allergen list, and it
will be printed on a label and read by someone who needs it to be right. "The
chunks do not say" is always an acceptable answer and is frequently the correct
one.

Rules:
- quote is the sentence from the chunk carrying the value, verbatim, and
  chunk_id is the chunk it came from. A fill missing either is not a fill.
- The value must match the attribute's declared type: an int is a number, not
  "45 W"; a list[str] is a list; and where the definition says the order carries
  meaning, keep the order the chunk gives.
- A chunk about a different product, or a different variant of this product,
  does not support a value here, however similar they are.
- Where two chunks disagree, do not average them and do not choose on
  plausibility. Report the gap as unresolved and name both.

Reply with JSON only:
{
  "fills": [
    {"entity_id": "the entity the value belongs to",
     "attribute_path": "the path being filled",
     "value": the value, typed as the definition requires,
     "chunk_id": "the chunk it came from",
     "quote": "the sentence, verbatim",
     "confidence": 0.0-1.0}
  ],
  "unresolved": [
    {"entity_id": "...", "attribute_path": "...",
     "why": "one sentence: what the chunks do not say"}
  ]
}"""


def enrich_user(gaps, chunks, attribute_defs) -> str:
    return (
        "GAPS - mandatory attributes with no value in the affected scope:\n"
        f"{_block(gaps)}\n\n"
        "ATTRIBUTE DEFINITIONS (type, unit, and whether order matters):\n"
        f"{_block(attribute_defs)}\n\n"
        "SOURCE EXTRACTS - the only place a value may come from:\n"
        f"{chunk_lines(chunks)}"
    )


# ---------------------------------------------------------------------------
# recommend: the reviewer's narrative
# ---------------------------------------------------------------------------

RECOMMEND_SYSTEM = """\
You write the recommendation a content reviewer will approve or reject.

Every number in your output is supplied to you. You must not compute, estimate,
round or adjust any figure. Quote them as given. If a figure you want is not
supplied, do not invent it - say the analysis does not cover it.

Name only a scenario_id that appears in the ranked list. Those are the
resolutions that were actually validated; anything else is a resolution nobody
has checked.

The narrative has a required shape, because it is what the reviewer is looking
for:

    source -> old value -> new value -> impacted outputs

Name the document and version the correction arrived on, the value that stood
before it, the value that stands now, and what that moves - fields, assets,
listings and channels, in the counts supplied. Then say what the recommended
resolution does about it and what it leaves open.

The ranking is authoritative, including its order. It is a deterministic score
over validator output, with safety pre-sorted ahead of every weight. Where the
top-ranked option is not the widest or the most obvious, explain the trade-off
rather than overriding it.

Say plainly where a channel is being withheld and why, and where a correction is
being applied narrowly on evidence rather than widely on caution - the
reviewer's first question is always "why not the other variant too", and the
answer is in the evidence you were given.

An assumption is something that would change the answer if it turned out to be
wrong. "The supplier's later clarification is authentic" is an assumption. "The
marketplace enforces its own schema" is not.

Reply with JSON only:
{
  "scenario_id": "the id of the resolution you recommend, from the ranked list",
  "narrative": "four to six sentences in the shape above",
  "assumptions": ["...", ...],
  "trade_offs": [{"dimension": "readiness|precision|effort|completeness",
                  "gain": "what improves", "cost": "what it costs"}],
  "rejected_alternatives": [{"scenario_id": "...", "why": "one sentence"}],
  "confidence": 0.0-1.0
}

When a PREVIOUS PLAN section is present you are revising, not starting over.
The reviewer has already read the superseded recommendation, so open the
narrative with what CHANGED and what moved it. The comparison is computed by
the validator - use those figures, do not restate them as your own estimate, and
do not claim a change the numbers do not show."""


# The seven figures the recommendation is written from. Everything else in a
# validation payload is trace.
_PROMPT_KPIS = ("listings_ready_pct", "fields_affected", "assets_stale",
                "channels_blocked", "completeness_pct", "safety_flags",
                "republish_steps")


def _ranked_for_prompt(ranked: list[dict]) -> list[dict]:
    """Trim to what the model needs.

    A full validation payload is mostly trace - every violation, every action,
    the change set itself - and it crowds out the figures the recommendation is
    actually written from. The trim is about the model reading the numbers, not
    about token cost.
    """
    out = []
    for r in ranked or []:
        kpis = r.get("kpis") or {}
        delta = r.get("delta") or {}
        scope = r.get("scope") or delta.get("scope") or {}
        out.append({
            "scenario_id": r.get("scenario_id") or r.get("delta_id"),
            "name": r.get("name", ""),
            "summary": r.get("summary", ""),
            "score": r.get("score"),
            "feasible": r.get("feasible"),
            "pareto_optimal": r.get("pareto_optimal"),
            "safety_hold": r.get("safety_hold"),
            "scope": {"level": scope.get("level"),
                      "entities": scope.get("entities") or []},
            "kpis": {k: kpis[k] for k in _PROMPT_KPIS if k in kpis},
            # What binds, in the validator's own words. Three is enough for a
            # reviewer to see the shape of the blockage.
            "binding_constraints": [v.get("detail") or v.get("constraint")
                                    for v in (r.get("violations") or [])
                                    if v.get("severity") == "HARD"][:3],
            "actions": [a.get("kind") for a in (delta.get("actions") or [])],
        })
    return out


def recommend_user(ranked, change_lines, citations, case_summary, weights,
                   plan_diff: dict | None = None,
                   blocked: dict | None = None,
                   clarification: dict | None = None,
                   precedent: dict | None = None) -> str:
    """Assemble the recommendation brief.

    The last four arguments are branch outputs, and each is present only on runs
    that took that branch. That is deliberate: the writer should be told "no
    resolution publishes every channel" exactly when it is true, and told
    nothing when it is not, rather than reasoning about an empty section.
    """
    context = ""
    if blocked:
        context += (
            "\n\nNOTHING IS FULLY PUBLISHABLE. Every candidate leaves at least "
            "one channel blocked by a HARD rule. Recommend the least-bad one, "
            "say plainly which channels do not go live, and name what binds "
            "them:\n" + _block(blocked, 1800)
        )
    if clarification:
        context += (
            "\n\nSOURCES DISAGREE AND THE SUPPLIER HAS BEEN ASKED. This run "
            "does not settle the conflict; the precedence order says which "
            "document leads until it is settled. Do not present the question as "
            "resolved:\n" + _block(clarification, 1800)
        )
    if precedent:
        context += (
            "\n\nTHIS HAS HAPPENED BEFORE. What the postmortem recorded:\n"
            + _block(precedent, 1800)
        )

    previous = ""
    if plan_diff:
        previous = (
            "\n\nPREVIOUS PLAN (you are revising it, not reopening the whole "
            "case). This comparison is computed, not estimated:\n"
            + _block(plan_diff, 1800)
        )

    return (
        f"CASE:\n{case_summary}\n\n"
        "CHANGES - source, old value, new value, impacted outputs (assembled "
        "from the catalog):\n"
        f"{change_table(change_lines)}\n\n"
        f"OBJECTIVE WEIGHTS SET BY THE REVIEWER: {json.dumps(weights or {})}\n\n"
        "VALIDATED RESOLUTIONS, RANKED (authoritative - every figure comes from "
        "the deterministic validator):\n"
        f"{_block(_ranked_for_prompt(ranked), 3200)}\n\n"
        f"AVAILABLE CITATIONS:\n{citation_lines(citations)}"
        + context
        + previous
    )
