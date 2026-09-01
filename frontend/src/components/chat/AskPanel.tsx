import { useCallback, useEffect, useRef, useState } from "react";

import { api, type ChatAnswer, type ChatSource } from "../../api";
import { IconAsk, IconSpeaker, IconSpeakerOff } from "../../icons";
import { Badge, Button, Panel, cn } from "../../ui";
import { useSpeech } from "./useSpeech";

/* Asking about a product in words.
 *
 * Not a sixth section. The five sections are the things a record is made of,
 * and a question can be about any of them - so this sits above all five and
 * links *into* them rather than competing for a place in the row.
 *
 * The design problem here is not the chat; it is making a confident sentence
 * and an admission of ignorance look different. An answer with sources renders
 * as prose with its evidence under it. An answer without them renders as a
 * refusal, in the muted treatment findings use for "nothing to report", and it
 * never gets the prose styling. A reader should be able to tell the two apart
 * from across the room.
 */

/** What the panel offers before anybody has typed anything.
 *
 *  Deliberately concrete rather than a category list: "what can I ask" is
 *  answered much better by four questions somebody would actually type than by
 *  a description of the space of questions. */
const SUGGESTIONS = [
  "What are its features?",
  "Can it launch?",
  "Where is it stocked?",
  "Which campaigns is it in?",
];

interface Turn {
  id: number;
  question: string;
  answer: ChatAnswer | null;
  error: string | null;
}

/** Where a citation points, in the words the section row uses. */
const SECTION_LABEL: Record<string, string> = {
  findings: "Findings",
  cause: "Root cause",
  record: "The record",
  media: "Imagery",
  graph: "Graph",
};

function SourceList({ sources, onJump }: {
  sources: ChatSource[];
  onJump?: (section: string) => void;
}) {
  if (sources.length === 0) return null;
  return (
    <ul className="mt-2 space-y-1 border-l-2 border-subtle pl-2.5">
      {sources.map((source, i) => (
        <li key={`${source.reference ?? source.label}-${i}`}
            className="text-xs leading-snug text-muted">
          <span className="text-faint">{source.kind}</span>
          {" · "}
          <span>{source.detail}</span>
          {source.section && onJump && (
            <button
              type="button"
              onClick={() => onJump(source.section as string)}
              className={cn("ml-1.5 underline decoration-dotted",
                            "underline-offset-2 hover:text-base")}
            >
              {SECTION_LABEL[source.section] ?? source.section}
            </button>
          )}
        </li>
      ))}
    </ul>
  );
}


export function AskPanel({ selected, sku, onJump }: {
  /** The variant on screen, or null when nothing is selected. */
  selected: string | null;
  sku?: string | null;
  onJump?: (section: string) => void;
}) {
  const [question, setQuestion] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [busy, setBusy] = useState(false);
  const [readAloud, setReadAloud] = useState(false);
  const speech = useSpeech();
  const nextId = useRef(1);
  const endRef = useRef<HTMLDivElement | null>(null);

  // A new product is a new conversation. Keeping the transcript would leave
  // answers about the previous SKU sitting above a question about this one,
  // and the two are indistinguishable once the prose has scrolled.
  useEffect(() => {
    setTurns([]);
    speech.stop();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "nearest" });
  }, [turns]);

  const ask = useCallback(async (text: string) => {
    const asked = text.trim();
    if (!asked || busy) return;

    const id = nextId.current++;
    setTurns((prev) => [...prev, { id, question: asked, answer: null,
                                   error: null }]);
    setQuestion("");
    setBusy(true);
    try {
      const answer = await api.chatAsk(asked, sku ?? selected);
      setTurns((prev) => prev.map((t) =>
        t.id === id ? { ...t, answer } : t));
      if (readAloud) speech.speak(answer.spoken);
    } catch (e) {
      setTurns((prev) => prev.map((t) =>
        t.id === id ? { ...t, error: String(e) } : t));
    } finally {
      setBusy(false);
    }
  }, [busy, readAloud, selected, sku, speech]);

  const toggleAloud = useCallback(() => {
    setReadAloud((on) => {
      if (on) speech.stop();
      return !on;
    });
  }, [speech]);

  return (
    <Panel
      icon={<IconAsk size={15} />}
      title="Ask about this product"
      subtitle={selected
        ? "answered only from what the estate records"
        : "select a product to ask about it"}
      actions={
        <div className="flex items-center gap-1.5">
          {speech.speaking && (
            <Button size="xs" tone="ghost" onClick={speech.stop}>
              Stop
            </Button>
          )}
          {speech.supported && (
            <Button
              size="xs"
              tone={readAloud ? "subtle" : "ghost"}
              onClick={toggleAloud}
              aria-pressed={readAloud}
              title={readAloud
                ? "Answers are read aloud. Click to stop reading them."
                : "Read answers aloud, using this browser's own voice."}
            >
              {readAloud ? <IconSpeaker size={14} /> : <IconSpeakerOff size={14} />}
              <span className="ml-1.5">Read aloud</span>
            </Button>
          )}
        </div>
      }
    >
      {turns.length === 0 && (
        <div className="flex flex-wrap gap-1.5">
          {SUGGESTIONS.map((s) => (
            <button
              key={s}
              type="button"
              disabled={!selected}
              onClick={() => ask(s)}
              className={cn(
                "rounded-full border border-subtle px-2.5 py-1 text-xs",
                "text-muted transition-colors",
                "hover:border-strong hover:text-base",
                "disabled:cursor-not-allowed disabled:opacity-50"
              )}
            >
              {s}
            </button>
          ))}
        </div>
      )}

      {turns.length > 0 && (
        <div className="max-h-[22rem] space-y-3 overflow-y-auto pr-1">
          {turns.map((turn) => (
            <div key={turn.id} className="space-y-1.5">
              <p className="text-sm font-medium text-base">{turn.question}</p>

              {turn.answer == null && turn.error == null && (
                <p className="text-sm text-faint">Looking...</p>
              )}
              {turn.error != null && (
                <p className="text-sm text-danger">{turn.error}</p>
              )}
              {turn.answer != null && <Answer answer={turn.answer}
                                              onJump={onJump}
                                              speech={speech} />}
            </div>
          ))}
          <div ref={endRef} />
        </div>
      )}

      <form
        className="mt-3 flex items-center gap-2"
        onSubmit={(e) => { e.preventDefault(); ask(question); }}
      >
        <input
          type="text"
          value={question}
          disabled={!selected}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder={selected
            ? "What are its features?"
            : "Select a product first"}
          aria-label="Ask a question about this product"
          className={cn(
            "h-[var(--control-h-sm)] w-full rounded-sm border",
            "border-strong bg-raised px-2.5 text-base",
            "transition-colors focus:border-focus",
            "disabled:cursor-not-allowed disabled:opacity-60"
          )}
        />
        <Button type="submit" size="sm" tone="primary"
                disabled={!selected || busy || question.trim() === ""}>
          Ask
        </Button>
      </form>
    </Panel>
  );
}


/** One answer, rendered as what it is rather than as prose either way. */
function Answer({ answer, onJump, speech }: {
  answer: ChatAnswer;
  onJump?: (section: string) => void;
  speech: ReturnType<typeof useSpeech>;
}) {
  if (!answer.grounded) {
    // A refusal. Muted, no prose treatment, no sources block - it has to be
    // visibly a different kind of thing from an answer, or the one time it
    // matters a reader will skim it as though it said something.
    return (
      <div className="rounded-sm border border-dashed border-subtle
                      bg-sunken px-2.5 py-2">
        <p className="text-sm leading-snug text-muted">{answer.reply}</p>
      </div>
    );
  }

  return (
    <div>
      <p className="text-sm leading-relaxed text-base">{answer.reply}</p>
      <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
        <Badge tone="neutral">{answer.intent.toLowerCase()}</Badge>
        {/* Which engine wrote the sentence. Worth showing rather than
          * hiding: "template" means the gateway was unreachable and the
          * same facts were rendered deterministically, and a reader who
          * knows that reads the prose differently. */}
        <span className="text-xs text-faint">
          {answer.phrased_by === "model"
            ? "phrased by the model from the evidence below"
            : "written from the evidence below, without a model"}
        </span>
        {speech.supported && (
          <button
            type="button"
            onClick={() => speech.speak(answer.spoken)}
            className={cn("text-xs text-faint underline decoration-dotted",
                          "underline-offset-2 hover:text-muted")}
          >
            read aloud
          </button>
        )}
      </div>
      <SourceList sources={answer.sources} onJump={onJump} />
    </div>
  );
}
