import { useEffect, useRef, useState } from "react";
import { useReducedMotion } from "./useReducedMotion";

/* Animate a figure to its new value.
 *
 * Every number on this screen is a simulation output, and a KPI that snaps
 * from one value to another gives no sense of which way it moved. Counting
 * carries the direction and the magnitude of the change for free.
 *
 * Two rules keep it honest:
 *
 *   - It counts from the PREVIOUS value, never from zero. Counting up from
 *     zero to 94.3% of listings ready implies a change that did not happen;
 *     counting from 93.8 to 94.3 shows the change that did.
 *   - The first render is not animated. There is nothing to have moved from.
 *
 * Under reduced motion it returns the target unchanged - no timer is started.
 */
export function useCountUp(target: number, durationMs = 520): number {
  const reduced = useReducedMotion();
  const [display, setDisplay] = useState(target);
  const fromRef = useRef(target);
  const frameRef = useRef(0);
  const firstRef = useRef(true);

  useEffect(() => {
    if (firstRef.current) {
      firstRef.current = false;
      fromRef.current = target;
      setDisplay(target);
      return;
    }
    if (reduced || !Number.isFinite(target)) {
      fromRef.current = target;
      setDisplay(target);
      return;
    }

    const from = fromRef.current;
    if (from === target) return;

    const start = performance.now();
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / durationMs);
      // Ease-out cubic. The value should decelerate into place; a linear count
      // reads like a loading spinner rather than a figure settling.
      const eased = 1 - Math.pow(1 - t, 3);
      setDisplay(from + (target - from) * eased);
      if (t < 1) frameRef.current = requestAnimationFrame(tick);
      else fromRef.current = target;
    };
    frameRef.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frameRef.current);
  }, [target, durationMs, reduced]);

  return display;
}
