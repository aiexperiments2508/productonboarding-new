import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import type { AutonomyThreshold } from "../api";
import { IconCheck } from "../icons";
import { Button, Code, Field, Panel, Skeleton, cn, useToast } from "../ui";

/* The autonomy threshold.
 *
 * One number, and it decides more than any other control in this product: at
 * or above it a proposed value for a missing field is recorded without anybody
 * looking at it. So it lives here, beside the model gateway and the retrieval
 * index, rather than on the screen where the decisions are made - moving it is
 * a policy change, not part of working a queue.
 *
 * Three things this panel has to say out loud, because a bare slider would
 * imply the opposite of each:
 *
 *   the threshold is not the only gate. A safety-class attribute is decided by
 *   a person whatever it scores, and so is any value only one source supports.
 *   Both are structural and neither moves with this number.
 *
 *   the score it is applied to is not a model's own confidence. It is composed
 *   from a discounted self-report plus counts of what is already on file, and
 *   the parts are on every proposal.
 *
 *   moving it is recorded. "Why was this written without anybody approving it"
 *   is answered by the threshold in force at the time, and a threshold with no
 *   history cannot answer it - which is why this asks for a name.
 */

//: The stops offered. Not a free slider: the difference between 0.94 and 0.95
//: is not a policy anybody holds, and offering it invites a precision the
//: score does not have.
const STOPS = [0.8, 0.85, 0.9, 0.95, 1.0];

export function AutonomyPanel() {
  const toast = useToast();
  const [policy, setPolicy] = useState<AutonomyThreshold | null>(null);
  const [actor, setActor] = useState("");
  const [working, setWorking] = useState<number | null>(null);

  const refresh = useCallback(() => {
    api.autonomyThreshold().then(setPolicy).catch(() => undefined);
  }, []);
  useEffect(refresh, [refresh]);

  const move = useCallback((wanted: number) => {
    if (!actor.trim()) return;
    setWorking(wanted);
    api.setAutonomyThreshold({ threshold: wanted, actor: actor.trim() })
      .then((result) => {
        toast.notify(
          `the autonomy threshold is ${Math.round(result.threshold * 100)}%`,
          `was ${Math.round(result.previous * 100)}% — the change is in the `
          + "audit ledger against your name");
        refresh();
      })
      .catch((e) => toast.error("Could not move the threshold", String(e)))
      .finally(() => setWorking(null));
  }, [actor, refresh, toast]);

  return (
    <Panel
      title="Autonomous approval"
      subtitle={policy ? `${Math.round(policy.threshold * 100)}% in force` : undefined}
    >
      {!policy ? (
        <div className="flex flex-col gap-2">
          <Skeleton className="h-4 w-2/5" />
          <Skeleton className="h-7 w-full" />
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          <p className="text-sm leading-relaxed text-muted">
            A proposed value for a missing field is recorded without a reviewer
            when its score reaches this. Below it, the proposal goes to a
            category manager in Supplier Intake with the evidence its score was
            composed from.
          </p>

          <Field label="Threshold">
            <div className="flex flex-wrap items-center gap-1.5">
              {STOPS.map((stop) => {
                const active = Math.abs(policy.threshold - stop) < 0.001;
                return (
                  <Button
                    key={stop}
                    size="sm"
                    tone={active ? "primary" : undefined}
                    loading={working === stop}
                    disabled={!actor.trim() || active}
                    icon={active ? <IconCheck size={13} /> : undefined}
                    onClick={() => move(stop)}
                  >
                    {Math.round(stop * 100)}%
                  </Button>
                );
              })}
              {Math.round(policy.threshold * 100) !== Math.round(policy.default * 100) && (
                <span className="text-xs text-faint">
                  default is {Math.round(policy.default * 100)}%
                </span>
              )}
            </div>
          </Field>

          <label className="flex max-w-xs flex-col gap-1 text-sm">
            <span className="text-muted">Who is changing it</span>
            <input
              value={actor}
              onChange={(e) => setActor(e.target.value)}
              placeholder="your name"
              className={cn(
                "rounded-md border border-subtle bg-raised px-2 py-1",
                "focus:outline-none focus:ring-2 focus:ring-focus"
              )}
            />
          </label>

          <div className="border-t border-subtle pt-3">
            <p className="text-sm leading-relaxed text-muted">
              <strong className="text-default">
                This number is not the only thing standing in the way.
              </strong>{" "}
              A safety-class attribute is decided by a person whatever it
              scores, and so is any value fewer than{" "}
              <Code>{policy.min_sources}</Code> independent sources agree with.
              Both are structural: turning this down cannot reach past either of
              them.
            </p>
            <p className="mt-2 text-sm leading-relaxed text-muted">
              The score it is applied to is not a model's own confidence —
              that is discounted and counts for part of it. The rest is a count
              of what the catalog, the category and your own past decisions
              already say, which is what makes the number checkable rather than
              fluent.
            </p>
            <p className="mt-2 text-xs leading-relaxed text-faint">
              Moving this is recorded in the audit ledger against the name
              above, because it is the answer to "why was this written without
              anybody approving it".
            </p>
          </div>
        </div>
      )}
    </Panel>
  );
}
