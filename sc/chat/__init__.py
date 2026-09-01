"""Asking about a product in words, and being told only what is recorded.

The one surface in this application that takes an open-ended question, which
makes it the easiest place in it to tell somebody something untrue. Three
decisions arrange it so that is hard rather than so that answering is easy:

* **Routing is deterministic.** ``intents`` picks which surfaces a question
  reaches from a closed keyword set. A model choosing what to look up is a
  model that can choose to look up nothing and answer anyway.
* **Evidence is gathered before anything is phrased.** ``evidence`` reads the
  record, the readiness verdict, the graph and the corpus, and returns facts.
  ``reply`` is handed those facts and asked for a sentence. It has no way to
  reach a fact that was not gathered.
* **An answer with no evidence is a refusal.** Not a hedge, not a general
  remark about the category - a refusal that names what could be asked
  instead.

The whole path works with no model. The gateway is asked to phrase and nothing
else, so when its circuit breaker is open the same facts are templated and the
answer says which engine wrote it.
"""

from __future__ import annotations

from sc.contracts import ChatAnswer, ChatIntent

#: Longer than any real question and short enough that the prompt built from
#: it stays a known size. A question this long is a paste, not a question.
MAX_QUESTION = 500


def ask(question: str, key: str | None = None, *,
        use_model: bool = True) -> ChatAnswer:
    """Answer one question about one product.

    ``key`` is whatever the screen was holding - a SKU, a variant id or a
    product id. It is resolved once, inside ``evidence.gather``, and the
    resolution comes back on the answer so a reader is never left guessing
    which of the three the system thought they meant.

    ``use_model=False`` forces the deterministic phrasing. That is what the
    tests exercise, and what the API sends when the caller asks for it.
    """
    from sc.chat import evidence as evidence_mod
    from sc.chat import intents, reply as reply_mod

    question = (question or "").strip()[:MAX_QUESTION]
    intent = intents.classify(question, has_product=bool(key))
    ev = evidence_mod.gather(question, intent, key)

    if not ev.grounded:
        # Nothing was found, so nothing is said. The intent is reported as
        # UNANSWERABLE whatever it was routed as, because "I looked in the
        # right place and it was empty" and "I did not know where to look"
        # are the same answer to the person asking.
        text, spoken = reply_mod.refusal(intent, has_product=bool(key))
        return ChatAnswer(
            question=question, intent=ChatIntent.UNANSWERABLE,
            reply=text, spoken=spoken, sources=[], grounded=False,
            resolved=ev.resolved, phrased_by="template",
            as_of=ev.as_of)

    text, spoken, phrased_by = reply_mod.phrase(question, ev,
                                                use_model=use_model)
    return ChatAnswer(
        question=question, intent=intent, reply=text, spoken=spoken,
        sources=ev.sources, grounded=True, resolved=ev.resolved,
        phrased_by=phrased_by, highlight=ev.highlight, as_of=ev.as_of)


def capabilities() -> list[dict]:
    """What can be asked, for a UI that wants to offer examples."""
    from sc.chat import intents

    return [{"intent": intent.value, "describes": text}
            for intent, text in intents.CAPABILITIES.items()]
