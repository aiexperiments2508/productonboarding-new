import { useCallback, useState } from "react";
import { api } from "../api";
import type { RCAReport } from "../api";
import { IconSpark } from "../icons";
import { Badge, Button, Code, SkeletonText, Tooltip, cn, useToast } from "../ui";

/* Why the findings happened, and who has to fix them.
 *
 * A finding says what is wrong and names the system that carried the value.
 * That is already more than most tools manage, and it still leaves a reviewer
 * holding eleven rows and no idea which supplier to email first.
 *
 * This joins the finding to the estate's own declaration about that system -
 * what it is for, who owns it, and how it is known to misbehave - and asks a
 * model to put the two together in a sentence. The model is fenced the way
 * everything else here is fenced: it may only use the finding, the system's
 * declared behaviour and a passage that was actually retrieved, and an account
 * citing nothing retrievable is dropped rather than softened.
 *
 * Which is why the panel still works with no gateway at all. The manifest
 * alone answers "what is the root cause and who fixes it"; the model only
 * writes it better. `written_by_model` says which one you are reading, and the
 * grounding is identical either way.
 *
 * Fetched on demand rather than with the assessment. The assessment is the
 * fast path and this is a second question, asked by somebody who has decided
 * the first answer was interesting.
 */

export function RootCausePanel({ entityId, findings }: {
  entityId: string;
  /** How many findings are open. Nothing to explain about a clean record. */
  findings: number;
}) {
  const toast = useToast();
  const [report, setReport] = useState<RCAReport | null>(null);
  const [busy, setBusy] = useState(false);

  const run = useCallback(async () => {
    setBusy(true);
    try {
      setReport(await api.rca(entityId, true, 3));
    } catch (e) {
      toast.error("Could not work out the root cause", String(e));
    } finally {
      setBusy(false);
    }
  }, [entityId, toast]);

  if (findings === 0) return null;

  if (!report && !busy) {
    return (
      <div className="mt-3 flex items-center gap-2 rounded-sm border border-subtle bg-sunken px-2.5 py-2">
        <span className="min-w-0 flex-1 text-xs text-muted">
          {findings} open finding{findings === 1 ? "" : "s"}. Ask what is
          upstream of {findings === 1 ? "it" : "them"}, and who has to fix it.
        </span>
        <Button size="xs" tone="primary" onClick={run}
                icon={<IconSpark size={13} />}>
          Suggest a root cause
        </Button>
      </div>
    );
  }

  return (
    <div className="mt-3 flex flex-col gap-2">
      <div className="flex items-center gap-2">
        <h3 className="text-xs font-semibold uppercase tracking-caps text-faint">
          Likely root cause
        </h3>
        <span className="h-px flex-1 bg-subtle" />
        {report && (
          <Button size="xs" tone="ghost" onClick={run} loading={busy}>
            re-run
          </Button>
        )}
      </div>

      {busy && !report ? (
        <div className="rounded-sm border border-subtle bg-sunken p-2.5">
          <SkeletonText lines={3} />
        </div>
      ) : (
        <>
          {report?.causes.map((cause) => (
            <div
              key={`${cause.check}-${cause.subject}`}
              className={cn(
                "rounded-sm border-l-2 bg-sunken px-2.5 py-2",
                cause.severity === "BLOCKING" ? "border-danger" : "border-warn",
              )}
            >
              <div className="flex flex-wrap items-baseline gap-2">
                <Code>{cause.check}</Code>
                <span className="font-mono text-2xs text-faint">
                  {cause.subject}
                </span>
                {cause.likely_defect && (
                  <Tooltip content={cause.defect_explanation}>
                    <span><Badge tone="warn">{cause.likely_defect}</Badge></span>
                  </Tooltip>
                )}
                {!cause.written_by_model && (
                  <Tooltip content={cause.note}>
                    <span><Badge tone="neutral">no model</Badge></span>
                  </Tooltip>
                )}
              </div>

              <p className="mt-1 text-xs text-fg">{cause.narrative}</p>

              <p className="mt-1.5 text-xs text-muted">
                <span className="text-2xs uppercase tracking-caps text-faint">
                  what fixes it{" "}
                </span>
                {cause.remedy}
              </p>

              <p className="mt-1.5 flex flex-wrap items-center gap-1.5 text-2xs text-faint">
                {cause.owner && <Badge tone="info">{cause.owner}</Badge>}
                {cause.system && <Code>{cause.system}</Code>}
                {cause.defect_rate != null && (
                  <span>
                    {Math.round(cause.defect_rate * 100)}% of what this system
                    sends carries a defect
                  </span>
                )}
                {cause.citation && (
                  <span className="ml-auto">
                    from <Code>{cause.citation}</Code>
                  </span>
                )}
              </p>
            </div>
          ))}

          {/* Said out loud rather than left as three of eleven. A panel that
              quietly stops at three reads as a product with three problems. */}
          {(report?.not_explained ?? 0) > 0 && (
            <p className="text-2xs text-faint">
              {report?.not_explained} further finding
              {report?.not_explained === 1 ? "" : "s"} not explained here — the
              worst are shown first.
            </p>
          )}
          {(report?.unattributed ?? 0) > 0 && (
            <p className="text-2xs text-faint">
              {report?.unattributed} finding
              {report?.unattributed === 1 ? " names" : "s name"} no system, so
              nobody can be asked to fix{" "}
              {report?.unattributed === 1 ? "it" : "them"} yet.
            </p>
          )}
        </>
      )}
    </div>
  );
}
