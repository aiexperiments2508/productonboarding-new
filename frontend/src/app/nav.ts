import type { ComponentType } from "react";
import {
  IconApprovals, IconInvestigate, IconScenarios, IconSystem, IconTower,
} from "../icons";
import type { IconProps } from "../icons";

/* The five sections, defined once.
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
  | "tower" | "investigation" | "scenarios" | "approvals" | "system";

export const SECTIONS: Section[] = [
  {
    id: "tower",
    label: "Ingest Fabric",
    description:
      "The external systems feeding the catalog, what each one is delivering right now, and which corrections are in force.",
    Icon: IconTower,
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
    id: "system",
    label: "System Control",
    description:
      "The replay transport, the model gateway, and the retrieval index behind the loop.",
    Icon: IconSystem,
  },
];

export const sectionById = (id: SectionId): Section =>
  SECTIONS.find((s) => s.id === id) ?? SECTIONS[0];
