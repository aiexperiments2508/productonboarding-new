import { useCallback, useEffect, useRef, useState } from "react";

/* Reading an answer out loud.
 *
 * The whole of the speech-out path, and it is deliberately the browser's own
 * `speechSynthesis` rather than anything served from here. Nothing is uploaded,
 * nothing is stored, and the application keeps working with the speakers muted
 * - which is the same posture the rest of this system takes towards the model
 * gateway: useful when present, never load-bearing.
 *
 * Two browser behaviours are worked around rather than assumed away:
 *
 * - **Voices arrive late.** `getVoices()` is empty on first call in Chrome and
 *   fills in after a `voiceschanged` event. Reading it once at mount gives a
 *   robotic default voice for the life of the page.
 * - **Long utterances stop early.** Chrome's synthesiser pauses itself after
 *   roughly fifteen seconds. The fix everybody uses is to call `resume()` on a
 *   timer while speaking; it is ugly, it is not our bug, and without it a
 *   three-sentence answer is cut off mid-clause.
 */

/** Chrome stops speaking after ~15s unless nudged. Well inside that. */
const KEEPALIVE_MS = 8_000;

export interface Speech {
  /** False when the browser has no speech synthesiser at all. */
  supported: boolean;
  speaking: boolean;
  speak: (text: string) => void;
  stop: () => void;
}

function synth(): SpeechSynthesis | null {
  if (typeof window === "undefined") return null;
  return window.speechSynthesis ?? null;
}

/** The most natural-sounding English voice on offer, or the default.
 *
 *  Preference order is a matter of taste and the list differs per platform, so
 *  this picks by a few known-good names and otherwise takes the first English
 *  voice rather than imposing one. */
function pickVoice(voices: SpeechSynthesisVoice[]): SpeechSynthesisVoice | null {
  if (voices.length === 0) return null;
  const english = voices.filter((v) => v.lang?.toLowerCase().startsWith("en"));
  const pool = english.length > 0 ? english : voices;
  const preferred = ["Google UK English Female", "Microsoft Sonia",
                     "Samantha", "Microsoft Aria"];
  for (const name of preferred) {
    const hit = pool.find((v) => v.name.includes(name));
    if (hit) return hit;
  }
  return pool[0] ?? null;
}

export function useSpeech(): Speech {
  const [speaking, setSpeaking] = useState(false);
  const [voices, setVoices] = useState<SpeechSynthesisVoice[]>([]);
  const keepalive = useRef<number | null>(null);

  const supported = synth() != null;

  useEffect(() => {
    const s = synth();
    if (!s) return;
    const load = () => setVoices(s.getVoices());
    load();
    // Chrome populates the list asynchronously; without this the first answer
    // is read in whatever default voice happened to exist at mount.
    s.addEventListener("voiceschanged", load);
    return () => s.removeEventListener("voiceschanged", load);
  }, []);

  const clearKeepalive = useCallback(() => {
    if (keepalive.current != null) {
      window.clearInterval(keepalive.current);
      keepalive.current = null;
    }
  }, []);

  const stop = useCallback(() => {
    clearKeepalive();
    synth()?.cancel();
    setSpeaking(false);
  }, [clearKeepalive]);

  const speak = useCallback((text: string) => {
    const s = synth();
    if (!s || !text.trim()) return;

    // Cancel first. Queueing means a reader who asks three questions quickly
    // sits through the first two answers before hearing the one they want.
    s.cancel();
    clearKeepalive();

    const utterance = new SpeechSynthesisUtterance(text);
    const voice = pickVoice(voices);
    if (voice) utterance.voice = voice;
    utterance.rate = 1.02;
    utterance.pitch = 1;

    utterance.onend = () => { clearKeepalive(); setSpeaking(false); };
    utterance.onerror = () => { clearKeepalive(); setSpeaking(false); };

    setSpeaking(true);
    s.speak(utterance);
    keepalive.current = window.setInterval(() => {
      if (s.speaking) s.resume();
    }, KEEPALIVE_MS);
  }, [clearKeepalive, voices]);

  // Leaving the page mid-sentence should not leave a voice talking over
  // whatever the reader opened next.
  useEffect(() => stop, [stop]);

  return { supported, speaking, speak, stop };
}
