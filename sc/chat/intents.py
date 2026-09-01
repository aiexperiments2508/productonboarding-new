"""What a question is asking for, decided without a model.

The obvious design is to hand the question to an LLM and let it choose which
tools to call. This does not do that, and the reason is the same one the rest
of the application gives for keeping AI to four places: a model choosing what
to look up is a model that can choose to look up nothing and answer anyway.

Routing here is a keyword match over a closed set. That has three properties
worth more than the flexibility it gives up:

* **It cannot invent a source.** The intent decides which surfaces are read,
  and every surface returns facts or returns nothing.
* **It works with no gateway.** The circuit breaker opens after two failures
  and this surface keeps answering, because nothing about deciding *what to
  look up* needed a model.
* **It is inspectable.** "Why did it answer about stock?" has an answer you can
  read in this file, rather than one that has to be reconstructed from a
  prompt.

The cost is real: a question phrased unusually lands on ``UNANSWERABLE``. That
is the failure this is arranged to prefer - saying "I can answer these things"
is recoverable in a way that a confident answer about the wrong subject is not.
"""

from __future__ import annotations

import re

from sc.contracts import ChatIntent

#: Words that select an intent, and how strongly. A word appearing under two
#: intents is worth less to each, which is what stops "product" - a word in
#: half of all questions - deciding anything.
#:
#: Weights are small integers rather than floats because the arithmetic is a
#: tie-break, not a probability, and writing 0.7 would imply a calibration
#: nobody has done.
KEYWORDS: dict[ChatIntent, dict[str, int]] = {
    ChatIntent.FEATURES: {
        "feature": 3, "features": 3, "spec": 3, "specs": 3, "specification": 3,
        "attribute": 3, "attributes": 3, "ingredient": 3, "ingredients": 3,
        "allergen": 3, "allergens": 3, "material": 2, "weight": 2, "size": 2,
        "dimensions": 2, "power": 2, "battery": 2, "capacity": 2, "colour": 2,
        "color": 2, "made of": 3, "contain": 2, "contains": 2, "gtin": 2,
        "barcode": 2, "what is in": 3, "describe": 1,
    },
    ChatIntent.READINESS: {
        "ready": 3, "readiness": 3, "launch": 3, "blocked": 3, "block": 2,
        "finding": 3, "findings": 3, "wrong": 3, "problem": 2, "issue": 2,
        "fix": 2, "outstanding": 2, "open": 1, "publish": 2, "go live": 3,
        "can it": 2, "why not": 2, "verdict": 3,
    },
    ChatIntent.MEDIA: {
        "image": 3, "images": 3, "imagery": 3, "photo": 3, "photos": 3,
        "picture": 3, "pictures": 3, "shot": 2, "pack shot": 3, "hero": 2,
        "asset": 2, "assets": 2, "media": 3, "visual": 2,
    },
    ChatIntent.COMPLIANCE: {
        "certificate": 3, "certificates": 3, "certification": 3, "certified": 3,
        "compliance": 3, "compliant": 3, "regulation": 3, "regulations": 3,
        "regulatory": 3, "lawful": 3, "legal": 3, "expire": 3, "expires": 3,
        "expiring": 3, "lapse": 3, "ukca": 3, "ce mark": 3, "market": 1,
        "restricted": 3, "hazmat": 3, "dangerous": 2, "age": 1,
        # "Sold" is a strong SALES word and "market" is weighted at 1 here
        # precisely because it is ambiguous - so "which markets can it be sold
        # in" reached SALES and answered a question about lawfulness with a
        # revenue figure. Where a thing may be sold and what it sold are
        # different questions that share their vocabulary; only the phrasing
        # separates them.
        "sold in": 3, "sell in": 3, "which markets": 3, "what markets": 3,
        "allowed": 2, "permitted": 3, "lawfully": 3,
    },
    ChatIntent.STOCK: {
        "stock": 3, "stocked": 3, "warehouse": 3, "warehouses": 3, "depot": 3,
        "depots": 3, "inventory": 3, "on hand": 3, "how many": 2, "reorder": 3,
        "quantity": 2, "pallet": 2, "storage": 2, "ship": 2, "shipping": 2,
    },
    ChatIntent.SALES: {
        "sale": 2, "sales": 3, "sell": 3, "sold": 3, "selling": 3, "revenue": 3,
        "price": 3, "priced": 3, "cost": 2, "margin": 2, "units": 2,
        "best seller": 3, "bestseller": 3, "channel": 2, "channels": 2,
        "listing": 2, "listings": 2, "how much": 2,
    },
    ChatIntent.MARKETING: {
        "campaign": 3, "campaigns": 3, "promotion": 3, "promotions": 3,
        "promoted": 3, "marketing": 3, "keyword": 3, "keywords": 3,
        "audience": 3, "persona": 3, "advert": 2, "advertising": 2,
        "cross-sell": 3, "cross sell": 3, "bundle": 2,
    },
    ChatIntent.CONNECTIONS: {
        "connected": 3, "connection": 3, "connections": 3, "related": 3,
        "relate": 2, "linked": 3, "graph": 2, "similar": 3, "complement": 3,
        "complements": 3, "goes with": 3, "neighbour": 2, "neighbours": 2,
        "supplier": 2, "category": 2, "taxonomy": 2,
    },
    ChatIntent.STANDARDS: {
        "standard": 3, "standards": 3, "policy": 3, "policies": 3, "rule": 2,
        "rules": 2, "guideline": 3, "guidelines": 3, "says": 2, "state": 1,
        "requirement": 3, "requirements": 3, "incident": 2,
        "what does": 2, "according to": 3,
        # "What do the standards say about allergens" is a corpus question
        # whatever the last word is - but "allergen" is a strong FEATURES
        # word, and on single tokens alone the two tied and the record won.
        # A document *speaking* is the thing being asked about here, so the
        # phrase carries weight the nouns cannot outvote.
        "standards say": 3, "standard says": 3, "standards says": 3,
        "policy says": 3, "policy say": 3, "policies say": 3,
        "guidelines say": 3, "guideline says": 3, "rules say": 3,
        "say about": 2, "says about": 2,
    },
    ChatIntent.OVERVIEW: {
        "overview": 3, "summary": 3, "summarise": 3, "summarize": 3,
        "tell me about": 3, "what is": 2, "who makes": 2, "brand": 2,
        "everything": 2, "about this": 2,
    },
}

def _inflect(word: str) -> list[str]:
    """The forms of a word somebody might actually type.

    Hand-written tables miss inflections, and each miss is a real routing
    failure rather than a near miss: "what did it sell" scored nothing for
    SALES because the table had sold, sells and selling but not the bare verb,
    and "what is blocking it" missed READINESS the same way. Both were found
    by testing the surface rather than by reading the table, which is a good
    reason not to trust reading the table.

    This generates a few non-words - "selled" among them. They cost a dict
    entry each and can never match anything a person types, which is a better
    trade than the two defects above.
    """
    if word.endswith("e"):
        return [word + "s", word + "d", word[:-1] + "ing"]
    if word.endswith("s"):
        return []
    return [word + "s", word + "ed", word + "ing"]


def _base(word: str) -> list[str]:
    """The word an inflection was built from.

    ``_inflect`` only adds suffixes, so a table whose author happened to write
    "connected" and "connections" never yields "connect" - and "what does it
    connect to" then scores nothing for CONNECTIONS. Stripping is the other
    half of the same job.

    Short results are dropped: taking "ing" off "ranks" leaves noise rather
    than a word, and a two-letter key would match half the language.
    """
    forms = []
    if word.endswith("ing") and len(word) > 6:
        forms += [word[:-3], word[:-3] + "e"]
    elif word.endswith("ed") and len(word) > 5:
        forms += [word[:-2], word[:-1]]
    elif word.endswith("s") and len(word) > 4:
        forms.append(word[:-1])
    return [f for f in forms if len(f) >= 4]


def _expand(table: dict) -> dict:
    """Add the missing inflections, without letting one intent take another's.

    A form already spelled out under *any* intent is left exactly where its
    author put it. That guard is what stops COMPLIANCE - which weights
    "market" at 1 - quietly acquiring "marketing" and answering campaign
    questions with a list of regulations.
    """
    claimed = {word for words in table.values() for word in words}
    for words in table.values():
        for word in list(words):
            if " " in word:
                continue
            for form in _inflect(word) + _base(word):
                if form not in claimed:
                    words[form] = words[word]
                    claimed.add(form)
    return table


KEYWORDS = _expand(KEYWORDS)


#: Below this an intent has not really been named and OVERVIEW is the honest
#: default for a question that mentions a product. Two is one strong word or a
#: pair of weak ones.
FLOOR = 2

_WORD = re.compile(r"[a-z0-9'-]+")


def _normalise(question: str) -> str:
    return " ".join(_WORD.findall(question.lower()))


def score(question: str) -> dict[ChatIntent, int]:
    """How strongly each intent is named. Exposed so a test can read it.

    Phrases are matched against the normalised string and single words against
    its tokens, so "how much" cannot be satisfied by a "much" three clauses
    away.
    """
    text = _normalise(question)
    tokens = set(text.split())

    totals: dict[ChatIntent, int] = {}
    for intent, words in KEYWORDS.items():
        total = 0
        for word, weight in words.items():
            if " " in word:
                if word in text:
                    total += weight
            elif word in tokens:
                total += weight
        if total:
            totals[intent] = total
    return totals


#: Words that point at whatever is on screen. A question with none of them and
#: no keyword either is not a question about this product.
_SUBJECT = frozenset({
    "this", "it", "its", "that", "the", "product", "sku", "variant", "item",
    "here", "thing",
})


def _refers_to_subject(question: str) -> bool:
    return bool(set(_normalise(question).split()) & _SUBJECT)


def classify(question: str, *, has_product: bool) -> ChatIntent:
    """Which intent answers this, or UNANSWERABLE.

    ``has_product`` matters because the same words mean different things with
    and without a subject. "What does the standard say about allergens" with no
    product is a corpus question; with a product in hand it is still a corpus
    question, but "tell me about it" is only answerable when there is an "it".
    """
    if not question or not question.strip():
        return ChatIntent.UNANSWERABLE

    totals = score(question)
    best = max(totals.values(), default=0)

    if best < FLOOR:
        # Nothing was named. Falling back to OVERVIEW here used to answer "how
        # do I get to Milton Keynes" with a product summary - technically
        # grounded, and still not an answer to the question asked. So the
        # fallback now requires the question to actually be *about* the thing
        # on screen.
        if has_product and _refers_to_subject(question):
            return ChatIntent.OVERVIEW
        return ChatIntent.UNANSWERABLE

    # Ties break by the order intents are declared above, which runs from the
    # most specific question to the most general - so a question naming both a
    # certificate and a category is answered about the certificate.
    for intent in KEYWORDS:
        if totals.get(intent) != best:
            continue
        if intent in _NEEDS_PRODUCT and not has_product:
            # "What do our standards say about stock" scores for STOCK and for
            # STANDARDS; with no product selected the corpus reading is the
            # only one that means anything. But "where is it stocked" with no
            # product is not a corpus question - it is a question missing its
            # subject, and saying so is better than searching for it.
            if totals.get(ChatIntent.STANDARDS, 0) >= FLOOR:
                return ChatIntent.STANDARDS
            return ChatIntent.UNANSWERABLE
        return intent
    return ChatIntent.UNANSWERABLE


#: Intents that only mean something about a particular product. Asked without
#: one, they fall back to the corpus - "what do our standards say about stock"
#: is a real question even with no SKU selected.
_NEEDS_PRODUCT = frozenset({
    ChatIntent.OVERVIEW, ChatIntent.FEATURES, ChatIntent.READINESS,
    ChatIntent.MEDIA, ChatIntent.STOCK, ChatIntent.SALES,
    ChatIntent.MARKETING, ChatIntent.CONNECTIONS,
})


#: What this surface can answer, in the words it would use to say so. Read out
#: when a question lands on UNANSWERABLE, because "I cannot answer that" is
#: only half an answer without it.
CAPABILITIES: dict[ChatIntent, str] = {
    ChatIntent.OVERVIEW: "what a product is",
    ChatIntent.FEATURES: "its recorded features and specifications",
    ChatIntent.READINESS: "whether it can launch, and what is open",
    ChatIntent.MEDIA: "what imagery it has and what it is missing",
    ChatIntent.COMPLIANCE: "its certificates and where it may be sold",
    ChatIntent.STOCK: "which depots hold it",
    ChatIntent.SALES: "what it is priced at and what it sold",
    ChatIntent.MARKETING: "which campaigns it is in",
    ChatIntent.CONNECTIONS: "what it is connected to",
    ChatIntent.STANDARDS: "what the standards and policies say",
}
