import type { ReactNode } from "react";
import { sectionById } from "../nav";
import type { SectionId } from "../nav";

/* Page header.
 *
 * Title, one line on what the section is for, and the section-level actions.
 * The description is not filler: five dense panels with no framing leave a
 * reviewer to infer what they are looking at from the panel titles, and the
 * distinction between "Blast Radius" and "Readings" is exactly the sort of
 * thing that is obvious once and never again.
 */

export function PageHeader({
  section, actions,
}: {
  section: SectionId;
  actions?: ReactNode;
}) {
  const current = sectionById(section);
  return (
    <div className="mb-3 flex shrink-0 items-start gap-4">
      <div className="min-w-0 flex-1">
        <h1 className="truncate text-xl font-semibold tracking-tight text-fg">
          {current.label}
        </h1>
        <p className="mt-0.5 max-w-3xl text-sm leading-relaxed text-muted">
          {current.description}
        </p>
      </div>
      {actions && (
        <div className="flex shrink-0 items-center gap-2 pt-0.5">{actions}</div>
      )}
    </div>
  );
}
