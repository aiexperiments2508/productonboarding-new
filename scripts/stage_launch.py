"""Put two products on sale, so a late change has something to be late for.

    python scripts/stage_launch.py            two products live across the estate
    python scripts/stage_launch.py --press    and the print run inside its freeze
    python scripts/stage_launch.py --inject   and deliver the late change directly

The demonstration needs a state the seed pack deliberately does not ship: every
listing in the pack is PREPARED, because the pack describes a catalog in the
middle of being prepared and nothing in it has launched. That is right for the
correction story the tape tells. It is wrong for this one, which is about a
correction arriving *after* the launch.

So this puts VAR-05A and VAR-04A on sale across everything that carries them,
and leaves the print channel genuinely inside its freeze window rather than
incidentally so.

``--inject`` is a fallback and is not the intended demonstration. The point of
the vendor portal is that a person sends the change from another application
while the room watches; this flag exists for a rehearsal with no second screen,
and for the tests.

**PRD-01 is not touched.** It carries the existing arc - the ambiguous power
correction the tape delivers - and a rehearsal that disturbed it would break the
demonstration this one sits beside.
"""

from __future__ import annotations

import argparse
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sc import bootstrap  # noqa: E402

#: The two products, and why each one is here.
#:
#: VAR-05A is regulated food carrying a real allergen declaration that its own
#: copy quotes on six channels, one of which cannot be recalled. A change to it
#: is safety-class, which forces mandatory review *and* forces the redaction
#: path - and the print run turns that into an erratum rather than a fix.
#:
#: VAR-04A is an ordinary appliance specification. It is here because a
#: demonstration where every correction is an allergen teaches that the system
#: only works on allergens.
STAGED = ("VAR-05A", "VAR-04A")

#: The late changes, if they are delivered from here rather than from the
#: portal. Written to match what the portal sends, so a rehearsal and a live
#: demonstration put the system in the same place.
LATE = {
    "VAR-05A": {
        "supplier": "SUP-02",
        "system": "supplier-portal",
        "path": "food.allergens.may_contain",
        "value": ["milk", "peanuts"],
        "note": ("Peanut handling introduced on the packing line from the next "
                 "production run. The may-contain statement must be updated "
                 "before the next despatch."),
    },
    "VAR-04A": {
        "supplier": "SUP-04",
        "system": "supplier-pim",
        "path": "specs.power_w",
        "value": 2200,
        "note": ("Element specification revised from 3000 W to 2200 W for the "
                 "current production batch."),
    },
}


def stage(press: bool = False) -> dict:
    """Put the staged variants on sale, and report what moved."""
    from sc.contracts import Provenance, ProvenanceKind
    from sc.replay import tape
    from sc.state import baseline as baseline_mod
    from sc.state import overlay as overlay_mod
    from sc.state import store

    base = baseline_mod.get()
    now = tape.sim_now()
    provenance = Provenance(kind=ProvenanceKind.RECORDED, source_id="STAGE",
                            system="CHANNEL_GATEWAY",
                            note="staged for the launch demonstration")

    live, frozen = [], []
    for variant_id in STAGED:
        for listing_id in base.listings_of.get(variant_id, []):
            listing = base.listings[listing_id]
            channel = base.channels[listing.channel_id]

            # Facts are append-only, so a second run would stack duplicates.
            # Skipped rather than guarded with a key, because the check is one
            # read and the intent - "make sure this is live" - is idempotent by
            # nature rather than by bookkeeping.
            held = store.get("listing", listing_id, overlay_mod.ATTR_STATUS,
                             now, now)
            if getattr(held, "value", None) != "LIVE":
                store.record("listing", listing_id, overlay_mod.ATTR_STATUS,
                             "LIVE", valid_from=now, recorded_at=now,
                             provenance=provenance)
                live.append(listing_id)

            version = store.get("listing", listing_id,
                                overlay_mod.ATTR_PUBLISHED_VERSION, now, now)
            if version is None:
                store.record("listing", listing_id,
                             overlay_mod.ATTR_PUBLISHED_VERSION, "v1",
                             valid_from=now, recorded_at=now,
                             provenance=provenance)

            # A print channel is only interesting inside its window. Dating the
            # press run backwards from the current instant puts it there on
            # purpose rather than by luck of when the clock happens to be.
            if press and channel.freeze_days:
                pressed = now - timedelta(days=max(channel.freeze_days - 2, 1))
                store.record("listing", listing_id,
                             overlay_mod.ATTR_PUBLISHED_VERSION, "v1",
                             valid_from=pressed, recorded_at=pressed,
                             provenance=provenance)
                frozen.append(listing_id)

    return {"live": sorted(set(live)), "frozen": sorted(set(frozen)),
            "as_of": now.isoformat()}


def inject() -> list[dict]:
    """Deliver the late changes as if a supplier had sent them.

    Through the same intake the portal uses, so the events, the arrivals, the
    submission rows and the document versions are identical to a real one.
    There is deliberately no separate code path for a scripted change: a
    rehearsal that exercised different code would be rehearsing something else.
    """
    from sc.estate import intake

    results = []
    for variant_id, change in LATE.items():
        results.append(intake.submit_specification_change(
            supplier=change["supplier"], system_id=change["system"],
            entity_id=variant_id, attribute_path=change["path"],
            new_value=change["value"], note=change["note"],
            idempotency_key=f"stage:{variant_id}:{change['path']}"))
    return results


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Stage two launched products for the late-change demo.")
    parser.add_argument("--press", action="store_true",
                        help="put the print listing inside its freeze window")
    parser.add_argument("--inject", action="store_true",
                        help="deliver the late change without the vendor portal")
    args = parser.parse_args()

    bootstrap.load_env()
    bootstrap.ensure_ready()

    from sc.replay import ingest, tape

    # Same opening as prepare_demo: release the recorded flight to its finale,
    # so PRD-01's arc is live and undisturbed beside this one.
    released = tape.jump_to(tape.inject_seq() + 12)
    ingest.ingest(released)

    result = stage(press=args.press)
    print(f"  {len(result['live'])} listing(s) put on sale")
    if result["frozen"]:
        print(f"  {len(result['frozen'])} inside a freeze window "
              f"(cannot be recalled)")

    if args.inject:
        for row in inject():
            if row.get("accepted"):
                print(f"  late change delivered: {row['doc_ref']} "
                      f"({row['submission_id']})")
            else:
                print(f"  ! refused: {row.get('error')}")
    else:
        print("  no late change delivered - send it from the Vendor Portal")

    from sc.lifecycle import board

    lanes = board.build(limit=400)["totals"]
    print("\n  lifecycle: " + ", ".join(f"{k.lower().replace('_', ' ')} {v}"
                                        for k, v in lanes.items() if v))
    print(f"  simulated clock: {result['as_of']}")


if __name__ == "__main__":
    main()
