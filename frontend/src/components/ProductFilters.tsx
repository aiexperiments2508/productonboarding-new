import type { Facets, ProductRollup } from "../api";
import { IconSearch } from "../icons";
import { Badge, Button, Menu, MenuItem, Panel, Skeleton, Tooltip, cn } from "../ui";

/* The question this screen exists to answer.
 *
 * "For this date range, from all suppliers or these ones, in this category or
 * all of them - how many products came in fit to push downstream, and how many
 * had to go back to their source to be corrected."
 *
 * Two things about it are worth being careful with.
 *
 * **The date range is an arrival window.** A product has no date; an *event*
 * does. So the range asks which products anything arrived for between those
 * two moments, measured on the simulated clock the recorded flight runs on -
 * not on the wall clock the replayer happens to be running at this afternoon.
 * The response says which clock it used and the footer repeats it, because
 * that ambiguity would be invisible and wrong.
 *
 * **"Cleared" is not a score.** It is a count of products whose verdict is
 * READY_TO_LAUNCH, and it inherits the same rule every other surface follows:
 * if any product in the window was assessed by the rule checks alone, the
 * headline says "no rule findings" rather than "cleared", because a number on
 * a dashboard gets repeated by people who never opened the product.
 */

export interface Filters {
  q: string;
  start: string;
  end: string;
  suppliers: string[];
  categories: string[];
  includeUntouched: boolean;
}

export const EMPTY_FILTERS: Filters = {
  q: "", start: "", end: "", suppliers: [], categories: [],
  includeUntouched: false,
};

export function ProductFilters({
  filters, onChange, facets, horizon,
}: {
  filters: Filters;
  onChange: (next: Filters) => void;
  facets?: Facets | null;
  /** The recorded flight's own bounds, so the date fields cannot be set
   *  outside the tape and come back empty for no visible reason. */
  horizon?: { start: string; end: string } | null;
}) {
  const set = (patch: Partial<Filters>) => onChange({ ...filters, ...patch });
  const active =
    filters.suppliers.length + filters.categories.length
    + (filters.start ? 1 : 0) + (filters.end ? 1 : 0);

  return (
    <div className="flex flex-col gap-2 border-b border-subtle p-2">
      <label className="flex items-center gap-2 rounded-sm border border-line bg-canvas px-2">
        <IconSearch size={13} className="shrink-0 text-faint" />
        <input
          value={filters.q}
          onChange={(e) => set({ q: e.target.value })}
          placeholder="NAV-AP300-MAX, VAR-01B, or purifier"
          aria-label="Search products"
          className={cn(
            "min-w-0 flex-1 bg-transparent py-1.5 font-mono text-xs",
            "text-fg placeholder:text-faint focus:outline-none",
          )}
        />
      </label>

      <div className="flex flex-wrap items-center gap-1.5">
        <Tooltip content="Which products anything arrived for, on the recorded flight's own clock">
          <div className="flex items-center gap-1">
            <input
              type="date"
              value={filters.start}
              min={horizon?.start}
              max={horizon?.end}
              onChange={(e) => set({ start: e.target.value })}
              aria-label="Arrived on or after"
              className={cn(
                "rounded-sm border border-line bg-canvas px-1.5 py-1",
                "font-mono text-2xs text-fg focus:outline-none",
                "focus:ring-2 focus:ring-focus",
              )}
            />
            <span className="text-2xs text-faint">to</span>
            <input
              type="date"
              value={filters.end}
              min={horizon?.start}
              max={horizon?.end}
              onChange={(e) => set({ end: e.target.value })}
              aria-label="Arrived on or before"
              className={cn(
                "rounded-sm border border-line bg-canvas px-1.5 py-1",
                "font-mono text-2xs text-fg focus:outline-none",
                "focus:ring-2 focus:ring-focus",
              )}
            />
          </div>
        </Tooltip>

        <FacetMenu
          label="supplier"
          options={(facets?.suppliers ?? []).map((s) => ({
            value: s.id, label: s.name, n: s.products,
          }))}
          selected={filters.suppliers}
          onToggle={(value) => set({
            suppliers: toggle(filters.suppliers, value),
          })}
        />

        <FacetMenu
          label="category"
          options={(facets?.categories ?? []).map((c) => ({
            value: c.prefix, label: c.label, n: c.products,
          }))}
          selected={filters.categories}
          onToggle={(value) => set({
            categories: toggle(filters.categories, value),
          })}
        />

        {active > 0 && (
          <Button size="xs" tone="ghost"
                  onClick={() => onChange({ ...EMPTY_FILTERS, q: filters.q })}>
            clear {active} filter{active === 1 ? "" : "s"}
          </Button>
        )}
      </div>
    </div>
  );
}

const toggle = (list: string[], value: string): string[] =>
  list.includes(value) ? list.filter((v) => v !== value) : [...list, value];

function FacetMenu({
  label, options, selected, onToggle,
}: {
  label: string;
  options: { value: string; label: string; n: number }[];
  selected: string[];
  onToggle: (value: string) => void;
}) {
  // "categorys" is what naive pluralisation produces, and it is the kind of
  // thing a room notices before it notices anything else on the screen.
  const plural = label.endsWith("y") ? `${label.slice(0, -1)}ies` : `${label}s`;
  const summary =
    selected.length === 0 ? `all ${plural}`
    : selected.length === 1
      ? options.find((o) => o.value === selected[0])?.label ?? selected[0]
      : `${selected.length} ${plural}`;

  return (
    <Menu
      trigger={
        <Button size="xs" tone={selected.length ? "subtle" : "default"}>
          {summary}
        </Button>
      }
    >
      {options.map((option) => (
        <MenuItem key={option.value} keepOpen
                  onSelect={() => onToggle(option.value)}>
          <span className={cn("min-w-0 flex-1 truncate",
                              selected.includes(option.value) && "text-fg")}>
            {selected.includes(option.value) ? "✓ " : "   "}
            {option.label}
          </span>
          <span className="ml-2 shrink-0 font-mono text-2xs text-faint">
            {option.n}
          </span>
        </MenuItem>
      ))}
    </Menu>
  );
}

/* --- the counting answer -------------------------------------------------- */

export function ProductRollupStrip({
  rollup, loading,
}: {
  rollup: ProductRollup | null;
  loading: boolean;
}) {
  if (loading && !rollup) {
    return (
      <Panel title="Disposition" subtitle="counting…">
        <div className="grid grid-cols-4 gap-2">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-14" rounded="md" />
          ))}
        </div>
      </Panel>
    );
  }
  if (!rollup) return null;

  // The narrow-assessment rule, at population scale. If any product in this
  // window was assessed by the rule checks alone, the headline may not use the
  // word that means a complete assessment cleared it.
  const clearedWord = rollup.checks_complete ? "cleared" : "no rule findings";
  const window = rollup.window.start || rollup.window.end
    ? `${rollup.window.start || "start of the tape"} → ${rollup.window.end || "end of the tape"}`
    : "the whole recorded flight";

  return (
    <Panel
      title="Disposition"
      subtitle={window}
      actions={
        rollup.untouched > 0 ? (
          <Tooltip content="In the filter, but nothing arrived for them in this window. A source that went quiet is itself worth seeing.">
            <span><Badge tone="neutral">{rollup.untouched} untouched</Badge></span>
          </Tooltip>
        ) : undefined
      }
    >
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <Tile n={rollup.cleared} label={clearedWord}
              hint="fit to push downstream"
              tone={rollup.checks_complete ? "ok" : "neutral"} />
        <Tile n={rollup.returned} label="returned"
              hint="back to source to correct" tone="warn" />
        <Tile n={rollup.blocked} label="blocked"
              hint="may not be sold as it stands" tone="danger" />
        <Tile n={rollup.assessed} label="assessed"
              hint="products in this window" tone="neutral" />
      </div>

      {rollup.caveat && (
        <p className="mt-2 rounded-sm border border-warn-border bg-warn-soft px-2 py-1.5 text-2xs text-warn-text">
          {rollup.caveat}
        </p>
      )}

      {rollup.by_system.length > 0 && (
        <div className="mt-3">
          <h3 className="text-2xs uppercase tracking-caps text-faint">
            who has to fix it
          </h3>
          <ul className="mt-1 flex flex-col gap-1">
            {rollup.by_system.slice(0, 5).map((row) => (
              <li key={row.system}
                  className="flex items-baseline gap-2 text-xs">
                <span className="min-w-0 flex-1 truncate text-muted">
                  {row.owner ?? row.system}
                </span>
                <span className="shrink-0 font-mono text-2xs text-faint">
                  {row.products} product{row.products === 1 ? "" : "s"} ·{" "}
                  {row.findings} finding{row.findings === 1 ? "" : "s"}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <p className="mt-2 text-2xs text-faint">
        Window measured on {rollup.window.source}.
      </p>
    </Panel>
  );
}

function Tile({ n, label, hint, tone }: {
  n: number; label: string; hint: string;
  tone: "ok" | "warn" | "danger" | "neutral";
}) {
  const accent =
    tone === "ok" ? "text-ok-text"
    : tone === "warn" ? "text-warn-text"
    : tone === "danger" ? "text-danger-text"
    : "text-fg";
  return (
    <div className="rounded-sm border border-subtle bg-sunken p-2.5">
      <div className={cn("font-mono text-xl leading-none", accent)}>{n}</div>
      <div className="mt-1 text-2xs text-muted">{label}</div>
      <div className="text-2xs text-faint">{hint}</div>
    </div>
  );
}
