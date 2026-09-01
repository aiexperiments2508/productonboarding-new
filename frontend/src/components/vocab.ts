import type { AttributeDef, CatalogState } from "../api";

/* Naming things the catalog already named.
 *
 * Two screens turn ids into sentences - the live event feed and the open-case
 * list - and both need the same three lookups. Held here rather than in either
 * of them because the second copy is where "rated power" and "specs.power_w"
 * start appearing in the same product for the same attribute.
 */

export interface Vocab {
  /** The display name for an id, falling back to the id itself. */
  name: (id: unknown) => string;
  /** An attribute path as a label that reads mid-sentence. */
  attr: (path: unknown) => string;
  def: (path: string) => AttributeDef | undefined;
}

export function buildVocab(catalog: CatalogState | null): Vocab {
  const names = new Map<string, string>();
  for (const n of catalog?.nodes ?? []) names.set(n.id, n.name);
  for (const p of catalog?.products ?? []) names.set(p.id, p.name);
  for (const v of catalog?.variants ?? []) names.set(v.id, v.name);
  for (const c of catalog?.channels ?? []) names.set(c.id, c.name);
  const defs = new Map<string, AttributeDef>();
  for (const a of catalog?.attributes ?? []) defs.set(a.path, a);
  return {
    name: (id) => (typeof id === "string" && id ? names.get(id) ?? id : ""),
    attr: (path) => {
      if (typeof path !== "string" || !path) return "";
      const label = defs.get(path)?.label;
      // "Rated power" reads badly after a verb; "GTIN" must not become
      // "gTIN", so only a sentence-cased label is lowered.
      return label
        ? /^[A-Z][a-z]/.test(label)
          ? label[0].toLowerCase() + label.slice(1)
          : label
        : path;
    },
    def: (path) => defs.get(path),
  };
}
