/* The seven domains, as the UI says them.
 *
 * **Every class here is a literal, and that is not a style preference.**
 * Tailwind builds its stylesheet by scanning source text for class names it
 * recognises. `fill-kg-${domain}` is a string it never sees, so it emits no
 * rule and every node renders unstyled - with no error, in a build that
 * succeeds. A lookup table is the only way to write this.
 *
 * Colour is also never the only channel. `NetworkMap` reinforces its states
 * with stroke width and dash as well as hue, and `Badge` says why: a signal
 * carried by hue alone does not survive being read by somebody who does not
 * separate red from green. Here the spine is a square and everything else is a
 * circle, and anything generated is dashed.
 */

import type { KgDomain } from "../../api";

export const DOMAIN_ORDER: KgDomain[] = [
  "CORE", "CATEGORY", "COMPLIANCE", "WAREHOUSE", "MEDIA", "SALES", "MARKETING",
];

/** What each domain is called on screen. Nouns a merchant uses, not enum
 *  members: "Compliance", not "COMPLIANCE". */
export const DOMAIN_LABEL: Record<KgDomain, string> = {
  CORE: "Core",
  CATEGORY: "Category",
  COMPLIANCE: "Compliance",
  WAREHOUSE: "Warehouse",
  MEDIA: "Media",
  SALES: "Sales",
  MARKETING: "Marketing",
};

/** One line on what each domain holds. Read out in the legend, because seven
 *  colours with no explanation is a key nobody can use. */
export const DOMAIN_BLURB: Record<KgDomain, string> = {
  CORE: "The product, its variants and who supplies it",
  CATEGORY: "Where it sits in the taxonomy, and what it is described by",
  COMPLIANCE: "Certificates, the rules they satisfy, the markets that enforce them",
  WAREHOUSE: "Which depots hold it, and how much",
  MEDIA: "The imagery held against it",
  SALES: "Channels, listings, prices and what it sold",
  MARKETING: "Campaigns, promotions, keywords and who they target",
};

export const DOMAIN_FILL: Record<KgDomain, string> = {
  CORE: "fill-kg-core",
  CATEGORY: "fill-kg-category",
  COMPLIANCE: "fill-kg-compliance",
  WAREHOUSE: "fill-kg-warehouse",
  MEDIA: "fill-kg-media",
  SALES: "fill-kg-sales",
  MARKETING: "fill-kg-marketing",
};

export const DOMAIN_STROKE: Record<KgDomain, string> = {
  CORE: "stroke-kg-core",
  CATEGORY: "stroke-kg-category",
  COMPLIANCE: "stroke-kg-compliance",
  WAREHOUSE: "stroke-kg-warehouse",
  MEDIA: "stroke-kg-media",
  SALES: "stroke-kg-sales",
  MARKETING: "stroke-kg-marketing",
};

export const DOMAIN_TEXT: Record<KgDomain, string> = {
  CORE: "text-kg-core",
  CATEGORY: "text-kg-category",
  COMPLIANCE: "text-kg-compliance",
  WAREHOUSE: "text-kg-warehouse",
  MEDIA: "text-kg-media",
  SALES: "text-kg-sales",
  MARKETING: "text-kg-marketing",
};

/** Which Product 360 section a node's domain belongs to, where one does.
 *
 *  This is the quick link out of the side panel and back into the record. A
 *  graph that could only ever show you a connection, and never take you to the
 *  screen that does something about it, would be a diagram rather than a tool.
 *  Null means there is no section for this domain - the four generated ones
 *  have no counterpart in the record, and pretending otherwise would send a
 *  reader to a panel that does not mention what they clicked. */
export const DOMAIN_SECTION: Record<KgDomain, "record" | "media" | null> = {
  CORE: "record",
  CATEGORY: "record",
  COMPLIANCE: "record",
  MEDIA: "media",
  WAREHOUSE: null,
  SALES: null,
  MARKETING: null,
};

/** How a node's own kind is said in a sentence. `MediaNode` is a label chosen
 *  to avoid shadowing a Python class; nobody should have to read that. */
export function labelNoun(label: string): string {
  if (label === "MediaNode") return "image";
  return label
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .toLowerCase();
}
