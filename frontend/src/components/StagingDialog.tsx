import { Dialog } from "radix-ui";
import type { Preview } from "../api";
import { IconClose } from "../icons";
import {
  Badge, Button, Code, LoadingBody, Skeleton, SkeletonText, cn,
} from "../ui";
import { MediaStrip } from "./MediaStrip";
import { verdictBadge } from "./verdict";

/* The staging page, as a dialog.
 *
 * It used to be a panel appended to the bottom of the right-hand column, below
 * two other panels - so "show me what this would look like" scrolled the
 * answer off the screen, and the reviewer had to go and find it. It is a
 * modal now: this is a distinct act with a beginning and an end, and it is the
 * last thing anybody looks at before a launch.
 *
 * **It opens before the answer arrives.** The old button set no busy flag,
 * disabled nothing and rendered nothing until the request resolved, which on
 * the slowest interaction in the application meant clicking and watching an
 * unchanged screen. The dialog now opens on the click, in the shape of the
 * page that is coming, and fills in.
 *
 * The refusal is still the whole response rather than a banner over a rendered
 * one. A page that renders a blocked product with a warning across the top is
 * a page somebody screenshots.
 */

export function StagingDialog({
  open, onOpenChange, preview, loading, title,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  preview: Preview | null;
  loading: boolean;
  /** Known before the request lands, so the header is never empty. */
  title: string;
}) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay
          className={cn(
            "fixed inset-0 z-[var(--z-dialog)] bg-scrim",
            "data-[state=open]:animate-fade-in",
          )}
        />
        <Dialog.Content
          className={cn(
            "fixed left-1/2 top-1/2 z-[var(--z-dialog)]",
            "flex w-[min(760px,calc(100vw-24px))] max-h-[85vh] -translate-x-1/2",
            "-translate-y-1/2 flex-col overflow-hidden rounded-lg",
            "border border-strong bg-overlay shadow-e3",
            "data-[state=open]:animate-scale-in",
          )}
        >
          <div className="flex shrink-0 items-start gap-2.5 border-b border-subtle p-3.5">
            <div className="min-w-0 flex-1">
              <Dialog.Title className="truncate text-md font-semibold text-fg">
                Staging page
              </Dialog.Title>
              <Dialog.Description className="mt-0.5 truncate text-xs text-faint">
                {loading
                  ? `Building what ${title} would look like…`
                  : preview?.rendered
                  ? "What the listing would look like, from the record as it stands"
                  : "Not available"}
              </Dialog.Description>
            </div>
            {!loading && preview?.rendered && (
              <Badge tone="ok" dot>ready</Badge>
            )}
            <Dialog.Close asChild>
              <Button tone="ghost" size="xs" iconOnly aria-label="Close"
                      icon={<IconClose size={14} />} />
            </Dialog.Close>
          </div>

          <div className="min-h-0 flex-1 overflow-y-auto p-4">
            {loading ? <StagingSkeleton /> : <StagingBody preview={preview} />}
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

/** The shape of the page that is coming, so the layout does not jump when it
 *  lands and the reviewer can see what they asked for is being built. */
function StagingSkeleton() {
  return (
    <LoadingBody label="Building the staging page">
      <div className="flex flex-col gap-4">
        <div>
          <Skeleton className="h-6 w-2/5" />
          <Skeleton className="mt-1.5 h-3 w-1/4" />
        </div>
        <Skeleton className="h-20 w-full" rounded="md" />
        <MediaStrip loading />
        <div className="grid grid-cols-2 gap-x-4 gap-y-2">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="contents">
              <Skeleton className="h-3 w-2/3" />
              <Skeleton className="h-3 w-1/2" />
            </div>
          ))}
        </div>
        <SkeletonText lines={2} />
      </div>
    </LoadingBody>
  );
}

function StagingBody({ preview }: { preview: Preview | null }) {
  if (!preview) {
    return (
      <p className="text-sm text-muted">
        Nothing to show. The request did not return a page.
      </p>
    );
  }

  if (!preview.rendered) {
    const badge = verdictBadge(preview.verdict, true);
    return (
      <div className="flex flex-col gap-2">
        <p className="text-sm text-muted">
          {preview.reason}. This product is{" "}
          <strong className="text-warn-text">{badge.label}</strong> with{" "}
          {preview.findings?.length ?? 0} open finding
          {(preview.findings?.length ?? 0) === 1 ? "" : "s"}.
        </p>
        {(preview.findings ?? []).length > 0 && (
          <ul className="flex flex-col gap-1.5">
            {(preview.findings ?? []).map((finding) => (
              <li
                key={`${finding.check}-${finding.subject}`}
                className={cn(
                  "rounded-sm border-l-2 bg-sunken px-2 py-1.5",
                  finding.severity === "BLOCKING"
                    ? "border-danger" : "border-warn",
                )}
              >
                <div className="flex flex-wrap items-baseline gap-2">
                  <Code>{finding.check}</Code>
                  <span className="font-mono text-2xs text-faint">
                    {finding.subject}
                  </span>
                  {finding.system && <Badge tone="info">{finding.system}</Badge>}
                </div>
                <p className="mt-0.5 text-xs text-muted">{finding.detail}</p>
              </li>
            ))}
          </ul>
        )}
      </div>
    );
  }

  const differentiator = preview.differentiator;
  return (
    <article className="flex flex-col gap-4">
      <header>
        <h3 className="text-lg font-semibold text-fg">{preview.title}</h3>
        <p className="font-mono text-2xs text-faint">
          {preview.sku} · {preview.category}
        </p>
      </header>

      {/* The differentiator, and its grounds shown beside it rather than
          hidden. A claim a reviewer cannot trace is a claim they cannot
          approve. */}
      {differentiator && (
        <div className="rounded-md border border-accent-border bg-accent-soft p-3">
          <p className="text-2xs uppercase tracking-caps text-accent-text">
            why somebody buys this
          </p>
          <p className="mt-1 text-sm text-fg">{differentiator.text}</p>
          <p className="mt-2 flex flex-wrap items-center gap-1.5 text-2xs text-muted">
            <span>grounded in</span>
            {differentiator.attributes.map((a) => <Code key={a}>{a}</Code>)}
            <span>and</span>
            <Code>{differentiator.source}</Code>
            {!differentiator.written_by_model && (
              <Badge tone="neutral">{differentiator.note}</Badge>
            )}
          </p>
        </div>
      )}

      <MediaStrip media={preview.media} />

      <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
        {(preview.specification ?? []).map((row) => (
          <div key={row.path} className="contents">
            <dt className="text-muted">{row.label}</dt>
            <dd className="font-mono text-fg">
              {String(row.value)}{row.unit ? ` ${row.unit}` : ""}
            </dd>
          </div>
        ))}
      </dl>

      {(preview.claims ?? []).length > 0 && (
        <p className="flex flex-wrap items-center gap-1.5">
          {(preview.claims ?? []).map((c) => (
            <Badge key={c} tone="ok">{c}</Badge>
          ))}
        </p>
      )}
    </article>
  );
}
