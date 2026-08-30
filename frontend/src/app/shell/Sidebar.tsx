import { Brand } from "../../art/BrandMark";
import { IconSidebar } from "../../icons";
import { Badge, Button, Tooltip, cn } from "../../ui";
import { SECTIONS } from "../nav";
import type { SectionId } from "../nav";

/* Left navigation.
 *
 * Collapses to a 56px icon rail. The collapsed state is not decoration: the
 * Ingest Fabric's catalog map is the widest thing in the product and it reads
 * meaningfully better with another 160px, so the rail is what a reviewer
 * actually watches a correction from.
 *
 * The active item is marked by a filled left edge rather than a background
 * change alone - at a glance across a room, a solid 3px bar is legible where a
 * tinted row is not.
 */

export function Sidebar({
  active, onSelect, collapsed, onToggleCollapsed, pendingCount,
}: {
  active: SectionId;
  onSelect: (id: SectionId) => void;
  collapsed: boolean;
  onToggleCollapsed: () => void;
  pendingCount: number;
}) {
  return (
    <nav
      aria-label="Sections"
      style={{
        width: collapsed ? "var(--shell-rail-w)" : "var(--shell-nav-w)",
      }}
      className={cn(
        "flex shrink-0 flex-col border-r border-subtle bg-raised",
        "transition-[width] duration-[var(--dur-base)] ease-standard"
      )}
    >
      <div
        className={cn(
          "flex h-[var(--shell-bar-h)] shrink-0 items-center border-b border-subtle",
          collapsed ? "justify-center px-2" : "px-3"
        )}
      >
        <Brand collapsed={collapsed} />
      </div>

      <ul className="flex min-h-0 flex-1 flex-col gap-0.5 overflow-y-auto p-2">
        {SECTIONS.map((section) => {
          const isActive = section.id === active;
          const badge =
            section.id === "approvals" && pendingCount > 0 ? pendingCount : 0;
          const item = (
            <button
              onClick={() => onSelect(section.id)}
              aria-current={isActive ? "page" : undefined}
              className={cn(
                "group relative flex w-full items-center gap-2.5 rounded-sm",
                "py-2 text-base transition-colors duration-[var(--dur-fast)]",
                collapsed ? "justify-center px-0" : "px-2.5",
                isActive
                  ? "bg-accent-soft font-medium text-accent-text"
                  : "text-muted hover:bg-hover hover:text-fg"
              )}
            >
              <span
                aria-hidden="true"
                className={cn(
                  "absolute left-0 top-1/2 w-[3px] -translate-y-1/2 rounded-r-full",
                  "bg-accent transition-[height] duration-[var(--dur-base)]",
                  "ease-emphasized",
                  isActive ? "h-5" : "h-0"
                )}
              />
              <section.Icon size={17} className="shrink-0" />
              {!collapsed && (
                <span className="min-w-0 flex-1 truncate text-left">
                  {section.label}
                </span>
              )}
              {badge > 0 && (
                <Badge
                  tone="warn"
                  className={cn(
                    collapsed &&
                      "absolute -right-0.5 -top-0.5 px-1 py-0 text-2xs"
                  )}
                >
                  {badge}
                </Badge>
              )}
            </button>
          );

          return (
            <li key={section.id}>
              {collapsed ? (
                <Tooltip side="right" content={section.label}>
                  {item}
                </Tooltip>
              ) : (
                item
              )}
            </li>
          );
        })}
      </ul>

      <div
        className={cn(
          "shrink-0 border-t border-subtle p-2",
          collapsed && "flex justify-center"
        )}
      >
        <Tooltip
          side="right"
          content={collapsed ? "Expand navigation" : "Collapse navigation"}
        >
          <Button
            tone="ghost"
            size="sm"
            onClick={onToggleCollapsed}
            iconOnly={collapsed}
            icon={<IconSidebar size={15} />}
            aria-label={collapsed ? "Expand navigation" : "Collapse navigation"}
            className={cn(!collapsed && "w-full justify-start")}
          >
            {!collapsed && "Collapse"}
          </Button>
        </Tooltip>
      </div>
    </nav>
  );
}
