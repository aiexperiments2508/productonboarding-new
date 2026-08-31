import type { ReactNode } from "react";
import { DropdownMenu } from "radix-ui";
import { IconCheck } from "../icons";
import { cn } from "./cn";

/* Dropdown menu.
 *
 * Radix owns focus trapping, typeahead, arrow-key navigation, and returning
 * focus to the trigger on close. Those are the parts that are tedious to write
 * and worse to write badly, and they are exactly what a hand-rolled menu on a
 * deadline skips.
 */

const CONTENT = cn(
  "z-[var(--z-overlay)] min-w-[190px] overflow-hidden rounded-md",
  "border border-strong bg-overlay p-1 shadow-e3",
  "data-[state=open]:animate-scale-in",
  "origin-[var(--radix-dropdown-menu-content-transform-origin)]"
);

const ITEM = cn(
  "flex cursor-pointer select-none items-center gap-2 rounded-sm px-2 py-1.5",
  "text-base text-fg outline-none transition-colors duration-[var(--dur-fast)]",
  "data-[highlighted]:bg-hover data-[highlighted]:text-fg",
  "data-[disabled]:pointer-events-none data-[disabled]:opacity-45"
);

export function Menu({
  trigger, children, align = "end", side = "bottom",
}: {
  trigger: ReactNode;
  children: ReactNode;
  align?: "start" | "center" | "end";
  side?: "top" | "right" | "bottom" | "left";
}) {
  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger asChild>{trigger}</DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content
          align={align}
          side={side}
          sideOffset={6}
          collisionPadding={8}
          className={CONTENT}
        >
          {children}
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}

export function MenuLabel({ children }: { children: ReactNode }) {
  return (
    <DropdownMenu.Label className="px-2 pb-1 pt-1.5 text-xs font-semibold uppercase tracking-caps text-faint">
      {children}
    </DropdownMenu.Label>
  );
}

export function MenuSeparator() {
  return <DropdownMenu.Separator className="my-1 h-px bg-subtle" />;
}

export function MenuItem({
  children, onSelect, icon, disabled, shortcut, keepOpen,
}: {
  children: ReactNode;
  onSelect?: () => void;
  icon?: ReactNode;
  disabled?: boolean;
  shortcut?: ReactNode;
  /** Stay open after this item is chosen. For a menu that is a multi-select
   *  rather than a command list: picking three suppliers should be three
   *  clicks, not three round trips through a menu that shut itself. */
  keepOpen?: boolean;
}) {
  return (
    <DropdownMenu.Item
      className={ITEM}
      disabled={disabled}
      onSelect={(event) => {
        if (keepOpen) event.preventDefault();
        onSelect?.();
      }}
    >
      {icon && <span className="shrink-0 text-faint">{icon}</span>}
      <span className="flex-1 truncate">{children}</span>
      {shortcut && <span className="shrink-0 text-xs text-faint">{shortcut}</span>}
    </DropdownMenu.Item>
  );
}

/** A radio group. The check occupies a reserved slot on every row, so the
 *  labels stay on one left edge instead of shifting as the selection moves. */
export function MenuRadioGroup({
  value, onValueChange, children,
}: {
  value: string;
  onValueChange: (v: string) => void;
  children: ReactNode;
}) {
  return (
    <DropdownMenu.RadioGroup value={value} onValueChange={onValueChange}>
      {children}
    </DropdownMenu.RadioGroup>
  );
}

export function MenuRadioItem({
  value, children, icon,
}: {
  value: string;
  children: ReactNode;
  icon?: ReactNode;
}) {
  return (
    <DropdownMenu.RadioItem value={value} className={ITEM}>
      <span className="flex size-4 shrink-0 items-center justify-center text-accent-text">
        <DropdownMenu.ItemIndicator>
          <IconCheck size={13} />
        </DropdownMenu.ItemIndicator>
      </span>
      {icon && <span className="shrink-0 text-faint">{icon}</span>}
      <span className="flex-1 truncate">{children}</span>
    </DropdownMenu.RadioItem>
  );
}
