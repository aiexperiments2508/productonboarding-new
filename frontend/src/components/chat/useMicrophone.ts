import { useCallback, useEffect, useRef, useState } from "react";

/* Recording a spoken question.
 *
 * `MediaRecorder` into a Blob, posted to `/api/chat/transcribe`, which runs
 * Whisper in the platform's own process. The browser's `SpeechRecognition` API
 * would have been shorter and in Chrome it uploads the audio to Google - which
 * for a system whose whole argument is that it can say where every fact came
 * from was the wrong trade.
 *
 * `http://localhost` counts as a secure context, so `getUserMedia` works here
 * with no TLS. It still needs permission, and permission can be refused or
 * permanently denied - both of which say so rather than leaving a dead button.
 *
 * The stream's tracks are stopped the moment recording ends. A page that keeps
 * a microphone open leaves the browser's recording indicator lit, and a reader
 * who sees that while reading a product record is entitled to be alarmed.
 */

/** Longer than any spoken question, and short enough that a forgotten
 *  recording cannot grow into a refused upload. */
const MAX_MS = 30_000;

export type MicState =
  | "idle" | "starting" | "recording" | "transcribing"
  | "denied" | "unsupported" | "error";

export interface Microphone {
  state: MicState;
  error: string | null;
  /** Begin recording. Resolves as soon as the stream is live. */
  start: () => Promise<void>;
  /** Stop, upload, and resolve with what was heard - "" when nothing was. */
  stop: () => Promise<string>;
  cancel: () => void;
}

function supported(): boolean {
  return typeof window !== "undefined"
    && typeof window.MediaRecorder !== "undefined"
    && !!navigator.mediaDevices?.getUserMedia;
}

/** The best container this browser will actually give us.
 *
 *  Chrome records Opus in WebM and Firefox in Ogg; Safari does neither and
 *  produces MP4/AAC. All three decode server-side through PyAV, so the only
 *  job here is to name one the browser accepts rather than to insist on one. */
function pickMimeType(): string | undefined {
  const candidates = [
    "audio/webm;codecs=opus", "audio/webm",
    "audio/ogg;codecs=opus", "audio/mp4",
  ];
  return candidates.find((type) => MediaRecorder.isTypeSupported(type));
}


export function useMicrophone(): Microphone {
  const [state, setState] = useState<MicState>(
    supported() ? "idle" : "unsupported");
  const [error, setError] = useState<string | null>(null);

  const recorder = useRef<MediaRecorder | null>(null);
  const stream = useRef<MediaStream | null>(null);
  const chunks = useRef<Blob[]>([]);
  const timer = useRef<number | null>(null);
  const settle = useRef<((blob: Blob | null) => void) | null>(null);

  const release = useCallback(() => {
    if (timer.current != null) { window.clearTimeout(timer.current); timer.current = null; }
    stream.current?.getTracks().forEach((track) => track.stop());
    stream.current = null;
    recorder.current = null;
  }, []);

  const cancel = useCallback(() => {
    settle.current?.(null);
    settle.current = null;
    chunks.current = [];
    release();
    setState(supported() ? "idle" : "unsupported");
  }, [release]);

  useEffect(() => cancel, [cancel]);

  const start = useCallback(async () => {
    if (!supported()) { setState("unsupported"); return; }
    setError(null);
    setState("starting");
    try {
      const live = await navigator.mediaDevices.getUserMedia({
        audio: {
          // The three that matter for speech on a laptop microphone in a room
          // with other people's laptops in it.
          echoCancellation: true, noiseSuppression: true,
          autoGainControl: true,
        },
      });
      stream.current = live;
      chunks.current = [];

      const mimeType = pickMimeType();
      const rec = new MediaRecorder(live, mimeType ? { mimeType } : undefined);
      recorder.current = rec;

      rec.ondataavailable = (e) => {
        if (e.data.size > 0) chunks.current.push(e.data);
      };
      rec.onstop = () => {
        const blob = new Blob(chunks.current,
                              { type: rec.mimeType || "audio/webm" });
        chunks.current = [];
        release();
        settle.current?.(blob);
        settle.current = null;
      };

      rec.start();
      setState("recording");
      // A recording nobody stopped is a recording that grows until the upload
      // is refused. Stopping it is friendlier than failing later.
      timer.current = window.setTimeout(() => {
        if (recorder.current?.state === "recording") recorder.current.stop();
      }, MAX_MS);
    } catch (e) {
      release();
      const name = (e as DOMException)?.name;
      if (name === "NotAllowedError" || name === "SecurityError") {
        setState("denied");
        setError("The browser blocked the microphone. Allow it for this site "
                 + "and try again.");
      } else if (name === "NotFoundError") {
        setState("error");
        setError("No microphone was found on this machine.");
      } else {
        setState("error");
        setError(String(e));
      }
    }
  }, [release]);

  const stop = useCallback(async (): Promise<string> => {
    const rec = recorder.current;
    if (!rec || rec.state !== "recording") { cancel(); return ""; }

    const blob = await new Promise<Blob | null>((resolve) => {
      settle.current = resolve;
      rec.stop();
    });
    if (!blob || blob.size === 0) { setState("idle"); return ""; }

    setState("transcribing");
    try {
      const heard = await postAudio(blob);
      setState("idle");
      if (!heard) {
        setError("I did not hear anything. Try again, a little closer.");
      }
      return heard;
    } catch (e) {
      setState("error");
      setError(String(e));
      return "";
    }
  }, [cancel]);

  return { state, error, start, stop, cancel };
}


/** POST the recording as a raw body.
 *
 *  Not a multipart form: the browser has a Blob and the endpoint wants bytes,
 *  and a form part in between is two encodings to agree about for no gain.
 *  Kept out of `api.ts` for the same reason - every entry there is JSON in,
 *  JSON out, and this is the one call that is neither. */
async function postAudio(blob: Blob): Promise<string> {
  const response = await fetch("/api/chat/transcribe", {
    method: "POST",
    headers: { "Content-Type": blob.type || "audio/webm" },
    body: blob,
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => null);
    throw new Error(detail?.detail ?? `transcription failed (${response.status})`);
  }
  const body = await response.json() as { text: string; heard: boolean };
  return body.heard ? body.text : "";
}
