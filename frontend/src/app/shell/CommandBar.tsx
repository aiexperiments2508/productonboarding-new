import { BRAND_PRESETS, useTheme } from "../../theme/ThemeProvider";
import type { Density, Theme } from "../../theme/ThemeProvider";
import {
  IconChevronRight, IconCommand, IconDensity, IconMonitor, IconMoon,
  IconPalette, IconSearch, IconSun,
} from "../../icons";
import {
  Badge, Button, Dot, Kbd, Menu, MenuLabel, MenuRadioGroup, MenuRadioItem,
  MenuSeparator, Tooltip, cn,
} from "../../ui";
import { sectionById } from "../nav";
import type { SectionId } from "../nav";
import type { Health } from "../../api";
import { ActivityPill } from "./ActivityPill";

/* Top bar.
 *
 * Breadcrumb on the left so the current section is stated in words as well as
 * by the rail's highlight, the palette trigger in the middle, and the two
 * things a reviewer checks without being asked - gateway reachability and the
 * appearance settings - on the right.
 */

export function CommandBar({
  section, health, liveNode, onOpenPalette, onOpenSystem,
}: {
  section: SectionId;
  health: Health | null;
  /** The graph node executing right now. Feeds the agent monitor. */
  liveNode: string | null;
  onOpenPalette: () => void;
  onOpenSystem: () => void;
}) {
  const current = sectionById(section);

  return (
    <header
      className={cn(
        "flex h-[var(--shell-bar-h)] shrink-0 items-center gap-3",
        "border-b border-subtle bg-raised px-3"
      )}
    >
      <nav aria-label="Breadcrumb" className="flex shrink-0 items-center gap-1.5">
        <span className="hidden text-sm text-faint sm:inline">
          Product Intelligence
        </span>
        <IconChevronRight
          size={12}
          className="hidden shrink-0 text-faint sm:inline"
        />
        <span className="flex items-center gap-1.5">
          <current.Icon size={15} className="shrink-0 text-accent-text" />
          <span className="whitespace-nowrap text-base font-medium text-fg">
            {current.label}
          </span>
        </span>
      </nav>

      <PaletteTrigger onClick={onOpenPalette} />

      <div className="ml-auto flex shrink-0 items-center gap-2">
        <ActivityPill liveNode={liveNode} onOpenSystem={onOpenSystem} />
        <GatewayPill health={health} />
        <AppearanceMenu />
      </div>
    </header>
  );
}

/** Looks like a search field, opens the palette. A real input here would be a
 *  second search surface competing with the palette's own. */
function PaletteTrigger({ onClick }: { onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "mx-auto hidden h-[var(--control-h-sm)] w-full min-w-0 max-w-sm items-center",
        "gap-2 rounded-sm border border-subtle bg-sunken px-2.5 text-sm",
        "text-faint transition-colors duration-[var(--dur-fast)]",
        "hover:border-strong hover:text-muted md:flex"
      )}
    >
      <IconSearch size={14} className="shrink-0" />
      <span className="flex-1 text-left">
        Search the standards, or run a command…
      </span>
      <span className="flex shrink-0 items-center gap-0.5">
        <Kbd>
          <IconCommand size={9} />
        </Kbd>
        <Kbd>K</Kbd>
      </span>
    </button>
  );
}

/** Gateway reachability. Degraded is not an error - every model step has a
 *  deterministic fallback - so it reads as a warning, never as a failure. The
 *  numbers on the change diff never came from a model in the first place. */
function GatewayPill({ health }: { health: Health | null }) {
  // Destructured rather than reached through twice. The contract makes
  // `gateway` required, but this pill is mounted outside the error boundary -
  // a payload missing the block would blank the whole shell instead of one
  // panel, so an absent block reads the same as no payload yet.
  const gateway = health?.gateway;
  const ok = gateway?.ok;
  const circuitOpen = gateway?.circuit?.open;
  const detail = !gateway
    ? "Checking the model gateway…"
    : ok
    ? `Gateway reachable\n${gateway.url}`
    : circuitOpen
    ? `Circuit open after repeated failures — retrying in ${gateway.circuit?.retry_in_seconds}s.\nEvery model step is running its deterministic fallback.`
    : "Gateway unreachable. Every model step is running its deterministic fallback — the wording of the copy degrades, the validation and the counts do not.";

  return (
    <Tooltip content={detail} side="bottom">
      <span
        className={cn(
          "hidden items-center gap-1.5 rounded-full border px-2 py-0.5",
          "text-xs sm:inline-flex",
          ok
            ? "border-ok-border bg-ok-soft text-ok-text"
            : "border-warn-border bg-warn-soft text-warn-text"
        )}
      >
        <Dot tone={ok ? "ok" : "warn"} className="[&>span]:size-1.5" />
        gateway
      </span>
    </Tooltip>
  );
}

const THEME_ICON: Record<Theme, typeof IconSun> = {
  light: IconSun,
  dark: IconMoon,
  system: IconMonitor,
};

function AppearanceMenu() {
  const {
    theme, setTheme, resolvedTheme, density, setDensity, brandHue, setBrandHue,
  } = useTheme();
  const ThemeIcon = THEME_ICON[theme];

  return (
    <Menu
      trigger={
        <Button
          tone="ghost"
          size="sm"
          iconOnly
          aria-label={`Appearance — theme ${theme}, density ${density}`}
          icon={<ThemeIcon size={15} />}
        />
      }
    >
      <MenuLabel>Theme</MenuLabel>
      <MenuRadioGroup
        value={theme}
        onValueChange={(v) => setTheme(v as Theme)}
      >
        <MenuRadioItem value="light" icon={<IconSun size={14} />}>
          Light
        </MenuRadioItem>
        <MenuRadioItem value="dark" icon={<IconMoon size={14} />}>
          Dark
        </MenuRadioItem>
        <MenuRadioItem value="system" icon={<IconMonitor size={14} />}>
          System
          <span className="ml-1.5 text-xs text-faint">
            ({resolvedTheme})
          </span>
        </MenuRadioItem>
      </MenuRadioGroup>

      <MenuSeparator />
      <MenuLabel>Density</MenuLabel>
      <MenuRadioGroup
        value={density}
        onValueChange={(v) => setDensity(v as Density)}
      >
        <MenuRadioItem value="comfortable" icon={<IconDensity size={14} />}>
          Comfortable
        </MenuRadioItem>
        <MenuRadioItem value="compact" icon={<IconDensity size={14} />}>
          Compact
        </MenuRadioItem>
      </MenuRadioGroup>

      <MenuSeparator />
      <MenuLabel>Accent</MenuLabel>
      <div className="flex items-center gap-1.5 px-2 pb-1.5 pt-0.5">
        <IconPalette size={14} className="shrink-0 text-faint" />
        {BRAND_PRESETS.map((preset) => (
          <button
            key={preset.id}
            onClick={() => setBrandHue(preset.hue)}
            aria-label={preset.label}
            title={preset.label}
            className={cn(
              "size-5 rounded-full border-2 transition-transform",
              "duration-[var(--dur-fast)] hover:scale-110",
              brandHue === preset.hue
                ? "border-fg"
                : "border-transparent"
            )}
            style={{
              // Drawn from the same OKLCH expression the ramp uses, so the
              // swatch is the colour the app will actually become.
              background: `oklch(0.596 0.13 ${preset.hue})`,
            }}
          />
        ))}
      </div>
      <div className="px-2 pb-1.5">
        <Badge tone="neutral" className="w-full justify-center" mono>
          hue {brandHue}
        </Badge>
      </div>
    </Menu>
  );
}
