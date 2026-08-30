"""Measure whether the model is right, not just whether the pipeline runs.

The test suite runs with the gateway pinned to a closed port, so what CI
exercises is the deterministic fallback in every node. That is the correct
choice for CI and it means nothing in the suite says whether a model reading a
supplier document gets the answer right. This does.

Run:  python scripts/evaluate.py                  # the configured tiers
      python scripts/evaluate.py --all-models     # every chat model served
      python scripts/evaluate.py --only extract   # one touchpoint
      python scripts/evaluate.py --json out.json

It needs a live gateway, which is why it is a script and not a test. It uses
the record/replay cache, so the first run costs tokens and every run after it
is free and identical.

Four touchpoints, chosen because each is a different kind of wrong:

*   **extract** - did it read the right field and the right value out of prose.
    Materiality is reported as precision and recall separately because the two
    errors do not cost the same: a false negative is a correction that never
    reaches a reviewer, a false positive is noise on their list. ``applies_to``
    is a three-class confusion matrix, and the cell that matters is UNCLEAR
    predicted as VARIANT - a model that resolves an ambiguity the document did
    not resolve has skipped the step this architecture exists to perform.
*   **resolve_scope** - which variants the correction was applied to, against
    the scope the supplier's own payload settles, plus how often the widest
    reading was taken with a narrower one on the table.
*   **scan_claims** - precision and recall against the claims
    ``engine.CLAIM_RULES`` confirms have stopped holding.
*   **calibration** - stated confidence against observed accuracy, bucketed.
    ``engine.SAFETY_CONFIDENCE`` withholds every listing whose safety-class
    value is asserted below 0.90, so a model that says 0.8 and is right 40% of
    the time is a governance defect rather than a quality one. This is the
    number that justifies that threshold or does not.

The answer key is ``data/golden/extractions.jsonl``, written by
scripts/generate_data.py out of the same event payloads the prose was written
from. Nothing here was hand-labelled, and the key regenerates with the data.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# A dedicated database, pinned before anything reads it. The eval resets the
# store between scenarios and must not be able to do that to a demo in progress.
os.environ.setdefault("DB_PATH", "data/eval.db")

from sc import bootstrap, db  # noqa: E402

bootstrap.load_env()
os.environ["DB_PATH"] = os.environ.get("DB_PATH") or "data/eval.db"

from sc.graph import build as graph_build  # noqa: E402
from sc.graph import nodes, prompts  # noqa: E402
from sc.llm import gateway, models as model_registry  # noqa: E402
from sc.llm.gateway import GatewayError  # noqa: E402
from sc.replay import ingest, tape  # noqa: E402
from sc.sim import engine  # noqa: E402
from sc.state import baseline as baseline_mod  # noqa: E402

KEY_PATH = ROOT / "data" / "golden" / "extractions.jsonl"
REPORT_PATH = ROOT / "data" / "eval" / "report.json"

# ---------------------------------------------------------------------------
# Throttle
#
# Every node in the graph catches GatewayError and falls back, which is exactly
# what it should do in production and exactly wrong here: a provider quota
# exhausted halfway through a sweep produces a run that measures the fallback
# and reports it as the model. An unthrottled matrix - five models, five
# scenarios, a graph run each - hits a per-minute limit within two models, and
# every number after that is silently about something else.
#
# So the pacing lives in the script rather than in sc.llm.gateway. It is a
# property of asking the whole matrix at once, not of the system under test,
# and putting it in the gateway would change the behaviour the eval exists to
# observe.
# ---------------------------------------------------------------------------

MIN_INTERVAL = float(os.environ.get("EVAL_MIN_INTERVAL", "4.0"))
BACKOFF = (15, 30, 60, 120)

_throttle = {"last": 0.0, "waits": 0, "seconds": 0.0, "exhausted": False}
_inner_post = gateway._post


def _throttled_post(path: str, body: dict) -> dict:
    error: Exception | None = None
    # A per-minute limit clears in seconds; a project spend cap does not clear
    # at all. Once a full backoff chain has failed, waiting again just turns a
    # capped account into a very slow way of producing the same error, so the
    # rest of the run fails fast and says so.
    chain = (0,) if _throttle["exhausted"] else (0, *BACKOFF)
    for wait in chain:
        if wait:
            _throttle["waits"] += 1
            _throttle["seconds"] += wait
            print(f"      provider is rate limiting - waiting {wait}s",
                  flush=True)
            time.sleep(wait)
        gap = MIN_INTERVAL - (time.monotonic() - _throttle["last"])
        if gap > 0:
            time.sleep(gap)
        try:
            result = _inner_post(path, body)
            _throttle["last"] = time.monotonic()
            return result
        except GatewayError as exc:
            _throttle["last"] = time.monotonic()
            if "rate limiting" not in str(exc):
                raise
            error = exc
    if not _throttle["exhausted"]:
        _throttle["exhausted"] = True
        print("      the provider is still refusing after every backoff. If "
              "this is a spend cap\n      rather than a per-minute limit it "
              "will not clear; the rest of this run will\n      fail fast and "
              "every affected row is labelled as a quota result, not a model "
              "one.", flush=True)
    raise error


gateway._post = _throttled_post

# The three answers the extraction prompt offers. Anything else a model returns
# is counted as OTHER rather than mapped onto the nearest one - a reply outside
# the contract is a defect, and folding it into a real class hides it.
CLASSES = ("BASE", "VARIANT", "UNCLEAR")

# Confidence buckets. Ten equal bins reads as noise on a set this size; these
# are the bands the gate actually cares about, with 0.90 as its own edge
# because that is where engine.SAFETY_CONFIDENCE binds.
BUCKETS = ((0.0, 0.5), (0.5, 0.7), (0.7, 0.8), (0.8, 0.9), (0.9, 1.01))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def load_key() -> list[dict]:
    if not KEY_PATH.exists():
        raise SystemExit(f"no answer key at {KEY_PATH}. Run "
                         "scripts/generate_data.py first.")
    return [json.loads(line) for line in
            KEY_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]


# The response cache lives in the application database, and every scenario
# starts by dropping that database - so without a sidecar each reseed would
# throw the cache away and every run would be a fresh bill. This keeps the
# cache outside the store it is carried through, which is what makes a repeat
# run free and identical rather than merely cheaper.
CACHE_DB = ROOT / "data" / "eval" / "llm_cache.db"
CACHE_COLUMNS = ("cache_key", "model", "temperature", "request", "response",
                 "prompt_tokens", "completion_tokens", "cost_usd",
                 "latency_ms", "created_at", "hits", "run_id", "agent")


def _cache_sidecar():
    import sqlite3

    CACHE_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(CACHE_DB))
    conn.execute(
        "CREATE TABLE IF NOT EXISTS llm_calls (cache_key TEXT PRIMARY KEY,"
        " model TEXT, temperature REAL, request TEXT, response TEXT,"
        " prompt_tokens INTEGER, completion_tokens INTEGER, cost_usd REAL,"
        " latency_ms REAL, created_at TEXT, hits INTEGER, run_id TEXT,"
        " agent TEXT)")
    return conn


def save_cache() -> int:
    """Copy anything new out of the store before it is dropped."""
    try:
        rows = db.query(f"SELECT {', '.join(CACHE_COLUMNS)} FROM llm_calls")
    except Exception:
        return 0
    conn = _cache_sidecar()
    conn.executemany(
        f"INSERT OR REPLACE INTO llm_calls ({', '.join(CACHE_COLUMNS)})"
        f" VALUES ({', '.join('?' * len(CACHE_COLUMNS))})",
        [tuple(row[c] for c in CACHE_COLUMNS) for row in rows])
    conn.commit()
    conn.close()
    return len(rows)


def load_cache() -> int:
    conn = _cache_sidecar()
    rows = conn.execute(
        f"SELECT {', '.join(CACHE_COLUMNS)} FROM llm_calls").fetchall()
    conn.close()
    if not rows:
        return 0
    target = db.connect()
    target.executemany(
        f"INSERT OR IGNORE INTO llm_calls ({', '.join(CACHE_COLUMNS)})"
        f" VALUES ({', '.join('?' * len(CACHE_COLUMNS))})", rows)
    target.commit()
    return len(rows)


def reseed() -> None:
    """A fresh store with the tape loaded and nothing released.

    Every measurement starts here so a scenario cannot read facts a previous
    scenario recorded - which would make the numbers depend on the order the
    scenarios happened to run in.
    """
    save_cache()
    graph_build.reset_graph()
    db.close_all()
    # Checkpoints outlive the store they describe, so a thread id reused across
    # scenarios would resume a finished run instead of starting one.
    for suffix in ("", "-wal", "-shm"):
        path = Path(str(graph_build.checkpoint_path()) + suffix)
        if path.exists():
            try:
                path.unlink()
            except OSError:
                pass
    db.init_db(drop=True)
    load_cache()
    baseline_mod.get.cache_clear()
    bootstrap.ensure_ready()


def events_by_id() -> dict:
    rows = db.query("SELECT * FROM events ORDER BY seq")
    return {r["id"]: tape._row_to_event(r) for r in rows}


def release_through(day: int) -> None:
    """Release every event up to and including a horizon day, and ingest it."""
    base = baseline_mod.get()
    cutoff = base.horizon_start.toordinal() + day
    target = 0
    for row in db.query("SELECT seq, ts FROM events ORDER BY seq"):
        if date.fromisoformat(row["ts"][:10]).toordinal() <= cutoff:
            target = row["seq"]
    ingest.ingest(tape.jump_to(target))


def pin(model: str) -> None:
    """Point both tiers at one model, so a whole run is attributable to it."""
    os.environ["LITELLM_FAST_MODEL"] = model
    os.environ["LITELLM_REASONING_MODEL"] = model


def chat_models() -> list[str]:
    tiers = model_registry.list_models(refresh=True)["by_tier"]
    return sorted(set(tiers.get("fast", []) + tiers.get("reasoning", [])))


# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------


def coerced(value, dtype: str):
    """The value as the catalog would hold it, or a marker that it would not.

    Compared after coercion because that is what the catalog acts on: a model
    answering "65" for an int field has read the document correctly, and
    counting it wrong would measure JSON typing rather than comprehension. The
    raw comparison is reported alongside so the difference is visible.
    """
    parsed, why = nodes._coerce(value, dtype)
    return ("__uncoercible__", why) if why else (parsed, "")


def bucket_of(confidence) -> str | None:
    try:
        value = float(confidence)
    except (TypeError, ValueError):
        return None
    for low, high in BUCKETS:
        if low <= value < high:
            return f"{low:.2f}-{min(high, 1.0):.2f}"
    return None


def rates(tp: int, fp: int, fn: int) -> dict:
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    return {"tp": tp, "fp": fp, "fn": fn, "precision": precision,
            "recall": recall}


def drop_bucket(reason: str) -> str:
    """The failure taxonomy ``_extraction_rows`` already produces."""
    if "no such attribute" in reason:
        return "named an attribute the catalog has no path for"
    if "no such product or variant" in reason:
        return "named a product or variant the catalog does not hold"
    if "no value" in reason:
        return "named an attribute with no value"
    if "does not parse as" in reason or "expected " in reason:
        return "gave a value that will not coerce to the declared type"
    return "other"


def pct(numerator: int, denominator: int) -> str:
    if not denominator:
        return "   n/a"
    return f"{100 * numerator / denominator:5.1f}%"


# ---------------------------------------------------------------------------
# extract
# ---------------------------------------------------------------------------


def score_extraction(base, event, golden: dict, reply: dict,
                     error: str | None) -> dict:
    """One document, graded against the payload its prose was written from."""
    truth_path = golden["attribute_path"]
    pred_path = reply.get("attribute_path")
    pred_path = str(pred_path) if pred_path is not None else None
    path_ok = (pred_path == truth_path)

    dtype = (base.attr_defs[truth_path].dtype
             if truth_path in base.attr_defs else "str")
    truth_value, _ = coerced(golden["new_value"], dtype)
    pred_value, coercion_error = coerced(reply.get("new_value"), dtype)
    orphan = False
    if truth_path is None:
        # Nothing the catalog can hold: the right answer is to name no path,
        # which is what the prompt asks for. A value left beside a null path is
        # inert - _extraction_rows skips a candidate with no path before it
        # looks at the value - so it is recorded and not counted against.
        value_ok = True
        raw_ok = True
        orphan = reply.get("new_value") is not None
    else:
        value_ok = path_ok and pred_value == truth_value
        raw_ok = path_ok and reply.get("new_value") == golden["new_value"]

    # Did it read *a* correction this document asserts, rather than the one the
    # payload leads with? The reply template carries one attribute_path and the
    # finale revises two values, so "wrong field" and "the other right field"
    # are different results and only one of them is a comprehension failure.
    in_key = False
    for row in golden["rows"]:
        row_dtype = (base.attr_defs[row["attribute_path"]].dtype
                     if row["attribute_path"] in base.attr_defs else "str")
        if (pred_path == row["attribute_path"]
                and coerced(reply.get("new_value"), row_dtype)[0]
                == coerced(row["new_value"], row_dtype)[0]):
            in_key = True
            break

    material_pred = bool(reply.get("material")) if error is None else False

    applies_pred = str(reply.get("applies_to") or "").upper() or None
    if applies_pred not in CLASSES:
        applies_pred = "OTHER" if applies_pred else None

    kind_pred = str(reply.get("kind") or "").upper() or None

    rows, dropped, considered = ([], [], 0)
    if error is None:
        rows, dropped, considered = nodes._extraction_rows(
            base, event, reply, event.ts)

    return {
        "event_id": golden["event_id"],
        "label": golden["label"],
        "document": f"{golden['doc_id'] or '-'} {golden['doc_version'] or ''}".strip(),
        "error": error,
        "material_true": golden["material"],
        "material_pred": material_pred,
        "path_true": truth_path,
        "path_pred": pred_path,
        "path_ok": path_ok,
        "value_true": golden["new_value"],
        "value_pred": reply.get("new_value"),
        "value_ok": value_ok,
        "value_ok_raw": raw_ok,
        "orphan_value": orphan,
        "reads_a_real_correction": in_key or (truth_path is None
                                              and pred_path is None),
        "coercion_error": coercion_error or None,
        "applies_true": golden["applies_to"],
        "applies_pred": applies_pred,
        "applies_ok": (golden["applies_to"] is not None
                       and applies_pred == golden["applies_to"]),
        "applies_defensible": (applies_pred in
                               (golden["applies_to_acceptable"] or [])),
        "kind_true": golden["kind"],
        "kind_pred": kind_pred,
        "kind_ok": kind_pred == golden["kind"],
        "confidence": reply.get("confidence"),
        "is_correction_ok": bool(reply.get("is_correction")) == golden["is_correction"],
        "rows_written": len(rows),
        "rows_expected": len(golden["rows"]),
        "considered": considered,
        "dropped": dropped,
        # Two verdicts, because confidence and accuracy are answers to
        # different questions. ``correct`` is the strict one: did it produce
        # the reading the payload leads with. ``truthful`` asks whether what it
        # said is true of the document at all, which is what a stated
        # confidence is a claim about - so that is what the reliability curve
        # is built from.
        "correct": (error is None
                    and material_pred == golden["material"]
                    and path_ok and value_ok),
        "truthful": (error is None
                     and material_pred == golden["material"]
                     and (in_key or (truth_path is None and pred_path is None))),
    }


def run_extract(base, key: list[dict], model: str, run_id: str) -> dict:
    events = events_by_id()
    scored: list[dict] = []
    hint = nodes._catalog_hint(base)

    for golden in key:
        event = events[golden["event_id"]]
        reply, error = {}, None
        try:
            reply, _ = gateway.complete_json(
                nodes.extract_messages(base, event, hint),
                model=model, agent="eval:extract", run_id=run_id)
        except GatewayError as exc:
            error = str(exc)[:200]
        scored.append(score_extraction(base, event, golden, reply, error))

    return summarise_extract(scored)


def summarise_extract(scored: list[dict]) -> dict:
    """Everything measured over the documents the model actually answered.

    A refused reply is a different failure from a wrong one and is counted as
    one: the node catches GatewayError and reads the structured hint instead,
    so a document whose reply would not parse is not a misread field, it is a
    call that never influenced anything. Mixing the two would report a model
    that cannot emit a JSON object as one that cannot read a spec sheet.
    """
    answered = [s for s in scored if s["error"] is None]
    refused = [s for s in scored if s["error"] is not None]

    material = rates(
        tp=sum(1 for s in answered if s["material_true"] and s["material_pred"]),
        fp=sum(1 for s in answered
               if not s["material_true"] and s["material_pred"]),
        fn=sum(1 for s in answered
               if s["material_true"] and not s["material_pred"]))
    material["tn"] = sum(1 for s in answered
                         if not s["material_true"] and not s["material_pred"])

    matrix: dict[str, dict[str, int]] = {}
    graded = [s for s in answered if s["applies_true"] is not None
              and s["applies_pred"] is not None]
    for s in graded:
        row = matrix.setdefault(s["applies_true"], {})
        row[s["applies_pred"]] = row.get(s["applies_pred"], 0) + 1

    drops: dict[str, int] = {}
    for s in answered:
        for reason in s["dropped"]:
            drops[drop_bucket(reason)] = drops.get(drop_bucket(reason), 0) + 1

    contract: dict[str, int] = {}
    for s in refused:
        reason = ("reply was a JSON array, not an object"
                  if "not a JSON object" in (s["error"] or "")
                  else "reply was not valid JSON"
                  if "valid JSON" in (s["error"] or "")
                  # Not a result about the model. A run reporting these has
                  # measured a quota and should be re-run more slowly.
                  else "PROVIDER RATE LIMIT - not a model result"
                  if "rate limit" in (s["error"] or "")
                  else "gateway call failed")
        contract[reason] = contract.get(reason, 0) + 1

    correct = sum(1 for s in answered if s["correct"])
    return {
        "reads_a_real_correction": sum(1 for s in answered
                                       if s["reads_a_real_correction"]),
        "truthful": sum(1 for s in answered if s["truthful"]),
        "orphan_values": sum(1 for s in answered if s["orphan_value"]),
        "documents": len(scored),
        "answered": len(answered),
        "refused": len(refused),
        "refusal_reasons": contract,
        "path_exact": sum(1 for s in answered if s["path_ok"]),
        "value_exact_coerced": sum(1 for s in answered if s["value_ok"]),
        "value_exact_raw": sum(1 for s in answered if s["value_ok_raw"]),
        "whole_reading_correct": correct,
        # What the pipeline ends up with. The fallback reads the same payload
        # the answer key was written from, so it is right on every document by
        # construction - which is a property of the key, not evidence about the
        # fallback, and is the one thing this eval cannot measure.
        "whole_reading_with_fallback": correct + len(refused),
        "kind_correct": sum(1 for s in answered
                            if s["material_true"] and s["kind_ok"]),
        "kind_graded": sum(1 for s in answered if s["material_true"]),
        "is_correction_correct": sum(1 for s in answered
                                     if s["is_correction_ok"]),
        "materiality": material,
        "applies_to": {
            "matrix": matrix,
            "graded": len(graded),
            "exact": sum(1 for s in graded if s["applies_ok"]),
            "defensible": sum(1 for s in graded if s["applies_defensible"]),
            # The failure the whole scenario-one architecture exists to prevent.
            "unclear_called_variant": matrix.get("UNCLEAR", {}).get("VARIANT", 0),
            "unclear_total": sum(matrix.get("UNCLEAR", {}).values()),
        },
        "drop_reasons": drops,
        "rows_written": sum(s["rows_written"] for s in answered),
        "rows_expected": sum(s["rows_expected"] for s in scored),
        "detail": scored,
    }


# ---------------------------------------------------------------------------
# resolve_scope and scan_claims - measured on real runs
# ---------------------------------------------------------------------------


def scenarios_from(key: list[dict], base) -> list[dict]:
    """One run per correction document, with the scope its payload settles.

    The truth is the union of every correction on that product the tape has
    already delivered, because that is what the run is deciding about: a case
    is a product, and a run at day 30 is holding the day-18 correction too.
    Where the newest correction on the product leaves the variant open - the
    day-28 inject, which is the whole point of the scenario - there is no
    correct answer to score and the run is reported rather than graded.
    """
    corrections = [g for g in key if g["material"] and g["rows"]]
    out: list[dict] = []
    seen: set[tuple] = set()

    for golden in corrections:
        doc = (golden["doc_id"], golden["doc_version"])
        if doc in seen:
            continue
        seen.add(doc)
        product = golden["product"] or ""
        if product not in base.products:
            continue

        day = (date.fromisoformat(golden["ts"][:10]).toordinal()
               - base.horizon_start.toordinal())
        contributing = [g for g in corrections
                        if g["product"] == product and g["ts"] <= golden["ts"]]
        truth = sorted({e for g in contributing for e in g["scope_entities"]})
        out.append({
            "id": f"{golden['doc_id']}-{golden['doc_version']}",
            "event_id": golden["event_id"],
            "label": golden["label"],
            "product": product,
            "day": day,
            "truth": truth,
            # Graded only where the newest correction names its variants. The
            # inject deliberately does not, and calling a guess correct there
            # would reward exactly the behaviour the architecture forbids.
            "scored": bool(contributing[-1]["scope_determinate"]),
        })
    return sorted(out, key=lambda s: s["day"])


def run_to(node: str, incident: str, thread: str, case_id: str) -> dict:
    """Drive a real run and stop it once the node under test has landed.

    Streaming and breaking rather than invoking: everything past scan_claims is
    copy rewriting, which costs a model call per asset and answers a question
    this script is not asking.
    """
    stream = graph_build.stream_run(incident, thread, case_id=case_id)
    try:
        for update in stream:
            if update["node"] == node:
                break
    finally:
        try:
            stream.close()
        except Exception:
            pass  # a graph that objects to being stopped is not a finding
    return graph_build.snapshot(thread).get("values") or {}


def score_scope(values: dict, scenario: dict) -> dict:
    chosen = values.get("chosen_scope") or {}
    picked = sorted(chosen.get("entities") or [])
    candidates = values.get("scope_candidates") or []
    widest = (max(candidates, key=lambda c: len(c.get("entities") or []))
              if candidates else {})
    widest_entities = sorted(widest.get("entities") or [])
    truth = scenario["truth"]

    on_the_table = any(sorted(c.get("entities") or []) == truth
                       for c in candidates)
    took_widest = bool(picked) and picked == widest_entities

    return {
        "scenario": scenario["id"],
        "product": scenario["product"],
        "day": scenario["day"],
        "scored": scenario["scored"],
        "truth": truth,
        "picked": picked,
        "level": chosen.get("level"),
        "confidence": chosen.get("confidence"),
        "candidates": [{"entities": sorted(c.get("entities") or []),
                        "level": c.get("level"),
                        "confidence": c.get("confidence")}
                       for c in candidates],
        "exact": scenario["scored"] and picked == truth,
        "too_wide": scenario["scored"] and set(picked) > set(truth),
        "too_narrow": scenario["scored"] and set(picked) < set(truth),
        "took_widest": took_widest,
        # The specific error worth naming: the broadest reading taken while a
        # narrower one that matches the truth was sitting on the table.
        "widest_over_supportable": bool(
            scenario["scored"] and took_widest and on_the_table
            and set(picked) > set(truth)),
        "severity": values.get("severity"),
        "status": values.get("status"),
        # Which nodes in this run answered from their fallback instead of a
        # model. A scenario with anything here is measuring the fallback.
        "fell_back": sorted({str(e).split(":")[0]
                             for e in values.get("errors") or []
                             if "gateway" in str(e) or "rate limit" in str(e)
                             or "unreachable" in str(e)}),
    }


def score_claims(values: dict, scenario: dict, model: str,
                 run_id: str) -> dict | None:
    """Grade the model's raw flags against the claims the rule table confirms.

    The node's own output is not usable for this: it promotes a flag the table
    supports and appends every table finding the model missed, so scoring it
    would grade the table. The same prompt is asked again here, against the same
    inputs, and the reply is compared before any of that happens - which is what
    precision and recall on the model actually mean.
    """
    rows, assets, confirmed = nodes.scan_claims_inputs(values)
    if not rows or not assets:
        return None

    try:
        found, _ = gateway.complete_json(
            [{"role": "system", "content": prompts.SCAN_CLAIMS_SYSTEM},
             {"role": "user", "content": prompts.scan_claims_user(
                 rows, assets, engine.CLAIM_RULES)}],
            model=model, agent="eval:scan_claims", run_id=run_id)
        flags = [f for f in (found.get("flags") or []) if isinstance(f, dict)]
        error = None
    except GatewayError as exc:
        flags, error = [], str(exc)[:200]

    known = {a["id"] for a in assets}
    truth = {(asset_id, claim) for asset_id, claims in confirmed.items()
             for claim in claims}

    on_table, off_table, unknown_asset = set(), [], 0
    for flag in flags:
        asset_id = str(flag.get("asset_id") or "")
        claim = str(flag.get("claim") or "")
        if asset_id not in known:
            unknown_asset += 1
            continue
        if claim in engine.CLAIM_RULES:
            on_table.add((asset_id, claim))
        else:
            # The prompt invites a phrase of its own where the copy implies
            # something the table does not cover. Advisory by design, so it is
            # counted apart rather than held against precision.
            off_table.append({"asset_id": asset_id, "claim": claim,
                              "excerpt": str(flag.get("excerpt") or "")[:120],
                              "confidence": flag.get("confidence")})

    scored = rates(tp=len(on_table & truth), fp=len(on_table - truth),
                   fn=len(truth - on_table))
    return {
        "scenario": scenario["id"],
        "error": error,
        "assets_in_scope": len(assets),
        "table_confirms": len(truth),
        "flags_returned": len(flags),
        "flags_on_table": len(on_table),
        "flags_off_table": len(off_table),
        "flags_on_unknown_asset": unknown_asset,
        "off_table_examples": off_table[:4],
        "missed": sorted(f"{a}:{c}" for a, c in truth - on_table),
        "confidences": [{"claim": str(f.get("claim") or ""),
                         "confidence": f.get("confidence"),
                         "hit": (str(f.get("asset_id") or ""),
                                 str(f.get("claim") or "")) in truth}
                        for f in flags],
        **scored,
    }


def run_scenarios(key: list[dict], model: str, run_id: str,
                  want_claims: bool) -> tuple[list[dict], list[dict]]:
    reseed()
    scenario_list = scenarios_from(key, baseline_mod.get())

    scope_rows: list[dict] = []
    claim_rows: list[dict] = []
    for index, scenario in enumerate(scenario_list):
        reseed()
        release_through(scenario["day"])
        thread = f"EVAL-{scenario['id']}"
        try:
            values = run_to("scan_claims", f"INC-EVAL-{index}", thread,
                            scenario["product"])
        except Exception as exc:  # a run that dies is a result, not a crash
            scope_rows.append({"scenario": scenario["id"], "scored": False,
                               "error": f"{type(exc).__name__}: {exc}"[:200],
                               "truth": scenario["truth"], "picked": [],
                               "candidates": [], "exact": False,
                               "too_wide": False, "too_narrow": False,
                               "took_widest": False,
                               "widest_over_supportable": False})
            continue

        scope_rows.append(score_scope(values, scenario))
        if want_claims:
            scored = score_claims(values, scenario, model, run_id)
            if scored:
                claim_rows.append(scored)

    return scope_rows, claim_rows


# ---------------------------------------------------------------------------
# calibration
# ---------------------------------------------------------------------------


def reliability(samples: list[tuple]) -> list[dict]:
    """Stated confidence against observed accuracy, one row per bucket."""
    grouped: dict[str, list[bool]] = {}
    for confidence, correct in samples:
        name = bucket_of(confidence)
        if name is None:
            continue
        grouped.setdefault(name, []).append(bool(correct))

    out = []
    for low, high in BUCKETS:
        name = f"{low:.2f}-{min(high, 1.0):.2f}"
        hits = grouped.get(name)
        if not hits:
            continue
        out.append({
            "bucket": name,
            "n": len(hits),
            "correct": sum(hits),
            "observed": sum(hits) / len(hits),
            "midpoint": (low + min(high, 1.0)) / 2,
        })
    return out


def calibration_for(result: dict) -> dict:
    extract_samples = [(s["confidence"], s["truthful"])
                       for s in result["extract"]["detail"]
                       if s["error"] is None]
    scope_samples = [(s.get("confidence"), s.get("exact"))
                     for s in result.get("scope", []) if s.get("scored")]
    claim_samples = [(f["confidence"], f["hit"])
                     for row in result.get("claims", [])
                     for f in row.get("confidences", [])]

    high = [s for s in result["extract"]["detail"]
            if s["error"] is None
            and isinstance(s["confidence"], (int, float))
            and float(s["confidence"]) >= engine.SAFETY_CONFIDENCE]
    return {
        "extract": reliability(extract_samples),
        "resolve_scope": reliability(scope_samples),
        "scan_claims": reliability(claim_samples),
        "at_or_above_safety_threshold": {
            "threshold": engine.SAFETY_CONFIDENCE,
            "n": len(high),
            "correct": sum(1 for s in high if s["truthful"]),
        },
    }


def safety_gate(key: list[dict], detail: list[dict]) -> dict:
    """What the fail-closed gate would do with the confidences just measured.

    ``engine.SAFETY_CONFIDENCE`` withholds a listing whose safety-class value
    was asserted below 0.90. So the only confidences that decide anything are
    the ones attached to a safety-class correction, and how many of those clear
    the bar - and are right - is the governance number.
    """
    safety_events = {g["event_id"] for g in key
                     if any(str(r["attribute_path"]).startswith("food.allergens")
                            for r in g["rows"])}
    rows = [s for s in detail
            if s["event_id"] in safety_events and s["error"] is None]
    clears = [s for s in rows
              if isinstance(s["confidence"], (int, float))
              and float(s["confidence"]) >= engine.SAFETY_CONFIDENCE]
    return {
        "safety_documents": len(rows),
        "clears_threshold": len(clears),
        "clears_and_correct": sum(1 for s in clears if s["truthful"]),
        "withheld_but_correct": sum(1 for s in rows
                                    if s not in clears and s["truthful"]),
        "confidences": [{"event_id": s["event_id"],
                         "confidence": s["confidence"],
                         "correct": s["truthful"]} for s in rows],
        "fallback_confidence": nodes.FALLBACK_CONFIDENCE,
    }


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def _rate(value) -> str:
    return "  n/a " if value is None else f"{100 * value:5.1f}%"


def render_result(name: str, result: dict) -> None:
    e = result["extract"]
    n = e["answered"]
    total = e["documents"]
    print(f"\n{'=' * 78}\nMODEL: {name}\n{'=' * 78}")

    print("\nEXTRACT - reading the correction out of prose")
    print(f"  documents in the key         {total}")
    print(f"  replies the gateway accepted {n}"
          + (f"   ({e['refused']} refused, each one falling back to the "
             f"structured hint)" if e["refused"] else ""))
    for reason, count in sorted(e["refusal_reasons"].items(),
                                key=lambda kv: -kv[1]):
        print(f"      {count:>3}  {reason}")
    print(f"\n  scored over the {n} answered:")
    print(f"  attribute_path exact         {e['path_exact']:>3}/{n}  "
          f"{pct(e['path_exact'], n)}")
    print(f"  new_value exact, coerced     {e['value_exact_coerced']:>3}/{n}  "
          f"{pct(e['value_exact_coerced'], n)}")
    print(f"  new_value exact, raw JSON    {e['value_exact_raw']:>3}/{n}  "
          f"{pct(e['value_exact_raw'], n)}")
    print(f"  read a correction the doc does assert  {e['reads_a_real_correction']:>3}"
          f"/{n}  {pct(e['reads_a_real_correction'], n)}")
    print(f"  whole reading correct        {e['whole_reading_correct']:>3}/{n}  "
          f"{pct(e['whole_reading_correct'], n)}")
    print(f"  materiality + a true reading {e['truthful']:>3}/{n}  "
          f"{pct(e['truthful'], n)}   <- what the confidence is a claim about")
    print(f"  correction kind              {e['kind_correct']:>3}/"
          f"{e['kind_graded']}  {pct(e['kind_correct'], e['kind_graded'])}"
          f"   (material documents)")
    print(f"  with the fallback standing in for refusals: "
          f"{e['whole_reading_with_fallback']}/{total} - but the fallback reads "
          f"the\n  same payload the key was written from, so that is arithmetic, "
          f"not evidence.")
    if e["rows_expected"] > e["documents"]:
        extra = e["rows_expected"] - sum(
            1 for s in e["detail"] if s["path_true"] is not None)
        print(f"  the catalog ends up with {e['rows_expected']} corrected values "
              f"across the key, but the reply\n  template carries one "
              f"attribute_path: {extra} of them are folded in from the event's\n"
              f"  structured `changes` list, which no model is ever asked for.")

    m = e["materiality"]
    print(f"\n  materiality as a classifier   tp {m['tp']:<3} fp {m['fp']:<3} "
          f"fn {m['fn']:<3} tn {m['tn']:<3}")
    print(f"    precision {_rate(m['precision'])}   "
          f"(a false positive is reviewer noise)")
    print(f"    recall    {_rate(m['recall'])}   "
          f"(a false negative is a correction that reaches shoppers)")

    a = e["applies_to"]
    print(f"\n  applies_to, {a['graded']} graded - rows are the truth, "
          f"columns the answer")
    header = [c for c in CLASSES] + ["OTHER"]
    print("           " + "".join(f"{h:>9}" for h in header))
    for truth in CLASSES:
        row = a["matrix"].get(truth, {})
        print(f"    {truth:<7}" + "".join(f"{row.get(h, 0):>9}" for h in header))
    print(f"    exact {a['exact']}/{a['graded']}, "
          f"defensible {a['defensible']}/{a['graded']} "
          f"(a one-model product cannot tell the three apart)")
    if a["unclear_total"]:
        print(f"    UNCLEAR read as VARIANT: {a['unclear_called_variant']}"
              f"/{a['unclear_total']}  <- the failure scenario one exists to stop")

    if e["drop_reasons"]:
        print("\n  extractions the catalog refused")
        for reason, count in sorted(e["drop_reasons"].items(),
                                    key=lambda kv: -kv[1]):
            print(f"    {count:>3}  {reason}")
    else:
        print("\n  extractions the catalog refused: none")

    print("\n  document by document")
    print(f"    {'event':<11}{'document':<11}{'what it is':<24}"
          f"{'path':<22}{'value':<14}{'conf':>5}  ok")
    for s in e["detail"]:
        if s["error"]:
            print(f"    {s['event_id']:<11}{s['document']:<11}"
                  f"{s['label'][:23]:<24}{'-- reply refused --':<36}"
                  f"{'':>5}   -")
            continue
        value = str(s["value_pred"])
        if not s["value_ok"]:
            value = f"{value[:9]} (want {str(s['value_true'])[:9]})"
        conf = s["confidence"]
        mark = "y" if s["correct"] else "~" if s["truthful"] else "n"
        print(f"    {s['event_id']:<11}{s['document']:<11}{s['label'][:23]:<24}"
              f"{str(s['path_pred'])[:21]:<22}{value[:13]:<14}"
              f"{(f'{conf:.2f}' if isinstance(conf, (int, float)) else '  - '):>5}"
              f"  {mark}")
    print("    y = the payload's headline reading;  ~ = a different correction "
          "the document\n    does assert;  n = wrong about materiality, the "
          "field, or the value.")

    scope = result.get("scope") or []
    if scope:
        graded = [s for s in scope if s.get("scored")]
        print("\nRESOLVE_SCOPE - which variants the correction was applied to")
        print(f"  {'scenario':<14}{'day':>4}  {'truth':<22}{'chosen':<22}"
              f"{'conf':>6}  verdict")
        for s in scope:
            if s.get("error"):
                print(f"  {s['scenario']:<14}{'':>4}  "
                      f"{'run failed':<22}{s['error'][:40]}")
                continue
            verdict = ("not graded - the document leaves the variant open"
                       if not s["scored"] else
                       "exact" if s["exact"] else
                       "too wide" if s["too_wide"] else
                       "too narrow" if s["too_narrow"] else "wrong")
            conf = s.get("confidence")
            print(f"  {s['scenario']:<14}{s['day']:>4}  "
                  f"{(','.join(s['truth']) or '-'):<22}"
                  f"{(','.join(s['picked']) or '-'):<22}"
                  f"{(f'{conf:.2f}' if isinstance(conf, (int, float)) else '  -'):>6}"
                  f"  {verdict}")
        degraded = sorted({node for s in scope for node in s.get("fell_back") or []})
        if degraded:
            print(f"  WARNING: {', '.join(degraded)} answered from the "
                  f"deterministic fallback in at least one scenario.\n"
                  f"  Those rows measure the fallback, not the model. Re-run "
                  f"with a larger EVAL_MIN_INTERVAL.")
        if graded:
            print(f"  graded {len(graded)}: exact "
                  f"{sum(1 for s in graded if s['exact'])}, too wide "
                  f"{sum(1 for s in graded if s['too_wide'])}, too narrow "
                  f"{sum(1 for s in graded if s['too_narrow'])}")
            print(f"  widest reading taken with a narrower one supportable: "
                  f"{sum(1 for s in graded if s['widest_over_supportable'])}"
                  f"/{len(graded)}")

    claims = result.get("claims") or []
    if claims:
        print("\nSCAN_CLAIMS - sentences the corrected values made untrue")
        print(f"  {'scenario':<14}{'copy':>5}{'table':>7}{'flags':>7}"
              f"{'tp':>4}{'fp':>4}{'fn':>4}   precision  recall")
        for c in claims:
            print(f"  {c['scenario']:<14}{c['assets_in_scope']:>5}"
                  f"{c['table_confirms']:>7}{c['flags_returned']:>7}"
                  f"{c['tp']:>4}{c['fp']:>4}{c['fn']:>4}   "
                  f"{_rate(c['precision'])}  {_rate(c['recall'])}")
        tp = sum(c["tp"] for c in claims)
        fp = sum(c["fp"] for c in claims)
        fn = sum(c["fn"] for c in claims)
        overall = rates(tp, fp, fn)
        print(f"  overall        tp {tp} fp {fp} fn {fn}   "
              f"precision {_rate(overall['precision'])}  "
              f"recall {_rate(overall['recall'])}")
        off = sum(c["flags_off_table"] for c in claims)
        bad = sum(c["flags_on_unknown_asset"] for c in claims)
        print(f"  advisory flags naming a claim the table does not hold: {off}"
              f"   ({bad} named copy out of scope and were dropped)")
        print("  read recall with care. The prompt hands the model the same "
              "rule table this is\n  scored against and tells it those are "
              "already checked, then asks for what they\n  cannot catch - so "
              "recall here measures overlap with the deterministic pass, not\n"
              "  value added. The node appends every table finding the model "
              "missed regardless,\n  so a low recall costs a reviewer nothing. "
              "The off-table count is the step's point.")

    cal = result.get("calibration") or {}
    for label, key_name in (("extract", "extract"),
                            ("resolve_scope", "resolve_scope"),
                            ("scan_claims", "scan_claims")):
        curve = cal.get(key_name) or []
        if not curve:
            continue
        scored_on = {"extract": "a true reading of the document",
                     "resolve_scope": "the scope the payload settles",
                     "scan_claims": "a claim the rule table confirms"}[key_name]
        print(f"\nCALIBRATION - {label}: stated confidence vs observed accuracy")
        print(f"  correct here means: {scored_on}")
        print(f"  {'bucket':<14}{'n':>4}{'right':>7}{'observed':>11}")
        for row in curve:
            print(f"  {row['bucket']:<14}{row['n']:>4}{row['correct']:>7}"
                  f"{100 * row['observed']:>10.1f}%")

    gate = result.get("safety_gate") or {}
    if gate.get("safety_documents"):
        print(f"\n  the gate at engine.SAFETY_CONFIDENCE = "
              f"{engine.SAFETY_CONFIDENCE}")
        print(f"    safety-class documents             "
              f"{gate['safety_documents']}")
        print(f"    stated at or above the threshold   "
              f"{gate['clears_threshold']}"
              f"  (of which correct: {gate['clears_and_correct']})")
        print(f"    correct but withheld by the gate   "
              f"{gate['withheld_but_correct']}")
        print(f"    the deterministic fallback asserts "
              f"{gate['fallback_confidence']}, deliberately below it")


def render_comparison(results: dict) -> None:
    if len(results) < 2:
        return
    print(f"\n{'=' * 78}\nPER-MODEL SUMMARY\n{'=' * 78}")
    print(f"  {'model':<26}{'reply':>7}{'path':>7}{'value':>7}{'whole':>7}"
          f"{'mat.P':>8}{'mat.R':>8}{'scope':>7}{'claims R':>10}")
    for name, result in results.items():
        e = result["extract"]
        n = e["answered"] or 1
        m = e["materiality"]
        graded = [s for s in result.get("scope", []) if s.get("scored")]
        exact = sum(1 for s in graded if s["exact"])
        claims = result.get("claims") or []
        recall = rates(sum(c["tp"] for c in claims), 0,
                       sum(c["fn"] for c in claims))["recall"]
        print(f"  {name:<26}{pct(e['answered'], e['documents']):>7}"
              f"{pct(e['path_exact'], n):>7}"
              f"{pct(e['value_exact_coerced'], n):>7}"
              f"{pct(e['whole_reading_correct'], n):>7}"
              f"{_rate(m['precision']):>8}{_rate(m['recall']):>8}"
              f"{pct(exact, len(graded)):>7}{_rate(recall):>10}")
    print("\n  reply = share of documents whose reply the gateway accepted at "
          "all;\n  everything after it is scored over those replies only.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", default="",
                        help="comma-separated model ids to grade")
    parser.add_argument("--all-models", action="store_true",
                        help="grade every chat model the gateway serves")
    parser.add_argument("--only", default="extract,scope,claims",
                        help="touchpoints to run. extract always runs - the "
                             "calibration curve is built from its confidences")
    parser.add_argument("--json", default=str(REPORT_PATH),
                        help="where to write the machine-readable report")
    parser.add_argument("--no-cache", action="store_true",
                        help="bypass the LLM response cache")
    args = parser.parse_args()

    wanted = {part.strip() for part in args.only.split(",") if part.strip()}
    if args.no_cache:
        os.environ["LLM_CACHE"] = "0"

    health = gateway.health()
    if not health.get("ok"):
        raise SystemExit(
            f"the gateway at {gateway.base_url()} is not reachable: "
            f"{health.get('detail')}\nThis script grades a live model; the test "
            "suite is what runs without one.")

    if args.models:
        chosen = [m.strip() for m in args.models.split(",") if m.strip()]
    elif args.all_models:
        chosen = chat_models()
    else:
        chosen = sorted({model_registry.resolve_tier("fast"),
                         model_registry.resolve_tier("reasoning")})

    key = load_key()
    print(f"gateway {gateway.base_url()}   cache "
          f"{'off' if args.no_cache else 'on'}")
    print(f"answer key {KEY_PATH.relative_to(ROOT)}: {len(key)} documents, "
          f"{sum(1 for g in key if g['material'])} material, "
          f"{sum(len(g['rows']) for g in key)} corrected values")
    print(f"grading {len(chosen)} model(s): {', '.join(chosen)}")

    results: dict[str, dict] = {}
    started = time.time()
    for model in chosen:
        pin(model)
        run_id = f"EVAL-{model}"
        print(f"\n... {model}")

        reseed()
        base = baseline_mod.get()
        result: dict = {"extract": run_extract(base, key, model, run_id)}

        if wanted & {"scope", "claims"}:
            scope_rows, claim_rows = run_scenarios(
                key, model, run_id, want_claims="claims" in wanted)
            result["scope"] = scope_rows
            result["claims"] = claim_rows

        result["calibration"] = calibration_for(result)
        result["safety_gate"] = safety_gate(key, result["extract"]["detail"])
        results[model] = result
        render_result(model, result)

    render_comparison(results)

    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "gateway": gateway.base_url(),
        "answer_key": str(KEY_PATH.relative_to(ROOT)),
        "documents": len(key),
        "safety_confidence": engine.SAFETY_CONFIDENCE,
        "fallback_confidence": nodes.FALLBACK_CONFIDENCE,
        "touchpoints": sorted(wanted),
        "elapsed_seconds": round(time.time() - started, 1),
        "min_interval_seconds": MIN_INTERVAL,
        "rate_limit_backoffs": _throttle["waits"],
        # Carried in the artefact so a number read six months from now arrives
        # with the reasons it is not what it looks like.
        "notes": [
            "Scored over the documents whose reply the gateway accepted. A "
            "refused reply routes to the deterministic fallback and is counted "
            "as a contract failure, not a misread field.",
            "whole_reading_with_fallback is arithmetic, not evidence: the "
            "fallback reads the same payload the answer key was written from, "
            "so it is right on every document by construction. This key can "
            "grade the model and cannot grade the fallback.",
            "scan_claims recall is measured against the same rule table the "
            "prompt tells the model is already checked, so it measures overlap "
            "with the deterministic pass rather than value added. The node "
            "appends every missed table finding regardless.",
            "The scope truth is the union of the corrections the tape has "
            "delivered for that product by that day, because a case is a "
            "product. Where the newest correction leaves the variant open - the "
            "day-28 inject - the run is reported and not graded.",
        ],
        "models": results,
    }
    out = Path(args.json)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True, default=str),
                   encoding="utf-8")
    print(f"\nreport written to {out}")
    print(f"{save_cache()} cached responses carried in "
          f"{CACHE_DB.relative_to(ROOT)} - a repeat run is free")
    if _throttle["waits"]:
        print(f"backed off {_throttle['waits']} time(s) for "
              f"{_throttle['seconds']:.0f}s of provider rate limiting")

    db.close_all()
    graph_build.reset_graph()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
