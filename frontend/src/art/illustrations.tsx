/* Empty-state illustrations.
 *
 * An empty panel is where a reviewer is most likely to think the app is broken.
 * Each of these draws the thing that is *missing*, in the idle state it would
 * be in, so the panel reads as waiting rather than failed - and each one hints
 * at the action that fills it.
 *
 * The vocabulary is the factory's own, so a panel and its picture agree: a
 * supplier document is a page, a variant is a circle, a channel is a tile, and
 * a line between them is a derivation - the path a corrected value travels to
 * reach published content.
 *
 * Shared constraints so they read as one family:
 *   - 160x104 viewBox, line art, stroke 1.5, no fills except node bodies
 *   - semantic tokens only, so they invert correctly with the theme
 *   - one slow idle loop each; nothing that pulls the eye off the page
 */

const FRAME = "mx-auto block";
const W = 160;
const H = 104;

function Art({ children, label }: { children: React.ReactNode; label: string }) {
  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      width={W}
      height={H}
      fill="none"
      className={FRAME}
      role="img"
      aria-label={label}
    >
      {children}
    </svg>
  );
}

/** A supplier document: a page with a folded corner and three lines of prose.
 *  Reused wherever the source of a correction has to appear. */
function Page({ x, y }: { x: number; y: number }) {
  return (
    <g transform={`translate(${x} ${y})`}>
      <path
        d="M0 0h20l10 10v36H0z"
        fill="var(--surface-sunken)"
        stroke="var(--border-strong)"
        strokeWidth="1.5"
        strokeLinejoin="round"
      />
      <path d="M20 0v10h10" stroke="var(--border-strong)" strokeWidth="1.5"
            strokeLinejoin="round" />
      <path d="M7 21h16M7 28h16M7 35h9" stroke="var(--border-strong)"
            strokeWidth="1.5" strokeLinecap="round" />
    </g>
  );
}

/* --- no correction worked yet --------------------------------------------- */
/* A document that has arrived, a variant it names, and the three channels
   built on it. Nothing has been asked of any of it; the pulse travels the
   derivation to say the lineage is there and unused. */
export function ArtNoRun() {
  const route = "M48 49H118";
  return (
    <Art label="A supplier document and the content derived from it, at rest">
      <Page x={16} y={26} />

      {[29, 49, 69].map((y) => (
        <path
          key={y}
          d={y === 49 ? "M94 49h24" : `M94 49C106 49 106 ${y} 118 ${y}`}
          stroke="var(--border-strong)"
          strokeWidth="1.5"
          strokeDasharray="4 4"
        />
      ))}
      <path d="M48 49h30" stroke="var(--border-strong)" strokeWidth="1.5"
            strokeDasharray="4 4" />

      <circle cx="86" cy="49" r="8" fill="var(--surface-sunken)"
              stroke="var(--border-strong)" strokeWidth="1.5" />
      {[22, 42, 62].map((y) => (
        <rect key={y} x="118" y={y} width="16" height="14" rx="3"
              fill="var(--surface-sunken)" stroke="var(--border-strong)"
              strokeWidth="1.5" />
      ))}

      <circle r="3" fill="var(--accent-solid)" opacity="0.9">
        <animateMotion dur="4.2s" repeatCount="indefinite" path={route} />
        <animate attributeName="opacity" values="0;0.9;0.9;0"
                 keyTimes="0;0.1;0.9;1" dur="4.2s" repeatCount="indefinite" />
      </circle>
    </Art>
  );
}

/* --- nothing awaiting a decision ------------------------------------------ */
/* A cleared review tray: the change diff a reviewer signs, old value to new,
   with nothing left on it. The check breathes rather than blinks - this is a
   settled state, not a notification. */
export function ArtNoDecision() {
  return (
    <Art label="No correction is waiting on a reviewer">
      <rect x="34" y="24" width="80" height="58" rx="6"
            fill="var(--surface-sunken)" stroke="var(--border-strong)"
            strokeWidth="1.5" />
      {[
        { y: 40, from: 16, to: 20 },
        { y: 52, from: 12, to: 24 },
        { y: 64, from: 20, to: 14 },
      ].map((row) => (
        <g key={row.y} stroke="var(--border-strong)" strokeWidth="1.5"
           strokeLinecap="round">
          <path d={`M46 ${row.y}h${row.from}`} />
          <path d={`M${46 + row.from + 6} ${row.y}h6`} />
          <path d={`M${46 + row.from + 9} ${row.y - 2.5}l2.5 2.5-2.5 2.5`}
                strokeLinejoin="round" />
          <path d={`M${46 + row.from + 16} ${row.y}h${row.to}`} />
        </g>
      ))}
      <g className="sc-breathe">
        <circle cx="112" cy="70" r="14" fill="var(--surface-raised)"
                stroke="var(--ok-solid)" strokeWidth="1.8" />
        <path d="M105.5 70.5 110 75 118.5 65.5" stroke="var(--ok-solid)"
              strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      </g>
    </Art>
  );
}

/* --- no resolutions validated --------------------------------------------- */
/* An empty frontier, axes drawn and waiting. The ghost points fade in and out
   in sequence to suggest the candidate readings that will land here once the
   validator has priced them. */
export function ArtNoOptions() {
  const points = [
    { x: 52, y: 62 }, { x: 74, y: 48 }, { x: 96, y: 54 }, { x: 116, y: 36 },
  ];
  return (
    <Art label="No candidate resolutions have been validated yet">
      <path d="M36 20v62h92" stroke="var(--viz-axis)" strokeWidth="1.5"
            strokeLinecap="round" />
      {[34, 52, 70].map((y) => (
        <path key={y} d={`M36 ${y}h92`} stroke="var(--viz-grid)"
              strokeWidth="1" strokeDasharray="2 4" />
      ))}
      {points.map((p, i) => (
        <circle key={i} cx={p.x} cy={p.y} r="4.5"
                fill="var(--accent-solid)" opacity="0">
          <animate attributeName="opacity" values="0;0.75;0.75;0"
                   keyTimes="0;0.2;0.7;1" dur="3.6s"
                   begin={`${i * 0.32}s`} repeatCount="indefinite" />
        </circle>
      ))}
    </Art>
  );
}

/* --- the tape has released nothing ---------------------------------------- */
/* The event tape with its cursor still at zero: every document is on the reel
   and none of them has been let through. The panel reads as loaded and
   waiting, which is exactly what it is, and the cursor is the control that
   fills it. */
export function ArtQuietFeed() {
  return (
    <Art label="No events released from the tape yet">
      <path d="M20 64h120" stroke="var(--border-strong)" strokeWidth="1.6"
            strokeLinecap="round" />
      {[36, 52, 68, 84, 100, 116, 132].map((x) => (
        <g key={x}>
          <rect x={x} y="44" width="8" height="8" rx="1.5"
                fill="var(--surface-sunken)" stroke="var(--border-strong)"
                strokeWidth="1.5" />
          <path d={`M${x + 4} 52v12`} stroke="var(--viz-grid)" strokeWidth="1" />
        </g>
      ))}
      <g className="sc-breathe">
        <path d="M26 40v32" stroke="var(--accent-solid)" strokeWidth="1.8"
              strokeLinecap="round" />
        <path d="M26 56l7 4-7 4z" fill="var(--accent-solid)" />
      </g>
    </Art>
  );
}

/* --- nothing retrieved ---------------------------------------------------- */
/* A page from the reference library and the query that did not find it. */
export function ArtNoEvidence() {
  return (
    <Art label="Nothing retrieved from the reference library">
      <Page x={44} y={20} />
      <g className="sc-breathe">
        <circle cx="104" cy="62" r="15" fill="none"
                stroke="var(--accent-solid)" strokeWidth="1.8" />
        <path d="M115 73 126 84" stroke="var(--accent-solid)" strokeWidth="2"
              strokeLinecap="round" />
      </g>
    </Art>
  );
}

/* --- the catalog is clean ------------------------------------------------- */
/* One variant publishing cleanly to three channels. This is the only
   illustration that shows motion as the *good* state, so it uses the same flow
   overlay the catalog map draws a live listing with. */
export function ArtAllClear() {
  const routes = [
    "M34 52C70 52 84 32 120 32",
    "M34 52h86",
    "M34 52C70 52 84 72 120 72",
  ];
  return (
    <Art label="No correction is in force; every listing is publishing">
      {routes.map((d, i) => (
        <g key={d}>
          <path d={d} stroke="var(--viz-edge)" strokeWidth="1.5" />
          <path
            d={d}
            stroke="var(--ok-solid)"
            strokeWidth="1.8"
            strokeLinecap="round"
            className="sc-flow"
            style={{ animationDelay: `${i * 0.35}s` }}
          />
        </g>
      ))}
      <circle cx="26" cy="52" r="8" fill="var(--surface-raised)"
              stroke="var(--ok-solid)" strokeWidth="1.6" />
      {[26, 46, 66].map((y) => (
        <rect key={y} x="120" y={y} width="16" height="12" rx="3"
              fill="var(--surface-raised)" stroke="var(--ok-solid)"
              strokeWidth="1.6" />
      ))}
    </Art>
  );
}

/* --- something went wrong ------------------------------------------------- */
/* A derivation that could not be walked: the link between two nodes is broken
   rather than merely empty, which is the distinction every other state here
   exists to avoid implying. */
export function ArtBroken() {
  return (
    <Art label="Could not load">
      <path d="M24 52h44" stroke="var(--border-strong)" strokeWidth="1.6"
            strokeLinecap="round" />
      <path d="M92 52h44" stroke="var(--border-strong)" strokeWidth="1.6"
            strokeLinecap="round" />
      <g className="sc-breathe">
        <path d="M68 44 76 52 68 60M92 44 84 52 92 60"
              stroke="var(--danger-solid)" strokeWidth="2"
              strokeLinecap="round" strokeLinejoin="round" />
      </g>
      <path d="M80 30v-8M62 34l-5-6M98 34l5-6" stroke="var(--danger-solid)"
            strokeWidth="1.6" strokeLinecap="round" opacity="0.6" />
    </Art>
  );
}
