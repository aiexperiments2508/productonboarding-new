import { useState } from "react";
import type { TowerSpend } from "../../api";
import {
  Button, EmptyState, Panel, SegmentedControl, Table, Td, Th, Tooltip, Tr,
  cn, useToast,
} from "../../ui";
import { Caveat, Tile, tokens, usd } from "./common";

/* What the models cost, and the one control that goes with it.
 *
 * Two figures that must never be added together sit at the top: what was spent,
 * and what the response cache saved. They are two sums over one ledger - a
 * cache hit is recorded with its tokens intact and no cost - and putting them
 * side by side is both the honest reading and the flattering one, which is the
 * only reason to prefer it.
 *
 * The cap is here rather than in System Control because this is where somebody
 * looking at the bill is standing. It demands a name, like the autonomy
 * threshold does, and for the same reason: moving a control that changes what
 * the system does unattended is a decision with a person behind it.
 */

const GROUPS = [
  { value: "model", label: "Model", title: "Which model the spend went to" },
  { value: "surface", label: "Surface",
    title: "Which part of the system asked - readiness, onboarding, the graph, chat" },
  { value: "feed", label: "Feed", title: "Which supplier archive caused it" },
  { value: "kind", label: "Kind", title: "Completions against embeddings" },
] as const;

export function CostTab({ data, groupBy, onGroupBy, onBudget }: {
  data: TowerSpend | null;
  groupBy: string;
  onGroupBy: (g: string) => void;
  onBudget: (usd: number | null, actor: string,
             tokens: number | null) => Promise<void>;
}) {
  if (!data) return null;

  return (
    <div className="flex flex-col gap-3">
      <Panel
        title="Spend"
        subtitle={
          "What left for the gateway, and what the cache answered instead. "
          + "The two are separate sums over one ledger and must not be added."
        }
      >
        <div className="grid grid-cols-[repeat(auto-fit,minmax(140px,1fr))] gap-2">
          <Tile label="Spent" value={usd(data.cost_usd)}
                sub={`${data.live_calls} calls`}
                tone={data.priced ? undefined : "bad"} />
          <Tile label="Avoided by cache" value={usd(data.cost_avoided_usd)}
                sub={`${data.cache_hits} hits`} tone="good" />
          <Tile label="Tokens" value={tokens(data.tokens)}
                sub={`${tokens(data.prompt_tokens)} in · ${tokens(data.completion_tokens)} out`} />
          <Tile label="Tokens avoided" value={tokens(data.tokens_avoided)}
                sub="served from cache" tone="good" />
          <Tile label="Avg latency"
                value={data.avg_latency_ms ? `${Math.round(data.avg_latency_ms)} ms` : "—"}
                sub="live calls only" />
        </div>
        <Caveat text={data.caveat} className="mt-2" />
      </Panel>

      <Panel
        title="Where it went"
        subtitle="Grouped four ways. Cost descending, so the first row is the one worth looking at."
        actions={
          <SegmentedControl
            value={groupBy}
            onChange={onGroupBy}
            options={GROUPS.map((g) => ({
              value: g.value, label: g.label, title: g.title,
            }))}
            ariaLabel="Group spend by"
          />
        }
        flush
      >
        {data.groups.length ? (
          <Table>
            <thead>
              <Tr>
                <Th>{GROUPS.find((g) => g.value === groupBy)?.label ?? "Key"}</Th>
                <Th num>Calls</Th>
                <Th num>Cache hits</Th>
                <Th num>Tokens</Th>
                <Th num>Cost</Th>
                <Th num>
                  <Tooltip content="What these calls cost the day they were real. Read off the cache's own record, never re-estimated.">
                    <span>Avoided</span>
                  </Tooltip>
                </Th>
              </Tr>
            </thead>
            <tbody>
              {data.groups.map((row) => (
                <Tr key={row.key}>
                  <Td className="font-mono text-sm">{row.key}</Td>
                  <Td num>{row.calls}</Td>
                  <Td num className={row.cache_hits ? undefined : "text-faint"}>
                    {row.cache_hits || "—"}
                  </Td>
                  <Td num>{tokens(row.tokens)}</Td>
                  <Td num>{usd(row.cost_usd)}</Td>
                  <Td num className={cn(row.cost_avoided_usd ? "text-ok-text" : "text-faint")}>
                    {row.cost_avoided_usd ? usd(row.cost_avoided_usd) : "—"}
                  </Td>
                </Tr>
              ))}
            </tbody>
          </Table>
        ) : (
          <EmptyState
            compact
            title="No model call in this window"
            children="Nothing was asked of a model between these dates - which is not the same as it having been free."
          />
        )}
      </Panel>

      <BudgetPanel budget={data.budget} onBudget={onBudget} />
    </div>
  );
}

const capInput = (width: string) => cn(
  width,
  "rounded-sm border border-line bg-canvas px-2 py-1",
  "font-mono text-2xs text-fg placeholder:text-faint",
  "focus:outline-none focus:ring-2 focus:ring-focus"
);

/** The cap.
 *
 * Deliberately soft. A breached cap raises the same error an unreachable
 * gateway raises, so every deterministic fallback already written runs and the
 * work continues, narrower. A control that halted the factory would be turned
 * off within a day of somebody meeting it.
 */
function BudgetPanel({ budget, onBudget }: {
  budget: TowerSpend["budget"];
  onBudget: (usd: number | null, actor: string,
             tokens: number | null) => Promise<void>;
}) {
  const [amount, setAmount] = useState("");
  const [tokenCap, setTokenCap] = useState("");
  const [actor, setActor] = useState("");
  const [busy, setBusy] = useState(false);
  const toast = useToast();

  const submit = async (usd: number | null, tokens: number | null) => {
    if (!actor.trim()) {
      toast.error("Moving the cap is audited, so it needs a name");
      return;
    }
    setBusy(true);
    try {
      await onBudget(usd, actor.trim(), tokens);
      setAmount("");
      setTokenCap("");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Panel
      title="Spend cap"
      subtitle={
        "A soft cap. Past it the gateway refuses the way an unreachable gateway "
        + "refuses, so the deterministic fallbacks run and the work continues "
        + "with narrower answers rather than stopping."
      }
    >
      <div className="flex flex-col gap-3">
        <div className="grid grid-cols-[repeat(auto-fit,minmax(140px,1fr))] gap-2">
          <Tile label="Cap — money"
                value={budget.limit_usd === null ? "none" : usd(budget.limit_usd)}
                tone={budget.exceeded_by === "cost" ? "bad" : undefined}
                sub={`${usd(budget.spent_usd)} spent · ${budget.calls} calls`} />
          <Tooltip content="Not decoration. Cost comes from the gateway's own price map, and a model it does not recognise returns none - so on this deployment a money cap can never be reached and a token cap is the only one that can fire.">
            <div>
              <Tile label="Cap — tokens"
                    value={budget.limit_tokens === null
                      ? "none" : budget.limit_tokens.toLocaleString()}
                    tone={budget.exceeded_by === "tokens" ? "bad" : undefined}
                    sub={`${budget.spent_tokens.toLocaleString()} used`} />
            </div>
          </Tooltip>
          <Tile label="Status"
                value={budget.exceeded ? "reached" : "under"}
                tone={budget.exceeded ? "bad" : undefined}
                sub={budget.since
                  ? `set ${budget.since.slice(0, 16).replace("T", " ")}`
                  : "no cap set"} />
        </div>

        <p className="text-2xs leading-relaxed text-faint">
          Either cap is enough on its own. The meter starts when a cap is set,
          not at the beginning of time — an operator setting a limit means{" "}
          <em>from here</em>, and measuring it against spend that had already
          happened would make a new cap read as instantly breached.
        </p>

        <div className="flex flex-wrap items-center gap-2">
          <input
            value={actor}
            onChange={(e) => setActor(e.target.value)}
            placeholder="your name"
            aria-label="Who is setting the cap"
            className={capInput("w-32")}
          />
          <input
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            inputMode="decimal"
            placeholder="$5.00"
            aria-label="Cap in US dollars"
            className={capInput("w-20")}
          />
          <input
            value={tokenCap}
            onChange={(e) => setTokenCap(e.target.value)}
            inputMode="numeric"
            placeholder="50000 tokens"
            aria-label="Cap in tokens"
            className={capInput("w-28")}
          />
          <Button
            size="sm"
            disabled={busy || (!amount.trim() && !tokenCap.trim())}
            onClick={() => {
              const money = amount.trim() ? Number(amount) : null;
              const toks = tokenCap.trim() ? Number(tokenCap) : null;
              if (money !== null && (!Number.isFinite(money) || money <= 0)) {
                toast.error("A money cap has to be a number above zero");
                return;
              }
              if (toks !== null && (!Number.isInteger(toks) || toks <= 0)) {
                toast.error("A token cap has to be a whole number above zero");
                return;
              }
              void submit(money, toks);
            }}
          >
            Set the cap
          </Button>
          {(budget.limit_usd !== null || budget.limit_tokens !== null) && (
            <Button size="sm" tone="ghost" disabled={busy}
                    onClick={() => void submit(null, null)}>
              Clear it
            </Button>
          )}
        </div>
      </div>
    </Panel>
  );
}
