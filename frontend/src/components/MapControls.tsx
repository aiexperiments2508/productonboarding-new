import type { Facets, MapView } from "../api";
import { IconSearch } from "../icons";
import { Badge, Button, Menu, MenuItem, SegmentedControl, cn } from "../ui";

/* Search and filters for the Ingest Fabric.
 *
 * The map draws a page of the catalog, not all of it. At six products that
 * distinction did not exist; at a hundred and fifty a picture of everything is
 * a picture of nothing, and the honest response is not to draw smaller nodes
 * but to draw fewer and say so.
 *
 * So: ten products by default, and the controls to choose which ten. The
 * search is the same banded ranking the product list uses - an exact SKU beats
 * a name match, always - so the map and the list can never disagree about what
 * a query means.
 *
 * The count line is not decoration. "10 of 150" is the difference between a
 * reviewer understanding they are looking at a sample and believing they are
 * looking at the estate.
 */

export const PAGE_SIZES = ["8", "10", "25", "50"] as const;
export type PageSize = (typeof PAGE_SIZES)[number];

export interface MapFilters {
  q: string;
  limit: number;
  offset: number;
  suppliers: string[];
  categories: string[];
}

export const DEFAULT_MAP_FILTERS: MapFilters = {
  q: "", limit: 10, offset: 0, suppliers: [], categories: [],
};

export function MapControls({
  filters, onChange, facets, page, busy,
}: {
  filters: MapFilters;
  onChange: (next: MapFilters) => void;
  facets?: Facets | null;
  page?: MapView["page"] | null;
  busy?: boolean;
}) {
  // Any change to what is selected resets the page. Staying on page four of a
  // filter that now has one page shows an empty map and looks like a fault.
  const set = (patch: Partial<MapFilters>) =>
    onChange({ ...filters, offset: 0, ...patch });

  const total = page?.total_products ?? 0;
  const shown = page?.returned ?? 0;
  const from = total === 0 ? 0 : filters.offset + 1;
  const to = filters.offset + shown;

  return (
    <div className="flex flex-wrap items-center gap-2 border-b border-subtle px-3 py-2">
      <label className="flex min-w-[180px] flex-1 items-center gap-2 rounded-sm border border-line bg-canvas px-2">
        <IconSearch size={13} className="shrink-0 text-faint" />
        <input
          value={filters.q}
          onChange={(e) => set({ q: e.target.value })}
          placeholder="Find a product, SKU or identifier"
          aria-label="Find a product on the map"
          className={cn(
            "min-w-0 flex-1 bg-transparent py-1 font-mono text-xs",
            "text-fg placeholder:text-faint focus:outline-none",
          )}
        />
      </label>

      <FacetMenu
        label="source"
        options={(facets?.suppliers ?? []).map((s) => ({
          value: s.id, label: s.name, n: s.products,
        }))}
        selected={filters.suppliers}
        onToggle={(v) => set({ suppliers: toggle(filters.suppliers, v) })}
      />

      <FacetMenu
        label="category"
        options={(facets?.categories ?? []).map((c) => ({
          value: c.prefix, label: c.label, n: c.products,
        }))}
        selected={filters.categories}
        onToggle={(v) => set({ categories: toggle(filters.categories, v) })}
      />

      <SegmentedControl
        value={String(filters.limit) as PageSize}
        onChange={(v) => set({ limit: Number(v) })}
        options={PAGE_SIZES.map((n) => ({ value: n, label: n }))}
        ariaLabel="How many products the map draws"
      />

      <div className="ml-auto flex items-center gap-1.5">
        <span className="font-mono text-2xs text-faint">
          {busy ? "…" : `${from}–${to} of ${total}`}
        </span>
        {page?.truncated && (
          <Badge tone="neutral">filtered</Badge>
        )}
        <Button
          size="xs"
          disabled={filters.offset === 0}
          onClick={() => onChange({
            ...filters,
            offset: Math.max(0, filters.offset - filters.limit),
          })}
        >
          prev
        </Button>
        <Button
          size="xs"
          disabled={to >= total}
          onClick={() => onChange({
            ...filters, offset: filters.offset + filters.limit,
          })}
        >
          next
        </Button>
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
          <span className="min-w-0 flex-1 truncate">
            {selected.includes(option.value) ? "✓ " : "   "}
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
