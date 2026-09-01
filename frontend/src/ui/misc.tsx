import { useRef } from "react";
import type { KeyboardEvent, ReactNode } from "react";
import { cn } from "./cn";

/* Small shared pieces. Each is a few lines and none of them earns a file.
 */

/** Keyboard shortcut hint. */
export function Kbd({ children }: { children: ReactNode }) {
  return (
    <kbd
      className={cn(
        "inline-flex h-4 min-w-4 items-center justify-center rounded-xs",
        "border border-strong bg-sunken px-1 font-mono text-2xs",
        "font-medium text-muted"
      )}
    >
      {children}
    </kbd>
  );
}

/** Determinate progress bar. */
export function ProgressBar({
  value, tone = "accent", className, ariaLabel,
}: {
  /** 0-100. */
  value: number;
  tone?: "accent" | "ok" | "warn" | "danger";
  className?: string;
  ariaLabel?: string;
}) {
  const fill =
    tone === "ok" ? "bg-ok"
    : tone === "warn" ? "bg-warn"
    : tone === "danger" ? "bg-danger"
    : "bg-accent";
  const pct = Math.max(0, Math.min(100, value));
  return (
    <div
      role="progressbar"
      aria-label={ariaLabel}
      aria-valuenow={Math.round(pct)}
      aria-valuemin={0}
      aria-valuemax={100}
      className={cn("h-1.5 overflow-hidden rounded-full bg-sunken", className)}
    >
      <div
        className={cn(
          "h-full rounded-full transition-[width]",
          "duration-[var(--dur-slow)] ease-standard",
          fill
        )}
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}

/** Segmented control. Used for theme and density, where the options are few,
 *  mutually exclusive, and worth showing all at once rather than behind a
 *  menu. Arrow keys move between options, per the radiogroup pattern.
 *
 *  That last sentence was a lie for a long time. The roles were right and
 *  there was no key handling at all, so every option was an independently
 *  tabbable button - which is the one thing a radiogroup is specified not to
 *  be, and it meant tabbing through a page with a five-option control cost
 *  five stops. The roving tabindex below is what the docstring was always
 *  describing. */
export function SegmentedControl<T extends string>({
  value, onChange, options, ariaLabel, className,
}: {
  value: T;
  onChange: (v: T) => void;
  options: { value: T; label: ReactNode; title?: string }[];
  ariaLabel?: string;
  className?: string;
}) {
  const container = useRef<HTMLDivElement | null>(null);

  // Arrow keys select *and* move focus, because in a radiogroup they are the
  // same act: the checked option is the focused one. Home and End go to the
  // ends, which is the rest of the pattern and costs two lines.
  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const keys = ["ArrowRight", "ArrowDown", "ArrowLeft", "ArrowUp",
                  "Home", "End"];
    if (!keys.includes(event.key)) return;
    event.preventDefault();

    const at = options.findIndex((opt) => opt.value === value);
    const last = options.length - 1;
    let next = at;
    if (event.key === "Home") next = 0;
    else if (event.key === "End") next = last;
    else if (event.key === "ArrowRight" || event.key === "ArrowDown") {
      next = at >= last ? 0 : at + 1;
    } else {
      next = at <= 0 ? last : at - 1;
    }
    if (next === at) return;

    onChange(options[next].value);
    // The DOM has not re-rendered yet, so focus by position rather than by
    // looking for the checked one.
    const buttons = container.current?.querySelectorAll("button");
    buttons?.[next]?.focus();
  };

  return (
    <div
      ref={container}
      role="radiogroup"
      aria-label={ariaLabel}
      onKeyDown={onKeyDown}
      className={cn(
        "inline-flex items-center gap-0.5 rounded-sm border border-subtle",
        "bg-sunken p-0.5",
        className
      )}
    >
      {options.map((opt) => {
        const active = opt.value === value;
        return (
          <button
            key={opt.value}
            role="radio"
            aria-checked={active}
            // One tab stop for the whole control, on whichever option is
            // checked. This is the roving half of the roving tabindex.
            tabIndex={active ? 0 : -1}
            title={opt.title}
            onClick={() => onChange(opt.value)}
            className={cn(
              "inline-flex h-6 items-center justify-center gap-1.5 rounded-xs",
              "px-2 text-sm transition-colors duration-[var(--dur-fast)]",
              active
                ? "bg-raised text-fg shadow-e1"
                : "text-muted hover:text-fg"
            )}
          >
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}

/** Label above a figure. The building block of every KPI on the screen. */
export function Stat({
  label, value, sub, tone, mono = true, className,
}: {
  label: ReactNode;
  value: ReactNode;
  sub?: ReactNode;
  tone?: "good" | "bad";
  mono?: boolean;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "min-w-0 rounded-sm border border-subtle bg-sunken px-2.5 py-2",
        className
      )}
    >
      <div className="truncate text-2xs uppercase tracking-caps text-faint">
        {label}
      </div>
      <div
        className={cn(
          "mt-0.5 truncate text-lg leading-tight tabular-nums",
          mono && "font-mono",
          tone === "good" ? "text-ok-text"
            : tone === "bad" ? "text-danger-text" : "text-fg"
        )}
      >
        {value}
      </div>
      {sub && <div className="mt-0.5 truncate text-xs text-faint">{sub}</div>}
    </div>
  );
}

/** Horizontal rule with a bit more air than <hr>. */
export function Divider({ className }: { className?: string }) {
  return <div className={cn("h-px w-full shrink-0 bg-subtle", className)} />;
}

/** Inline code / identifier. Identifiers are the primary key of this whole
 *  screen, so they get a consistent treatment everywhere they appear. */
export function Code({
  children, className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <code
      className={cn(
        "rounded-xs bg-sunken px-1 py-px font-mono text-xs text-muted",
        className
      )}
    >
      {children}
    </code>
  );
}
