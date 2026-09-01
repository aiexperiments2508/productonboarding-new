"""Turning gathered facts into a sentence, and nothing more than a sentence.

The model's whole job here is phrasing. It is handed evidence that has already
been gathered by ``sc.chat.evidence`` and asked to say it in English. It is not
given a retrieval tool, a database handle or a graph query, so the failure mode
where a model answers confidently from its own memory is not mitigated here -
it is unavailable.

Two things come out rather than one. ``reply`` is what appears on screen, where
"as recorded by supplier-portal" is the reason to believe the sentence.
``spoken`` is what is read aloud, where the same clause is noise a listener has
to sit through. They state the same facts at different lengths, because a
screen and an ear want different things - not because one is a summary of the
other.

When the gateway is unreachable the template writes the answer instead, from
the same evidence. That path is not a degraded mode to apologise for: it is
what a venue with no network gets, what the test suite exercises, and what the
circuit breaker falls back to after two failures.
"""

from __future__ import annotations

import re

from sc.chat import intents
from sc.chat.evidence import Evidence
from sc.contracts import ChatIntent

#: How many facts are handed to the model. The same cap the evidence layer
#: applies, restated here because a prompt that grows without bound is a
#: prompt whose behaviour changes with the size of the catalog.
MAX_FACTS = 12

#: Sentences read aloud. Speech is linear and cannot be skimmed, so the spoken
#: answer states the headline and the two or three facts that carry it, and
#: leaves the rest on screen where a reader can move at their own speed.
SPOKEN_FACTS = 3

SYSTEM = (
    "You are answering a question about one product in a retail onboarding "
    "system. You will be given a question and a numbered list of facts.\n\n"
    "Rules:\n"
    "1. Use only the facts given. Never add a fact, a number, a name or a "
    "date that is not in the list.\n"
    "2. If the facts do not answer the question, say so plainly.\n"
    "3. Answer in two to four sentences of plain English prose. No lists, no "
    "headings, no markdown.\n"
    "4. Do not write citation markers. The sources are shown beside your "
    "answer already.\n"
    "5. Prefer the concrete over the general: a number that is in the facts "
    "is worth more than an adjective that is not."
)


# ---------------------------------------------------------------------------
# The refusal
# ---------------------------------------------------------------------------


def _capabilities() -> str:
    """What this surface can answer, as a sentence somebody can act on.

    Read out whenever an answer is refused. "I cannot answer that" is half an
    answer; the missing half is what could be asked instead, and a reader who
    has to guess at the second half usually guesses wrong twice and stops.
    """
    return "; ".join(intents.CAPABILITIES.values())


def refusal(intent: ChatIntent, has_product: bool) -> tuple[str, str]:
    """What to say when there is nothing to stand on. Never a guess."""
    if not has_product:
        opening = ("I need a product selected before I can answer that. "
                   "Open one from the product list and ask again.")
    elif intent is ChatIntent.UNANSWERABLE:
        opening = "I cannot answer that from what this system records."
    else:
        opening = ("Nothing is recorded here that answers that. That is an "
                   "absence of data rather than a negative answer - the "
                   "question may simply not have reached this system yet.")
    return (f"{opening} I can tell you {_capabilities()}.",
            f"{opening} Ask me about a product's features, its readiness, "
            f"its imagery, compliance, stock, sales, campaigns or how it "
            f"connects to the rest of the catalog.")


# ---------------------------------------------------------------------------
# The deterministic path
# ---------------------------------------------------------------------------

#: Attribution clauses, stripped for speech. On screen they are the reason to
#: believe a sentence; read aloud they are three seconds of furniture between
#: the listener and the next fact.
_ATTRIBUTION = re.compile(
    r",? (?:as recorded by|according to) [^,.;]+", re.IGNORECASE)
#: Whatever a model writes despite being told not to.
_MARKER = re.compile(r"\s*[\[(](?:\d+|source \d+)[\])]")


def _strip_for_speech(text: str) -> str:
    return _MARKER.sub("", _ATTRIBUTION.sub("", text)).strip()


_WORD = re.compile(r"[a-z0-9._-]+")


def _stem(word: str) -> str:
    """Enough stemming to see that "blocking" and "block" are the same word.

    Not a linguistic claim - just enough to stop the de-duplication below
    being defeated by a suffix.
    """
    for suffix in ("ing", "ed", "s"):
        if len(word) > 4 and word.endswith(suffix):
            return word[: -len(suffix)]
    return word


def _significant(text: str) -> set[str]:
    # The dot belongs inside "compliance.certificate_ref" and nowhere near the
    # end of a sentence, and one character class cannot tell the two apart.
    # Matching greedily and trimming afterwards can: without the trim,
    # "findings." never stems to "finding" and the de-duplication below reads
    # every restatement as new information.
    words = (w.strip("._-") for w in _WORD.findall(text.lower()))
    return {_stem(w) for w in words if len(w) > 3}


def _adds_something(fact: str, headline: str) -> bool:
    """Whether a fact is worth a sentence given what the headline already said.

    The headline is a summary of the evidence, so the fact it summarises is
    usually in the list too - and stating the verdict, then restating the
    verdict, reads like a system with nothing to say. Anything sharing most of
    its words with the headline is dropped from the prose; it stays in the
    sources, where a reader looking for the citation will find it.
    """
    words = _significant(fact)
    if not words:
        return False
    shared = words & _significant(headline)
    return len(shared) / len(words) <= 0.5


def _sentence(fact: str) -> str:
    """One fact as a sentence, without mangling what it names.

    An attribute path is an identifier, and capitalising it turns
    ``compliance.certificate_ref`` into something that is not the name of
    anything. So the first letter is raised only when the first word is a
    word rather than a path.
    """
    if not fact:
        return ""
    head = fact.split(" ", 1)[0]
    if "." in head or "_" in head or head.isupper():
        return f" {fact}."
    return f" {fact[0].upper()}{fact[1:]}."


def template(question: str, ev: Evidence) -> tuple[str, str]:
    """The answer, written without a model, from the same evidence.

    Deliberately plain. This is not trying to sound like the model path and
    should not: a reader who can tell which one answered them knows whether
    the gateway was up, and that is worth more than a seamless imitation.
    """
    head = ev.headline or "Here is what is recorded."

    # Two findings can carry the same sentence against different fields - a
    # banned phrase in the description and in the marketing copy reads
    # identically. Both belong in the sources, where their subjects differ;
    # neither benefits from being read out twice. Exact equality only: the
    # three depot lines below also look alike, and the numbers that make them
    # different are the whole point of them.
    seen: set[str] = set()
    facts: list[str] = []
    for source in ev.sources[:MAX_FACTS]:
        if source.detail in seen or not _adds_something(source.detail, head):
            continue
        seen.add(source.detail)
        facts.append(source.detail)

    reply = head + "".join(_sentence(f) for f in facts[:6])
    spoken = _strip_for_speech(head) + "".join(
        _sentence(_strip_for_speech(f)) for f in facts[:SPOKEN_FACTS])
    return reply.strip(), spoken.strip()


# ---------------------------------------------------------------------------
# The model path
# ---------------------------------------------------------------------------


def _messages(question: str, ev: Evidence) -> list[dict]:
    lines = [f"{i}. {s.detail}" for i, s in enumerate(ev.sources[:MAX_FACTS], 1)]
    facts = "\n".join(lines)
    subject = ""
    if ev.resolved:
        subject = (f"The question is about {ev.resolved.get('sku')} "
                   f"(variant {ev.resolved.get('entity_id')}).\n")
    return [
        {"role": "system", "content": SYSTEM},
        {"role": "user",
         "content": f"{subject}Question: {question}\n\nFacts:\n{facts}"},
    ]


def phrase(question: str, ev: Evidence, *,
           use_model: bool = True) -> tuple[str, str, str]:
    """The answer, how it should be read aloud, and which engine wrote it.

    The model is asked once and is never retried. A phrasing step is not worth
    a second round trip: the template below says the same facts, and a reader
    waiting four seconds for a nicer sentence has been served worse than one
    who got the plain one immediately.
    """
    reply, spoken = template(question, ev)
    if not use_model or not ev.grounded:
        return reply, spoken, "template"

    from sc.llm import gateway

    if gateway.circuit_open():
        return reply, spoken, "template"

    try:
        text, _usage = gateway.complete(_messages(question, ev),
                                        temperature=0.0, agent="chat")
    except Exception:
        # Any failure at all falls back. The evidence is already gathered and
        # the template answer is already built, so there is nothing to report
        # to the reader beyond which engine phrased it - which the answer
        # carries anyway.
        return reply, spoken, "template"

    text = (text or "").strip()
    if not text:
        return reply, spoken, "template"
    return text, _strip_for_speech(text), "model"
