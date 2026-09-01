import { useState } from "react";
import type { BatchProduct, BatchReport } from "../../api";
import { ArtAllClear } from "../../art/illustrations";
import { Badge, Code, EmptyState, Panel, Table } from "../../ui";
import { verdictBadge } from "../verdict";
import { FindingLine } from "./common";

/* The second stage: is the record complete?
 *
 * Only products that cleared the gate appear here. That is the whole reason
 * the two stages are separate screens rather than one list with a column: a
 * product stopped by a withdrawal notice is not "missing three fields", it is
 * not being onboarded, and mixing the two would invite somebody to go and fill
 * in the three fields.
 *
 * The tables below are the same figures `rollup.tally` produces for the
 * catalog-wide summary, so this screen and Product 360 cannot disagree about
 * what is missing or about who owes it.
 */

export function OnboardingTab({ report }: { report: BatchReport }) {
  const onboarding = report.products.filter((p) => p.gate?.passed);
  const totals = report.totals;

  return (
    <div className="flex flex-col gap-3">
      <Panel
        flush
        title="Every product that reached onboarding, in the order it was sent"
        subtitle={`${onboarding.length} of ${report.products.length}`}
      >
        {onboarding.length === 0 ? (
          <div className="p-3">
            <EmptyState art={<ArtAllClear />} title="Nothing reached onboarding">
              Every product in this bundle was stopped at the compliance gate.
            </EmptyState>
          </div>
        ) : (
          <div className="divide-y divide-subtle">
            {onboarding.map((product) => (
              <ProductRow
                key={product.entity_id}
                product={product}
                complete={report.checks_complete}
              />
            ))}
          </div>
        )}
      </Panel>

      <div className="grid gap-3 lg:grid-cols-2">
        <Panel title="What is missing" subtitle="by the check that found it">
          {totals.by_check.length === 0 ? (
            <EmptyState art={<ArtAllClear />} title="Nothing to fix">
              Every product that reached onboarding passed every check that ran.
            </EmptyState>
          ) : (
            <Table>
              <thead>
                <tr>
                  <th>Check</th>
                  <th className="text-right">Products</th>
                  <th className="text-right">Findings</th>
                </tr>
              </thead>
              <tbody>
                {totals.by_check.map((row) => (
                  <tr key={row.check}>
                    <td><Code>{row.check}</Code></td>
                    <td className="text-right tabular-nums">{row.products}</td>
                    <td className="text-right tabular-nums">{row.findings}</td>
                  </tr>
                ))}
              </tbody>
            </Table>
          )}
        </Panel>

        <Panel
          title="Who has to fix it"
          subtitle="the system that supplied the problem, and the team that owns it"
        >
          {totals.by_system.length === 0 ? (
            <p className="p-3 text-sm text-muted">Nothing is owed by anybody.</p>
          ) : (
            <Table>
              <thead>
                <tr>
                  <th>System</th>
                  <th>Owner</th>
                  <th className="text-right">Products</th>
                </tr>
              </thead>
              <tbody>
                {totals.by_system.map((row) => (
                  <tr key={row.system}>
                    <td><Code>{row.system}</Code></td>
                    <td className="text-muted">{row.owner ?? "—"}</td>
                    <td className="text-right tabular-nums">{row.products}</td>
                  </tr>
                ))}
              </tbody>
            </Table>
          )}
        </Panel>
      </div>

      <Panel title="By category">
        <Table>
          <thead>
            <tr>
              <th>Category</th>
              <th className="text-right">Assessed</th>
              <th className="text-right">Stopped</th>
              <th className="text-right">Cleared</th>
              <th className="text-right">Back to source</th>
              <th className="text-right">Blocked</th>
            </tr>
          </thead>
          <tbody>
            {totals.by_category.map((row) => (
              <tr key={row.prefix}>
                <td>{row.label}</td>
                <td className="text-right tabular-nums">{row.assessed}</td>
                <td className="text-right tabular-nums">{row.stopped ?? 0}</td>
                <td className="text-right tabular-nums">{row.cleared}</td>
                <td className="text-right tabular-nums">{row.returned}</td>
                <td className="text-right tabular-nums">{row.blocked}</td>
              </tr>
            ))}
          </tbody>
        </Table>
        <p className="mt-2 text-xs leading-relaxed text-faint">
          Stopped overlaps the three columns beside it rather than replacing
          them — a product a withdrawal notice stopped is both stopped and
          blocked. Making the row add up would mean one of the other numbers
          being wrong.
        </p>
      </Panel>

      {report.proposals.length > 0 && (
        <Panel
          title="Lines we do not have yet"
          subtitle="held as proposals until a reviewer accepts them"
        >
          <Table>
            <thead>
              <tr>
                <th>Proposed</th>
                <th>Category</th>
                <th>Reference</th>
              </tr>
            </thead>
            <tbody>
              {report.proposals.map((p) => (
                <tr key={p.submission_id}>
                  <td>{p.name}</td>
                  <td className="text-muted">{p.category}</td>
                  <td><Code>{p.draft_id}</Code></td>
                </tr>
              ))}
            </tbody>
          </Table>
        </Panel>
      )}
    </div>
  );
}

function ProductRow({ product, complete }: {
  product: BatchProduct; complete: boolean;
}) {
  const [open, setOpen] = useState(false);
  const badge = verdictBadge(product.verdict, complete);
  // The gate's own findings are not this screen's business - they are why a
  // product is here or not, and a product on this list cleared them.
  const findings = product.gate?.data_findings ?? product.findings;

  return (
    <div>
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-3 px-3 py-2 text-left transition-colors hover:bg-hover"
      >
        <span className="w-8 shrink-0 text-right font-mono text-xs text-faint tabular-nums">
          {product.ordinal}
        </span>
        <Code className="shrink-0">{product.sku}</Code>
        <span className="min-w-0 flex-1 truncate text-sm">{product.name}</span>
        {product.gaps > 0 && (
          <Badge tone="neutral">
            {product.gaps} gap{product.gaps === 1 ? "" : "s"}
          </Badge>
        )}
        <Badge tone={badge.tone} dot={badge.narrow}>{badge.label}</Badge>
      </button>
      {open && (
        <div className="border-t border-subtle bg-sunken px-3 py-2">
          {findings.length === 0 ? (
            <p className="text-sm text-muted">
              Nothing was found against the checks that ran.
            </p>
          ) : (
            <ul className="flex flex-col gap-1.5">
              {findings.map((f, i) => (
                <FindingLine
                  key={i}
                  detail={f.detail}
                  basis={f.basis}
                  system={f.system}
                />
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
