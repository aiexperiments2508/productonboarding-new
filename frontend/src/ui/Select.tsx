import type { ReactNode } from "react";
import { Select as RSelect } from "radix-ui";
import { IconCheck, IconChevronDown } from "../icons";
import { cn } from "./cn";

/* Select.
 *
 * A native <select> cannot be themed on Windows - the popup is drawn by the OS,
 * ignores the app's palette entirely, and in dark mode arrives as a white slab.
 * The model pickers and the option picker are all long lists read against dark
 * surfaces, so they need a portalled listbox we control.
 *
 * Radix keeps the native semantics: typeahead, arrow keys, Home/End, and the
 * value announced as a listbox rather than as a div someone made clickable.
 */

export interface SelectOption {
  value: string;
  label: string;
  /** Optional right-aligned detail - a KPI figure, a tier, a latency. */
  hint?: string;
  group?: string;
}

export function Select({
  value, onValueChange, options, placeholder = "Select…", className,
  disabled, ariaLabel,
}: {
  value?: string;
  onValueChange: (v: string) => void;
  options: SelectOption[];
  placeholder?: string;
  className?: string;
  disabled?: boolean;
  ariaLabel?: string;
}) {
  // Preserve declaration order of groups; a Map keyed by group name would
  // reorder ungrouped options to the end.
  const groups: { name: string | undefined; items: SelectOption[] }[] = [];
  for (const opt of options) {
    const last = groups[groups.length - 1];
    if (last && last.name === opt.group) last.items.push(opt);
    else groups.push({ name: opt.group, items: [opt] });
  }

  return (
    <RSelect.Root value={value} onValueChange={onValueChange} disabled={disabled}>
      <RSelect.Trigger
        aria-label={ariaLabel}
        className={cn(
          "inline-flex h-[var(--control-h-sm)] min-w-0 items-center gap-2",
          "rounded-sm border border-strong bg-raised px-2.5 text-base text-fg",
          "transition-colors duration-[var(--dur-fast)]",
          "hover:bg-hover data-[state=open]:border-focus",
          "disabled:pointer-events-none disabled:opacity-45",
          className
        )}
      >
        <RSelect.Value placeholder={placeholder} className="truncate" />
        <RSelect.Icon className="ml-auto shrink-0 text-faint">
          <IconChevronDown size={13} />
        </RSelect.Icon>
      </RSelect.Trigger>

      <RSelect.Portal>
        <RSelect.Content
          position="popper"
          sideOffset={5}
          collisionPadding={8}
          className={cn(
            "z-[var(--z-overlay)] overflow-hidden rounded-md border border-strong",
            "bg-overlay shadow-e3 data-[state=open]:animate-scale-in",
            // Match the trigger's width so the list does not resize under the
            // pointer as the selection changes.
            "w-[var(--radix-select-trigger-width)]",
            "max-h-[min(420px,var(--radix-select-content-available-height))]",
            "origin-[var(--radix-select-content-transform-origin)]"
          )}
        >
          <RSelect.ScrollUpButton className="flex h-5 items-center justify-center text-faint">
            <IconChevronDown size={12} className="rotate-180" />
          </RSelect.ScrollUpButton>
          <RSelect.Viewport className="p-1">
            {groups.map((group, gi) => (
              <RSelect.Group key={group.name ?? `g${gi}`}>
                {group.name && (
                  <RSelect.Label className="px-2 pb-1 pt-1.5 text-xs font-semibold uppercase tracking-caps text-faint">
                    {group.name}
                  </RSelect.Label>
                )}
                {group.items.map((opt) => (
                  <RSelect.Item
                    key={opt.value}
                    value={opt.value}
                    className={cn(
                      "flex cursor-pointer select-none items-center gap-2 rounded-sm",
                      "px-2 py-1.5 text-base text-fg outline-none",
                      "transition-colors duration-[var(--dur-fast)]",
                      "data-[highlighted]:bg-hover",
                      "data-[disabled]:pointer-events-none data-[disabled]:opacity-45"
                    )}
                  >
                    <span className="flex size-4 shrink-0 items-center justify-center text-accent-text">
                      <RSelect.ItemIndicator>
                        <IconCheck size={13} />
                      </RSelect.ItemIndicator>
                    </span>
                    <RSelect.ItemText>
                      <span className="truncate">{opt.label}</span>
                    </RSelect.ItemText>
                    {opt.hint && (
                      <span className="ml-auto shrink-0 font-mono text-xs text-faint">
                        {opt.hint}
                      </span>
                    )}
                  </RSelect.Item>
                ))}
              </RSelect.Group>
            ))}
          </RSelect.Viewport>
          <RSelect.ScrollDownButton className="flex h-5 items-center justify-center text-faint">
            <IconChevronDown size={12} />
          </RSelect.ScrollDownButton>
        </RSelect.Content>
      </RSelect.Portal>
    </RSelect.Root>
  );
}

/** Label + control on one row. The label column is fixed so a stack of fields
 *  shares a single control edge. */
export function Field({
  label, children, width = 88,
}: {
  label: ReactNode;
  children: ReactNode;
  width?: number;
}) {
  return (
    <label className="flex items-center gap-2">
      <span
        style={{ width }}
        className="shrink-0 text-sm text-faint"
      >
        {label}
      </span>
      <span className="min-w-0 flex-1">{children}</span>
    </label>
  );
}
