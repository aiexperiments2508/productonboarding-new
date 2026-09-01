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
 * It sits beside the replay transport rather than on the Ingest Fabric, which
 * is where it used to be. The tape is what releases these rows and the tape is
 * what a reader reaches for when one of them needs explaining, so the feed and
 * the controls that drive it are one thing; the fabric is the graph.
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

export function EventFeed({ events, catalog, busy, onReplay }: {
  events: SCEvent[];
  catalog: CatalogState | null;
  busy: boolean;
  /** Drive the tape. The feed uses it to land the clock on a named event. */
  onReplay: (body: { action: string; steps?: number; speed?: number;
                     to_seq?: number }) => void;
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
          Start or step the replay from the transport above — the tape releases
          one supplier document at a time, which is how the correction gets
          narrated.
        </EmptyState>
      ) : (
        <div className="max-h-[420px] overflow-y-auto">
          {events.map((e, i) => {
            const sentence = describe(e, vocab);
            const subject = subjectId(e);
            return (
              <div
                key={e.id}
                // Only the newest few animate in. Animating all 200 on every
                // arrival would restart the whole list.
                className={cn(
                  "flex items-baseline gap-2 border-b border-subtle px-3 py-1.5",
                  "transition-colors hover:bg-hover",
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
                      <span className="mt-1 block font-mono text-2xs text-faint">
                        {idLine(e)}
                      </span>
                    </span>
                  }
                >
                  <span className="min-w-0 flex-1 truncate text-sm">
                    {sentence}
                  </span>
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
          The control at the end of a row lands the tape on that document rather
          than on the generic inject — the clock returns to that instant, and
          everything after it goes back to unreleased. It is how the same beat
          gets narrated twice off exactly the same evidence.
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
