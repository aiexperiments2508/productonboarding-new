import { useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import { Dialog } from "radix-ui";
import { api } from "../../api";
import type { Citation } from "../../api";
import {
  IconDensity, IconDoc, IconJump, IconMonitor, IconMoon, IconPlay, IconReset,
  IconRefresh, IconSearch, IconSpark, IconStep, IconSun,
} from "../../icons";
import { useTheme } from "../../theme/ThemeProvider";
import { Badge, Code, Kbd, Spinner, cn } from "../../ui";
import { SECTIONS } from "../nav";
import type { SectionId } from "../nav";
import { docTypeLabel } from "./DocPeek";

/* Command palette.
 *
 * Two jobs, and the second is the reason it exists rather than being a nav
 * shortcut. Commands reach the tape and the correction loop from anywhere,
 * which matters because the demo is narrated from the Ingest Fabric while the
 * controls used to live two tabs away. And the search half queries the
 * reference library through /api/sop/search - a fused BM25 + dense index over
 * the content standards, the channel rules, the source-precedence policy and
 * the postmortems, which was built, served, and typed in the client, but had
 * no UI at all.
 */

interface Command {
  id: string;
  label: string;
  hint?: string;
  group: string;
  icon: ReactNode;
  run: () => void;
  /** Extra words to match on that are not in the label. */
  keywords?: string;
}

export interface PaletteActions {
  navigate: (id: SectionId) => void;
  startRun: () => void;
  replan: (reason: string) => void;
  replay: (body: { action: string; steps?: number; speed?: number }) => void;
  openCitation: (c: Citation) => void;
}

const SEARCH_DEBOUNCE_MS = 220;
const MIN_QUERY = 2;

export function CommandPalette({
  open, onOpenChange, actions,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  actions: PaletteActions;
}) {
  const { theme, setTheme, density, setDensity } = useTheme();
  const [query, setQuery] = useState("");
  const [cursor, setCursor] = useState(0);
  const [docs, setDocs] = useState<Citation[]>([]);
  const [searching, setSearching] = useState(false);
  const listRef = useRef<HTMLDivElement>(null);

  const commands = useMemo<Command[]>(() => {
    const close = (fn: () => void) => () => {
      onOpenChange(false);
      fn();
    };
    return [
      ...SECTIONS.map((s) => ({
        id: `go:${s.id}`,
        label: s.label,
        group: "Go to",
        icon: <s.Icon size={15} />,
        keywords: s.description,
        run: close(() => actions.navigate(s.id)),
      })),
      {
        id: "run",
        label: "Work the correction",
        hint: "read the document, trace what it reaches, validate every resolution",
        group: "Correction",
        icon: <IconSpark size={15} />,
        keywords:
          "run start loop blast radius supplier spec sheet detect investigate " +
          "simulate recommend propagate",
        run: close(actions.startRun),
      },
      {
        id: "replan",
        label: "Revise on new evidence",
        hint: "same correction, next revision - keeps the earlier reading for comparison",
        group: "Correction",
        icon: <IconRefresh size={15} />,
        keywords:
          "re-plan replan revision update rerun clarification rejection " +
          "changed diff variant scope",
        run: close(() => actions.replan("run from the command palette")),
      },
      {
        id: "replay:start",
        label: "Start the replay clock",
        group: "Replay",
        icon: <IconPlay size={15} />,
        keywords: "play tape documents feed resume run the days",
        run: close(() => actions.replay({ action: "START" })),
      },
      {
        id: "replay:step",
        label: "Release one event",
        hint: "how the supplier document gets narrated",
        group: "Replay",
        icon: <IconStep size={15} />,
        keywords: "step advance next single tape document feed",
        run: close(() => actions.replay({ action: "STEP", steps: 1 })),
      },
      {
        id: "replay:step10",
        label: "Release ten events",
        group: "Replay",
        icon: <IconStep size={15} />,
        keywords: "step advance tape skip routine noise",
        run: close(() => actions.replay({ action: "STEP", steps: 10 })),
      },
      {
        id: "replay:jump",
        label: "Jump to the corrected spec sheet",
        hint: "release every document up to the correction",
        group: "Replay",
        icon: <IconJump size={15} />,
        keywords: "skip inject finale fast forward supplier correction 65 W",
        run: close(() => actions.replay({ action: "JUMP" })),
      },
      {
        id: "replay:reset",
        label: "Rewind the tape",
        hint: "back to day one, released documents cleared",
        group: "Replay",
        icon: <IconReset size={15} />,
        keywords: "reset restart clear tape start over",
        run: close(() => actions.replay({ action: "RESET" })),
      },
      {
        id: "theme",
        label: `Switch to ${theme === "dark" ? "light" : theme === "light" ? "system" : "dark"} theme`,
        group: "Appearance",
        icon:
          theme === "dark" ? <IconSun size={15} />
          : theme === "light" ? <IconMonitor size={15} />
          : <IconMoon size={15} />,
        keywords: "dark light system colour color appearance",
        run: close(() =>
          setTheme(theme === "dark" ? "light" : theme === "light" ? "system" : "dark")
        ),
      },
      {
        id: "density",
        label: `Switch to ${density === "compact" ? "comfortable" : "compact"} density`,
        group: "Appearance",
        icon: <IconDensity size={15} />,
        keywords: "spacing rows compact comfortable size",
        run: close(() =>
          setDensity(density === "compact" ? "comfortable" : "compact")
        ),
      },
    ];
  }, [actions, onOpenChange, theme, setTheme, density, setDensity]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return commands;
    return commands.filter((c) =>
      `${c.label} ${c.group} ${c.keywords ?? ""}`.toLowerCase().includes(q)
    );
  }, [commands, query]);

  // Reference search. Debounced, and every response checks that it is still the
  // one being awaited - a fast typist outruns the round trip, and without the
  // guard an earlier query can overwrite a later one's results.
  useEffect(() => {
    const q = query.trim();
    if (q.length < MIN_QUERY) {
      setDocs([]);
      setSearching(false);
      return;
    }
    setSearching(true);
    let live = true;
    const timer = setTimeout(() => {
      api
        .sopSearch(q, { top_k: 5 })
        .then((r) => {
          if (live) setDocs(r.results);
        })
        .catch(() => {
          if (live) setDocs([]);
        })
        .finally(() => {
          if (live) setSearching(false);
        });
    }, SEARCH_DEBOUNCE_MS);
    return () => {
      live = false;
      clearTimeout(timer);
    };
  }, [query]);

  const rows = useMemo(
    () => [
      ...filtered.map((c) => ({ kind: "command" as const, command: c })),
      ...docs.map((d) => ({ kind: "doc" as const, doc: d })),
    ],
    [filtered, docs]
  );

  useEffect(() => setCursor(0), [query]);
  useEffect(() => {
    if (!open) setQuery("");
  }, [open]);

  // Keep the highlighted row in view when arrowing past the fold.
  useEffect(() => {
    listRef.current
      ?.querySelector<HTMLElement>('[data-active="true"]')
      ?.scrollIntoView({ block: "nearest" });
  }, [cursor]);

  function onKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setCursor((c) => (rows.length ? (c + 1) % rows.length : 0));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setCursor((c) => (rows.length ? (c - 1 + rows.length) % rows.length : 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      activate(cursor);
    }
  }

  function activate(index: number) {
    const row = rows[index];
    if (!row) return;
    if (row.kind === "command") row.command.run();
    else {
      onOpenChange(false);
      actions.openCitation(row.doc);
    }
  }

  let lastGroup = "";

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay
          className={cn(
            "fixed inset-0 z-[var(--z-dialog)] bg-scrim backdrop-blur-[2px]",
            "data-[state=open]:animate-fade-in"
          )}
        />
        <Dialog.Content
          className={cn(
            "fixed left-1/2 top-[14vh] z-[var(--z-dialog)] w-[min(620px,calc(100vw-24px))]",
            "-translate-x-1/2 overflow-hidden rounded-lg border border-strong",
            "bg-overlay shadow-e3 data-[state=open]:animate-scale-in"
          )}
        >
          <Dialog.Title className="sr-only">Command palette</Dialog.Title>
          <Dialog.Description className="sr-only">
            Jump to a section, drive the replay, or search the content standards
            and channel rules.
          </Dialog.Description>

          <div className="flex items-center gap-2.5 border-b border-subtle px-3.5">
            <IconSearch size={16} className="shrink-0 text-faint" />
            <input
              autoFocus
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              // On the input, not on Dialog.Content. Focus lives here for the
              // whole life of the palette, and Radix's Content composes its own
              // dismiss handling over anything passed to it - a keydown handler
              // up there does not reliably see Enter.
              onKeyDown={onKeyDown}
              placeholder="Search commands, standards and channel rules…"
              aria-label="Search commands, standards and channel rules"
              className={cn(
                "h-11 min-w-0 flex-1 bg-transparent text-md text-fg outline-none",
                "placeholder:text-faint"
              )}
            />
            {searching && <Spinner size={13} />}
            <Kbd>esc</Kbd>
          </div>

          <div ref={listRef} className="max-h-[52vh] overflow-y-auto p-1.5">
            {rows.length === 0 && (
              <div className="px-3 py-8 text-center text-sm text-muted">
                {query.trim().length >= MIN_QUERY
                  ? "Nothing matches, in the commands or the reference library."
                  : "No matching command."}
              </div>
            )}

            {rows.map((row, i) => {
              const group =
                row.kind === "command" ? row.command.group : "Reference library";
              const header = group !== lastGroup ? group : null;
              lastGroup = group;
              const active = i === cursor;

              return (
                <div key={row.kind === "command" ? row.command.id : row.doc.chunk_id}>
                  {header && (
                    <div className="px-2 pb-1 pt-2 text-2xs font-semibold uppercase tracking-caps text-faint">
                      {header}
                    </div>
                  )}
                  <button
                    data-active={active}
                    onMouseMove={() => setCursor(i)}
                    onClick={() => activate(i)}
                    className={cn(
                      "flex w-full items-center gap-2.5 rounded-sm px-2 py-2 text-left",
                      "transition-colors duration-[var(--dur-fast)]",
                      active ? "bg-hover" : "hover:bg-hover"
                    )}
                  >
                    <span className="shrink-0 text-faint">
                      {row.kind === "command" ? row.command.icon : <IconDoc size={15} />}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-base text-fg">
                        {row.kind === "command"
                          ? row.command.label
                          : row.doc.heading || row.doc.title}
                      </span>
                      {row.kind === "command"
                        ? row.command.hint && (
                            <span className="block truncate text-xs text-faint">
                              {row.command.hint}
                            </span>
                          )
                        : (
                            // The document id rides with the excerpt: reviewers
                            // cite by id, and the heading alone is not citable.
                            <span className="flex min-w-0 items-baseline gap-1.5 text-xs text-faint">
                              <Code className="shrink-0">{row.doc.doc_id}</Code>
                              <span className="min-w-0 truncate">
                                {row.doc.excerpt}
                              </span>
                            </span>
                          )}
                    </span>
                    {row.kind === "doc" && (
                      <Badge tone="neutral" className="shrink-0">
                        {docTypeLabel(row.doc.doc_type)}
                      </Badge>
                    )}
                  </button>
                </div>
              );
            })}
          </div>

          <div className="flex items-center gap-3 border-t border-subtle px-3 py-1.5 text-2xs text-faint">
            <span className="flex items-center gap-1">
              <Kbd>↑</Kbd>
              <Kbd>↓</Kbd> navigate
            </span>
            <span className="flex items-center gap-1">
              <Kbd>↵</Kbd> run
            </span>
            <span className="ml-auto">
              standards, channel rules and postmortems — BM25 + dense, fused
            </span>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
