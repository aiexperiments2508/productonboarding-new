import type { ComponentType } from "react";
import {
  IconActivity, IconApprovals, IconIntake, IconInvestigate, IconLifecycle,
  IconProduct, IconScenarios, IconSystem, IconTower,
} from "../icons";
import type { IconProps } from "../icons";

/* The sections, defined once.
 *
 * The sidebar, the breadcrumb, the page header and the command palette all
 * read from this. Previously the label list lived in main.tsx and the palette
 * did not exist; four copies of the same five strings is four places to
 * disagree about what a section is called.
 */

export interface Section {
  id: SectionId;
  label: string;
  /** Shown under the page title. Says what the section is FOR, not what it
   *  contains - the panels already say what they contain. */
  description: string;
  Icon: ComponentType<IconProps>;
}

export type SectionId =
  | "fabric" | "intake" | "lifecycle" | "product360" | "investigation"
  | "scenarios" | "approvals" | "tower" | "system";

export const SECTIONS: Section[] = [
  {
    id: "fabric",
    label: "Ingest Fabric",
    description:
      "The catalog as a graph — every product, variant and channel, what a correction there would reach, and the tape arriving over it. What is in force opens from the rail.",
    Icon: IconTower,
  },
  {
    id: "intake",
    // "Supplier Intake", not "Reports": the noun is the thing that arrived,
    // and a section called Reports invites every other number in the product
    // to be moved into it.
    label: "Supplier Intake",
    description:
      "What a supplier sent in one archive, how much of it is fit to sell, "
      + "and which of the gaps could be closed from a document we already hold.",
    Icon: IconIntake,
  },
  {
    id: "lifecycle",
    // "Lifecycle", not "Pipeline": a pipeline implies one direction, and the
    // lane this view exists for is the one products come *back* into after
    // they have already launched.
    label: "Product Lifecycle",
    description:
      "Where every product has got to - sent back to its supplier, cleared, pushed downstream, on sale, or overtaken by a late change. The upstream and downstream systems open from here.",
    Icon: IconLifecycle,
  },
  {
    id: "product360",
    label: "Product 360",
    description:
      "Find a product by SKU or name, see what every system has said about it, and whether its information is fit to launch.",
    Icon: IconProduct,
  },
  {
    id: "investigation",
    label: "Blast Radius",
    description:
      "What the correction says, which variant it applies to, and every field, asset and channel built on the old value.",
    Icon: IconInvestigate,
  },
  {
    id: "scenarios",
    // "Readings", not "Resolutions": these are competing interpretations of one
    // ambiguous sentence, and the panel has always called them that. The rail
    // and the panel now agree, and neither promises a scatter plot the view
    // deliberately does not have.
    label: "Readings",
    description:
      "Every candidate reading of the correction, validated deterministically against the channel rules and ranked, with the evidence that decides between them beside each one.",
    Icon: IconScenarios,
  },
  {
    id: "approvals",
    label: "Review & Audit",
    description:
      "The suspended run, the change diff it is waiting on, and the append-only record of what was published.",
    Icon: IconApprovals,
  },
  {
    id: "tower",
    // "Control Tower", and it is the only section that reports on the estate
    // rather than on one product, one correction or one batch. Ninth rather
    // than first on purpose: it is the screen you read after the work, not the
    // one you start it from.
    label: "Control Tower",
    description:
      "Every feed from received to on sale, the KPIs over any date range, and "
      + "what the models cost reaching them. Pick a persona to change what you "
      + "are shown - it is a lens, not a permission boundary.",
    Icon: IconActivity,
  },
  {
    id: "system",
    label: "System Control",
    description:
      "The machinery under the factory: the replay transport and its feed, the systems delivering into it, the model gateway, and the retrieval index behind the loop.",
    Icon: IconSystem,
  },
];

export const sectionById = (id: SectionId): Section =>
  SECTIONS.find((s) => s.id === id) ?? SECTIONS[0];
