import { useMemo } from "react";
import { fmt } from "../api";
import type { CatalogState, SCEvent } from "../api";
import { ArtQuietFeed } from "../art/illustrations";
import { IconJump } from "../icons";
import { Badge, Button, EmptyState, Panel, Tooltip, cn } from "../ui";
import type { BadgeTone } from "../ui";
import { buildVocab } from "./vocab";
import type { Vocab } from "./vocab";

/* The live event feed.
 *
 * What arrived, as a sentence rather than a payload. The ids stay on the row
 * because a reviewer searches by them.
 *
 * **It sits on the Ingest Fabric, beside the graph the arrivals reach.** It
 * spent a while next to the replay transport instead, on the argument that the
 * tape releases these rows and the tape is what you reach for when one needs
 * explaining. That was true and it was the smaller half. The question a person
 * actually has on reading a row is *what does this touch* - and the answer is
 * the picture next to it, not the transport that let it through. The transport
 * is in the status strip on every screen anyway, so nothing was lost by
 * moving.
 *
 * Which is also what makes the feed a working surface rather than a ticker.
 * Two controls, and they are different questions:
 *
 *   the row      trace this event's subject on the map. "What does this
 *                reach?", answered by the API's own lineage walk.
 *   the jump     land the tape on this event. "Show me that moment again",
 *                answered by rewinding the clock to it.
 */

/** What each kind of event on the tape actually is, in a word. The raw enum
 *  stays in the row's tooltip - it is what the engine logs and filters on. */
const EVENT_LABEL: Record<string, string> = {
  SUPPLIER_FEED: "feed",
  SPEC_DOC: "document",
  CHANNEL_STATUS: "channel",
  CATALOG_UPDATE: "catalog",
  PUBLISH_TELEMETRY: "published",
  COMMS: "email",
};

export function EventFeed({
  events, catalog, busy, onReplay, onTrace, selected, maxHeight = "420px",
}: {
  events: SCEvent[];
  catalog: CatalogState | null;
  busy: boolean;
  /** Drive the tape. The feed uses it to land the clock on a named event. */
  onReplay: (body: { action: string; steps?: number; speed?: number;
                     to_seq?: number }) => void;
  /** Trace this event's subject on the map beside the feed. */
  onTrace?: (entityId: string) => void;
  /** What the map is tracing now, so the row that put it there says so. */
  selected?: string | null;
  /** The feed shares a rail with the queue above it, and a rail is a different
   *  shape from a tab. */
  maxHeight?: string;
}) {
  const vocab = useMemo(() => buildVocab(catalog), [catalog]);

  return (
    <Panel
      title="Live event feed"
      flush
      subtitle={events.length ? `${events.length} released` : undefined}
    >
      {events.length === 0 ? (
        <EmptyState art={<ArtQuietFeed />} title="Nothing has arrived yet">
          Start or step the replay from the transport in the status bar below —
          the tape releases one supplier document at a time, which is how the
          correction gets narrated. Whatever a supplier sends through a portal
          lands here too, the moment it is sent.
        </EmptyState>
      ) : (
        <div className="overflow-y-auto" style={{ maxHeight }}>
          {events.map((e, i) => {
            const sentence = describe(e, vocab);
            const subject = subjectId(e);
            const tracing = !!subject && selected === subject;
            return (
              <div
                key={e.id}
                // Only the newest few animate in. Animating all 200 on every
                // arrival would restart the whole list.
                className={cn(
                  "flex items-baseline gap-2 border-b border-subtle px-3 py-1.5",
                  "transition-colors hover:bg-hover",
                  tracing && "bg-accent-soft",
                  i < 3 && "animate-slide-in"
                )}
              >
                <span className="shrink-0 font-mono text-xs text-faint tabular-nums">
                  {fmt.stamp(e.ts)}
                </span>
                <Badge tone={eventTone(e)}>
                  {EVENT_LABEL[e.type] ?? e.type}
                </Badge>
                <Tooltip
                  content={
                    <span className="block">
                      <span className="block">{sentence}</span>
                      {onTrace && subject && (
                        <span className="mt-1 block text-2xs text-accent-text">
                          Click to trace {subject} on the map
                        </span>
                      )}
                      <span className="mt-1 block font-mono text-2xs text-faint">
                        {idLine(e)}
                      </span>
                    </span>
                  }
                >
                  {/* The sentence is the trace control, not the whole row: the
                      row already ends in a button, and one cannot nest. */}
                  {onTrace && subject ? (
                    <button
                      type="button"
                      onClick={() => onTrace(subject)}
                      className={cn(
                        "min-w-0 flex-1 truncate text-left text-sm",
                        "hover:text-accent-text focus-visible:text-accent-text",
                        tracing && "text-accent-text"
                      )}
                    >
                      {sentence}
                    </button>
                  ) : (
                    <span className="min-w-0 flex-1 truncate text-sm">
                      {sentence}
                    </span>
                  )}
                </Tooltip>
                {subject && (
                  <span className="shrink-0 font-mono text-2xs text-faint">
                    {subject}
                  </span>
                )}
                {/* The tape's only precise control. JUMP with a target seq
                    rewinds the cursor, so the clock, the catalog and this feed
                    all return to the instant that document landed - the same
                    beat, twice, identically. */}
                <Tooltip
                  content={`Land the tape on this event (seq ${e.seq}). The clock returns to this instant and everything after it goes back to unreleased.`}
                >
                  <Button
                    tone="ghost"
                    size="xs"
                    iconOnly
                    disabled={busy}
                    aria-label={`Land the tape on ${e.id}`}
                    onClick={() => onReplay({ action: "JUMP", to_seq: e.seq })}
                    icon={<IconJump size={12} />}
                    className="shrink-0 self-center text-faint hover:text-accent-text"
                  />
                </Tooltip>
              </div>
            );
          })}
        </div>
      )}
      {events.length > 0 && (
        <p className="border-t border-subtle px-3 py-2 text-xs leading-relaxed text-faint">
          {onTrace
            ? "Click a row to trace what that event reaches. The control at "
              + "the end of it lands the tape on that document instead — the "
              + "clock returns to that instant and everything after it goes "
              + "back to unreleased, which is how the same beat gets narrated "
              + "twice off exactly the same evidence."
            : "The control at the end of a row lands the tape on that document "
              + "rather than on the generic inject — the clock returns to that "
              + "instant, and everything after it goes back to unreleased."}
        </p>
      )}
    </Panel>
  );
}

/* --- the feed, in sentences ------------------------------------------------ */

/** "45 W", "peanuts", "38". */
function withUnit(value: unknown, unit: unknown): string {
  const text = fmt.value(value);
  return typeof unit === "string" && unit ? `${text} ${unit}` : text;
}

/** "rated power 45 → 65 W" out of a change row or a flat payload. */
function changeClause(row: Record<string, unknown>, v: Vocab): string {
  const label = v.attr(row.attribute_path ?? row.path) || "the value";
  const to = withUnit(row.new_value, row.unit);
  if (row.old_value === undefined || row.old_value === null) {
    return `${label} now ${to}`;
  }
  return `${label} ${withUnit(row.old_value, row.unit)} → ${to}`;
}

/** Who the document says it is about - and, in the case that drives the whole
 *  demo, that it does not say. */
function scopeClause(p: Record<string, unknown>, v: Vocab): string {
  const entities = (Array.isArray(p.entities) ? p.entities : [])
    .filter((x): x is string => typeof x === "string")
    .map((id) => v.name(id));
  const product = v.name(p.product);
  switch (String(p.applies_to ?? "")) {
    case "UNCLEAR":
      return product
        ? `on ${product}, without saying which variant`
        : "without saying which variant";
    case "VARIANT":
      return entities.length ? `for ${entities.join(" and ")}` : "for one variant";
    case "PRODUCT":
      return product ? `at product level on ${product}` : "at product level";
    case "ALL":
      return product ? `for every variant of ${product}` : "for every variant";
    default:
      return entities.length ? `on ${entities.join(" and ")}` : "";
  }
}

const join = (head: string, parts: string[]) => {
  const tail = parts.filter(Boolean).join(", ");
  return tail ? `${head} — ${tail}.` : `${head}.`;
};

/** One line of the feed, as a sentence a person would say.
 *
 * The tape carries six kinds of event and each is a different sort of news: a
 * routine price row and a spec sheet that moves an allergen must not read the
 * same way, and neither should read as a dumped payload.
 */
export function describe(e: SCEvent, v: Vocab): string {
  const p = (e.payload ?? {}) as Record<string, unknown>;
  const str = (k: string) => (typeof p[k] === "string" ? (p[k] as string) : "");

  switch (e.type) {
    case "SUPPLIER_FEED": {
      const who = v.name(p.supplier) || "A supplier";
      const what = v.name(p.entity_id) || "the catalog";
      switch (str("kind")) {
        case "STOCK":
          return `${who} reported ${fmt.count(Number(p.on_hand ?? 0))} in stock for ${what}.`;
        case "PRICE":
          return `${who} repriced ${what} at ${fmt.value(p.price)} ${str("currency")}`.trim() + ".";
        case "ATTRIBUTE_CONFIRM":
          return `${who} ${p.certified ? "certified" : "confirmed"} ${
            v.attr(p.path)} unchanged on ${what} — ${withUnit(p.value, p.unit)}.`;
        case "ATTRIBUTE":
          return p.is_correction
            ? `${who} corrected ${v.attr(p.path)} on ${what} to ${withUnit(p.value, p.unit)}.`
            : `${who} sent ${v.attr(p.path)} for ${what} — ${withUnit(p.value, p.unit)}.`;
        default:
          return `${who} sent a feed row for ${what}.`;
      }
    }

    case "SPEC_DOC": {
      const who = v.name(p.supplier) || "A supplier";
      const version = str("doc_version");
      const head = `${who} sent ${version ? `revision ${version} of ` : ""}${
        str("doc_id") || "a document"}`;
      const changes = (Array.isArray(p.changes) ? p.changes : [])
        .filter((c): c is Record<string, unknown> => Boolean(c) && typeof c === "object");
      const parts: string[] = [];
      if (changes.length === 1) parts.push(changeClause(changes[0], v));
      else if (changes.length > 1) parts.push(`${changes.length} values move`);
      else if (p.new_value !== undefined) parts.push(changeClause(p, v));
      else if (p.zero_delta) parts.push("republished with nothing changed");
      if (str("summary")) parts.push(str("summary"));
      if (p.provisional) parts.push("treat as provisional");
      parts.push(scopeClause(p, v));
      return join(head, parts);
    }

    case "CHANNEL_STATUS": {
      const channel = v.name(p.channel_id) || "A channel";
      const what = v.name(p.variant_id) || v.name(p.product) || "a listing";
      const code = str("code");
      switch (str("status")) {
        case "REJECTED":
          return join(
            `${channel} rejected the ${what} feed${code ? ` (${code})` : ""}`,
            [str("detail")]
          );
        case "ACCEPTED":
          return `${channel} accepted the ${what} feed.`;
        default:
          return join(
            `${channel} reported ${str("status").toLowerCase()} on ${what}`,
            [code, str("detail")]
          );
      }
    }

    case "PUBLISH_TELEMETRY": {
      const channel = v.name(p.channel_id) || "A channel";
      const what = v.name(p.variant_id) || "a listing";
      if (str("status") && str("status") !== "OK") {
        return `${channel} reported ${str("status").toLowerCase()} serving ${what}.`;
      }
      return `${channel} served ${fmt.count(Number(p.impressions ?? 0))} views of ${what}.`;
    }

    case "CATALOG_UPDATE": {
      const doc = `${str("doc_id")}${str("doc_version") ? ` ${str("doc_version")}` : ""}`;
      const status = str("status").toLowerCase();
      const reason = str("reason").replace(/_/g, " ");
      return join(`${doc || "A document"} is now ${status || "changed"}`, [reason]);
    }

    case "COMMS": {
      const who = v.name(p.supplier) || str("from") || "Someone";
      const parts: string[] = [];
      if (p.resolves_issue) parts.push("this clears the earlier notice");
      else if (p.provisional) parts.push("treat as provisional");
      else if (str("summary")) parts.push(str("summary"));
      return join(`${who} wrote: “${str("subject") || "no subject"}”`, parts);
    }

    default:
      return JSON.stringify(p).slice(0, 140);
  }
}

/** The tone of the news, not the tone of the type. A rejection is red whatever
 *  carried it; a stock row is grey whatever it says. */
function eventTone(e: SCEvent): BadgeTone {
  const p = (e.payload ?? {}) as Record<string, unknown>;
  switch (e.type) {
    case "CHANNEL_STATUS":
      return p.status === "REJECTED" ? "danger" : "neutral";
    case "SPEC_DOC":
      return p.is_correction ? "warn" : "info";
    case "CATALOG_UPDATE":
      return "warn";
    case "COMMS":
      return p.material_hint ? "info" : "neutral";
    case "SUPPLIER_FEED":
      return p.is_correction ? "warn" : "neutral";
    default:
      return "neutral";
  }
}

const SUBJECT_KEYS = [
  "listing_id", "entity_id", "variant_id", "product", "doc_id", "channel_id",
];

/** The one id worth keeping on the row. A reviewer searching for LST-11 has to
 *  be able to find it without opening anything. */
function subjectId(e: SCEvent): string {
  const p = (e.payload ?? {}) as Record<string, unknown>;
  for (const key of SUBJECT_KEYS) {
    const value = p[key];
    if (typeof value === "string" && value) return value;
  }
  const entities = Array.isArray(p.entities) ? p.entities : [];
  const first = entities.find((x) => typeof x === "string");
  return typeof first === "string" ? first : "";
}

const ID_KEYS = [
  "doc_id", "doc_version", "supplier", "product", "entity_id", "variant_id",
  "listing_id", "channel_id", "path", "attribute_path", "code", "field",
];

/** Every identifier on the event, for the tooltip. The sentence is for reading;
 *  this is for looking something up afterwards. */
function idLine(e: SCEvent): string {
  const p = (e.payload ?? {}) as Record<string, unknown>;
  const bits = [e.type, e.id];
  for (const key of ID_KEYS) {
    const value = p[key];
    if (typeof value === "string" && value) bits.push(value);
  }
  for (const entity of Array.isArray(p.entities) ? p.entities : []) {
    if (typeof entity === "string") bits.push(entity);
  }
  return Array.from(new Set(bits)).join(" · ");
}
