import { useState } from "react";
import type { MediaSlot } from "../api";
import { Badge, Skeleton, Tooltip, cn } from "../ui";

/* The imagery a product has, and the imagery it is missing.
 *
 * Until now the staging page rendered the *role* of each asset as a grey pill
 * and dropped the uri the server had been sending all along - so the last
 * surface before publication showed the words "hero, in situ, detail" where
 * the photography goes, and a product missing its ingredient panel looked
 * exactly like one that had it.
 *
 * Two states matter and they are drawn differently on purpose:
 *
 *   held         the asset arrived. Shown.
 *   required     the category cannot launch without this role and nothing has
 *                arrived. Drawn as a gap, naming the system that owes it -
 *                because "the imaging system has not delivered an ingredient
 *                panel" is something a person can chase and "media incomplete"
 *                is not.
 *
 * A role that is neither is not drawn at all. Every product could be missing a
 * dozen roles no rule wants, and a strip full of shrugs is a strip nobody
 * reads.
 *
 * The `onError` fallback matters as much as the happy path. An `<img>` whose
 * source 404s renders as a browser glyph that says "broken", and a reviewer
 * cannot tell a supplier who never sent a photograph from a page that is
 * malfunctioning. So a failed load falls back to the same honest tile as an
 * asset that was never delivered.
 */

const ROLE_WORDS: Record<string, string> = {
  HERO: "hero",
  IN_SITU: "in situ",
  PACK_FRONT: "pack front",
  INGREDIENT_PANEL: "ingredient panel",
  DETAIL: "detail",
};

export const roleWords = (role: string): string =>
  ROLE_WORDS[role] ?? role.toLowerCase().replace(/_/g, " ");

export function MediaStrip({
  media, loading, compact,
}: {
  media?: MediaSlot[] | null;
  loading?: boolean;
  /** Smaller tiles, for the readiness panel rather than the staging page. */
  compact?: boolean;
}) {
  if (loading) {
    return (
      <div className="flex flex-wrap gap-2" aria-hidden="true">
        {[0, 1, 2].map((i) => (
          <Skeleton key={i} className={compact ? "h-16 w-16" : "h-28 w-28"}
                    rounded="md" />
        ))}
      </div>
    );
  }

  const shown = (media ?? []).filter((slot) => slot.held || slot.required);
  if (shown.length === 0) return null;

  const missing = shown.filter((s) => !s.held).length;

  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex flex-wrap items-center gap-2">
        {shown.map((slot) => (
          <MediaTile key={slot.role} slot={slot} compact={compact} />
        ))}
      </div>
      {missing > 0 && (
        <p className="text-2xs text-warn-text">
          {missing} required image{missing === 1 ? "" : "s"} not delivered.
          Nothing here is broken — the asset has not arrived.
        </p>
      )}
    </div>
  );
}

function MediaTile({ slot, compact }: { slot: MediaSlot; compact?: boolean }) {
  // A load that fails is treated exactly like an absence, because to the
  // person deciding whether to launch it is one.
  const [failed, setFailed] = useState(false);
  const size = compact ? "h-16 w-16" : "h-28 w-28";
  const present = slot.held && slot.uri && !failed;

  return (
    <figure className="flex flex-col items-center gap-1">
      {present ? (
        <img
          src={slot.uri as string}
          alt={slot.alt_text ?? roleWords(slot.role)}
          loading="lazy"
          onError={() => setFailed(true)}
          className={cn(
            size,
            "rounded-md border border-subtle bg-sunken object-cover",
          )}
        />
      ) : (
        <Tooltip
          content={
            slot.system
              ? `${slot.system} has not delivered ${roleWords(slot.role)} for this product`
              : `no ${roleWords(slot.role)} has been delivered, and no system is recorded as owing it`
          }
        >
          <div
            className={cn(
              size,
              "flex flex-col items-center justify-center gap-1 rounded-md",
              "border border-dashed border-warn-border bg-warn-soft/40",
              "px-1 text-center",
            )}
          >
            <GapGlyph />
            <span className="text-2xs leading-tight text-warn-text">
              not delivered
            </span>
          </div>
        </Tooltip>
      )}
      <figcaption className="flex items-center gap-1 text-2xs text-faint">
        {roleWords(slot.role)}
        {slot.required && !present && <Badge tone="warn">required</Badge>}
      </figcaption>
    </figure>
  );
}

/** An empty frame. Deliberately not a warning triangle - nothing has gone
 *  wrong here, something has simply not turned up yet. */
function GapGlyph() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none"
         aria-hidden="true" className="text-warn-text opacity-70">
      <rect x="3.5" y="5" width="17" height="14" rx="2"
            stroke="currentColor" strokeWidth="1.4" strokeDasharray="3 2.5" />
      <path d="M7.5 15.5 11 12l2.5 2.5L16 12.5l2.5 3" stroke="currentColor"
            strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
