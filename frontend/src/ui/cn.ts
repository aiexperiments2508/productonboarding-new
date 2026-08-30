/** Join class names, dropping anything falsy.
 *
 * Deliberately not `clsx`. The whole utility is four lines and this codebase
 * never needs its object or nested-array forms - a dependency for that is a
 * dependency to audit, install and keep pinned in a lab that must build
 * offline.
 */
export function cn(...parts: (string | false | null | undefined)[]): string {
  return parts.filter(Boolean).join(" ");
}
