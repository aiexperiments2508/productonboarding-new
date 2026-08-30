import { cn } from "./cn";

/* Skeletons.
 *
 * Replacing the old "Loading…" text. A word centred in an empty panel gives no
 * sense of what is coming or how much of it; a skeleton in the shape of the
 * content keeps the layout from jumping when the data lands, which on a screen
 * of eight panels is the difference between a page settling and a page
 * flickering.
 */

export function Skeleton({
  className, rounded = "sm",
}: {
  className?: string;
  rounded?: "sm" | "md" | "full";
}) {
  return (
    <div
      aria-hidden="true"
      className={cn(
        "sc-skeleton",
        rounded === "full" ? "rounded-full"
          : rounded === "md" ? "rounded-md" : "rounded-sm",
        className
      )}
    />
  );
}

/** Rows of text. The last line is short, the way a paragraph ends. */
export function SkeletonText({ lines = 3 }: { lines?: number }) {
  return (
    <div className="flex flex-col gap-1.5" aria-hidden="true">
      {Array.from({ length: lines }, (_, i) => (
        <Skeleton
          key={i}
          className="h-3"
          // Vary the widths so it reads as prose rather than a bar chart.
          {...{ style: { width: i === lines - 1 ? "58%" : `${88 - i * 7}%` } }}
        />
      ))}
    </div>
  );
}

export function SkeletonTable({ rows = 5, cols = 4 }: { rows?: number; cols?: number }) {
  return (
    <div className="flex flex-col" aria-hidden="true">
      {Array.from({ length: rows }, (_, r) => (
        <div key={r} className="flex items-center gap-3 border-b border-subtle px-2.5 py-2">
          {Array.from({ length: cols }, (_, c) => (
            <Skeleton
              key={c}
              className="h-3"
              {...{ style: { flex: c === 0 ? 3 : 1 } }}
            />
          ))}
        </div>
      ))}
    </div>
  );
}

export function SkeletonKpis({ count = 3 }: { count?: number }) {
  return (
    <div
      className="grid gap-2"
      style={{ gridTemplateColumns: `repeat(${count}, minmax(0, 1fr))` }}
      aria-hidden="true"
    >
      {Array.from({ length: count }, (_, i) => (
        <div key={i} className="rounded-sm border border-subtle bg-sunken p-2.5">
          <Skeleton className="h-2.5 w-3/5" />
          <Skeleton className="mt-2 h-5 w-2/3" />
        </div>
      ))}
    </div>
  );
}

/** A busy panel body. `label` is announced; the bars are decorative. */
export function LoadingBody({
  label = "Loading", children,
}: {
  label?: string;
  children?: React.ReactNode;
}) {
  return (
    <div role="status" aria-live="polite" aria-busy="true" className="p-1">
      <span className="sr-only">{label}</span>
      {children ?? <SkeletonText />}
    </div>
  );
}
