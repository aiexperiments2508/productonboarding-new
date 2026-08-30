import type { ReactNode, ThHTMLAttributes, TdHTMLAttributes } from "react";
import { cn } from "./cn";

/* Table.
 *
 * Sticky header, hover rows, selectable rows, and a numeric column style that
 * is monospace and tabular so a column of figures aligns on the decimal and
 * stops jittering when a value updates in place.
 *
 * `Th`/`Td` take a `num` flag rather than the caller remembering a class pair -
 * the alignment and the font have to move together, and splitting them is how
 * a table ends up with right-aligned proportional numerals.
 */

export function Table({
  children, className, scroll,
}: {
  children: ReactNode;
  className?: string;
  /** Wrap in a horizontal scroller. Dense tables overflow on narrow panels,
   *  and the page must never be what scrolls sideways. */
  scroll?: boolean;
}) {
  // `w-full` alone makes a dense table compress its columns to fit rather
  // than overflow, which silently truncates the rightmost ones. Pairing it
  // with a min-width is what actually hands the overflow to the scroller.
  const table = (
    <table
      className={cn(
        "w-full border-collapse text-base",
        scroll && "min-w-[var(--table-min-w,680px)]",
        className
      )}
    >
      {children}
    </table>
  );
  return scroll ? (
    <div className="min-w-0 overflow-x-auto">{table}</div>
  ) : (
    table
  );
}

export function Th({
  num, className, children, ...rest
}: ThHTMLAttributes<HTMLTableCellElement> & { num?: boolean }) {
  return (
    <th
      className={cn(
        "sticky top-0 z-[1] border-b border-subtle bg-raised px-2.5 py-1.5",
        "text-xs font-semibold uppercase tracking-caps text-faint",
        num ? "text-right" : "text-left",
        className
      )}
      {...rest}
    >
      {children}
    </th>
  );
}

export function Td({
  num, className, children, ...rest
}: TdHTMLAttributes<HTMLTableCellElement> & { num?: boolean }) {
  return (
    <td
      className={cn(
        "border-b border-subtle px-2.5 py-1.5 align-top",
        num && "text-right font-mono text-sm tabular-nums",
        className
      )}
      {...rest}
    >
      {children}
    </td>
  );
}

export function Tr({
  selected, onClick, children, className,
}: {
  selected?: boolean;
  onClick?: () => void;
  children: ReactNode;
  className?: string;
}) {
  return (
    <tr
      onClick={onClick}
      // A clickable row is a real control: it needs to be reachable and
      // operable from the keyboard, not only from a mouse.
      tabIndex={onClick ? 0 : undefined}
      role={onClick ? "button" : undefined}
      aria-selected={onClick ? !!selected : undefined}
      onKeyDown={
        onClick
          ? (e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onClick();
              }
            }
          : undefined
      }
      className={cn(
        "transition-colors duration-[var(--dur-fast)]",
        onClick && "cursor-pointer",
        selected
          ? "bg-accent-soft"
          : onClick && "hover:bg-hover",
        className
      )}
    >
      {children}
    </tr>
  );
}
