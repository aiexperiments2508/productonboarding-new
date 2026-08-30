import { cn } from "../ui/cn";

/* The mark.
 *
 * One corrected value fanning out to the three channels built on it - which is
 * the product in one glyph. The routes draw themselves once on mount and a
 * pulse then travels them in turn, so the mark says "a correction reaching
 * every channel" rather than "a logo".
 *
 * The source node is solid because a corrected value is known; the channels are
 * hollow because what they publish is derived and, until the reviewer says so,
 * still standing on the old figure. That is the same fill grammar the catalog
 * map uses.
 *
 * Drawn on the same 24-unit grid as the icon set, so it sits correctly beside
 * them in the rail without optical adjustment.
 */

/* Kept in one place: the line that draws itself and the path the pulse travels
   are the same strings, so they cannot drift apart. */
const ROUTES = [
  "M7.2 12C12 12 12 5.5 16.8 5.5",
  "M7.2 12h9.6",
  "M7.2 12C12 12 12 18.5 16.8 18.5",
];

const CYCLE = 3.6;

export function BrandMark({
  size = 26, className, animated = true,
}: {
  size?: number;
  className?: string;
  animated?: boolean;
}) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      className={cn("shrink-0", className)}
      role="img"
      aria-label="Correction Engine"
    >
      <defs>
        <linearGradient id="bm-grad" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor="var(--accent-solid)" />
          <stop offset="100%" stopColor="var(--prov-inferred)" />
        </linearGradient>
      </defs>

      {/* The derivations. --draw-length is a rough over-estimate of the path
          length; a few units over is invisible and avoids a layout read on
          every mount. */}
      {ROUTES.map((d, i) => (
        <path
          key={d}
          d={d}
          stroke="url(#bm-grad)"
          strokeWidth="1.8"
          strokeLinecap="round"
          className={animated ? "sc-draw" : undefined}
          style={{
            ["--draw-length" as string]: "16",
            animationDelay: animated ? `${i * 90}ms` : undefined,
          }}
        />
      ))}

      <circle cx="4.8" cy="12" r="2.4" fill="var(--accent-solid)" />
      {[5.5, 12, 18.5].map((cy) => (
        <circle key={cy} cx="19.2" cy={cy} r="2.2" fill="var(--surface-raised)"
                stroke="var(--prov-inferred)" strokeWidth="1.7" />
      ))}

      {/* One pulse per route, each travelling in the first third of the cycle
          and staggered by a third. Only one is ever in flight, so the mark
          reads as a correction going out channel by channel rather than as
          three things moving at once. */}
      {animated && ROUTES.map((d, i) => (
        <circle key={d} r="1.4" fill="var(--surface-raised)"
                stroke="var(--accent-solid)" strokeWidth="1.2" opacity="0">
          <animateMotion
            dur={`${CYCLE}s`}
            begin={`${(i * CYCLE) / 3}s`}
            repeatCount="indefinite"
            keyPoints="0;1;1"
            keyTimes="0;0.33;1"
            calcMode="linear"
            path={d}
          />
          <animate
            attributeName="opacity"
            values="0;1;1;0;0"
            keyTimes="0;0.08;0.27;0.33;1"
            dur={`${CYCLE}s`}
            begin={`${(i * CYCLE) / 3}s`}
            repeatCount="indefinite"
          />
        </circle>
      ))}
    </svg>
  );
}

/** Wordmark + mark, for the rail header. */
export function Brand({ collapsed }: { collapsed?: boolean }) {
  return (
    <div className="flex min-w-0 items-center gap-2.5">
      <BrandMark />
      {!collapsed && (
        <div className="min-w-0 leading-tight">
          <div className="truncate text-base font-semibold tracking-tight text-fg">
            Correction Engine
          </div>
          <div className="truncate text-xs text-faint">
            Product intelligence factory
          </div>
        </div>
      )}
    </div>
  );
}
