import type { BatchProduct, BatchReport } from "../../api";
import { ArtAllClear } from "../../art/illustrations";
import { IconCheck } from "../../icons";
import { Badge, Code, EmptyState, Panel, cn } from "../../ui";
import { AuthorityTag, FindingLine } from "./common";

/* The first stage: may we onboard this at all?
 *
 * Every product in the bundle is checked against regulation and against the
 * retailer's own policy before anything looks at whether its record is
 * complete. A product that fails goes back to the supplier, and this screen is
 * where the reason it goes back is written down.
 *
 * The distinction the layout is built around is the one a supplier most needs
 * and could least infer: a **regulation** is not something they can argue with
 * by sending more data, and a **policy** is a rule this organisation set. Both
 * stop the product; only one of them is the law. So the authority is on the
 * row, and the clause it rests on is beside the sentence.
 *
 * Stopped products are listed first and in full. The ones that cleared are a
 * count and a list of names - nobody reads forty rows saying nothing happened,
 * and burying eight refusals underneath them is how a screen stops being read.
 */

export function GateTab({ report }: { report: BatchReport }) {
  const stopped = report.products.filter((p) => !p.gate?.passed);
  const passed = report.products.filter((p) => p.gate?.passed);

  return (
    <div className="flex flex-col gap-3">
      {stopped.length === 0 ? (
        <Panel title="Nothing was stopped">
          <EmptyState art={<ArtAllClear />} title="Every product may be onboarded">
            No regulation and no policy refused anything in this bundle
            {report.checks_complete
              ? "."
              : " — against the checks that ran. The two that read regulation "
                + "and policy need a model and have not been run for this "
                + "batch, so this is a narrower answer rather than a clean one."}
          </EmptyState>
        </Panel>
      ) : (
        <Panel
          flush
          tone="danger"
          title={`${stopped.length} product${stopped.length === 1 ? "" : "s"} stopped before onboarding`}
          subtitle={`going back to ${report.supplier}`}
        >
          <div className="divide-y divide-subtle">
            {stopped.map((product) => (
              <StoppedRow key={product.entity_id} product={product}
                          supplier={report.supplier} />
            ))}
          </div>
          <p className="border-t border-subtle px-3 py-2 text-xs leading-relaxed text-faint">
            Nothing downstream has been spent on these. No source was retrieved
            for them and no value proposed — a product going back to its
            supplier does not need a suggested wattage, and producing one would
            be work somebody then has to read.
          </p>
        </Panel>
      )}

      <Panel
        flush
        title={`${passed.length} cleared the gate and went on to onboarding`}
        subtitle={report.checks_complete ? undefined : "by the checks that ran"}
      >
        {passed.length === 0 ? (
          <p className="p-3 text-sm text-muted">
            Nothing in this bundle reached onboarding.
          </p>
        ) : (
          <div className="flex flex-wrap gap-1.5 p-3">
            {passed.map((product) => (
              <span
                key={product.entity_id}
                className={cn(
                  "inline-flex items-center gap-1.5 rounded-sm border",
                  "border-subtle bg-sunken px-2 py-1 text-sm"
                )}
              >
                <IconCheck size={12} className="shrink-0 text-ok-text" />
                <Code>{product.sku}</Code>
                <span className="text-muted">{product.name}</span>
              </span>
            ))}
          </div>
        )}
      </Panel>
    </div>
  );
}

function StoppedRow({ product, supplier }: {
  product: BatchProduct; supplier: string;
}) {
  const gate = product.gate;
  return (
    <div className="flex flex-col gap-2 px-3 py-2.5">
      <div className="flex flex-wrap items-center gap-1.5">
        <Code>{product.sku}</Code>
        <span className="text-sm font-medium text-fg">{product.name}</span>
        <AuthorityTag authority={gate.authority} />
        <Badge tone="neutral">{product.category}</Badge>
        <span className="ml-auto whitespace-nowrap text-2xs uppercase tracking-caps text-faint">
          returned to {supplier}
        </span>
      </div>

      <ul className="flex flex-col gap-1">
        {gate.findings.map((finding, i) => (
          <FindingLine
            key={i}
            detail={finding.detail}
            basis={finding.basis}
            system={finding.system}
          />
        ))}
      </ul>

      {product.gaps === 0 && gate.data_findings.length > 0 && (
        <p className="text-xs leading-relaxed text-faint">
          {gate.data_findings.length} other thing
          {gate.data_findings.length === 1 ? " is" : "s are"} also open on this
          record. They are not why it was stopped, and fixing them would not
          change that.
        </p>
      )}
    </div>
  );
}
