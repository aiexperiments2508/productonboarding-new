"""Asking about a product in words.

The tests worth having here are not about phrasing. They are about the three
properties that make an open-ended question surface safe to put in front of
somebody: it routes deterministically, it answers only from evidence it
actually gathered, and it refuses rather than guesses.

The last of those is the one with teeth. A chat surface that says something
plausible when it knows nothing is worse than no chat surface, because the
reader cannot tell the two apart - so "no evidence" has to come back as a
refusal, with the sources list empty and `grounded` false, every time.

`use_model=False` throughout. The gateway is asked to phrase and nothing else,
so nothing tested here needs it, and a test that reached for a model would be
testing the model rather than this code.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("DB_PATH", "data/test_chat.db")
os.environ["LITELLM_BASE_URL"] = "http://127.0.0.1:4999"
os.environ["KG_BACKEND"] = "memory"

from sc import chat, db  # noqa: E402
from sc.chat import evidence, intents, reply  # noqa: E402
from sc.contracts import ChatIntent  # noqa: E402
from sc.kg import memory, synth  # noqa: E402
from sc.replay import tape  # noqa: E402
from sc.state import baseline as baseline_mod  # noqa: E402

PURIFIER = "VAR-01A"
PURIFIER_SKU = "NAV-AP300-STD"


@pytest.fixture(scope="module")
def pack_file(tmp_path_factory):
    target = tmp_path_factory.mktemp("chat") / "backoffice.jsonl"
    synth.write(target)
    return target


@pytest.fixture(autouse=True)
def fresh(pack_file):
    db.init_db(drop=True)
    baseline_mod.get.cache_clear()
    memory.cache_clear()
    tape.load_tape(reset=True)
    tape.load_reference(pack_file, reset=True)
    yield
    db.close()


def client():
    from fastapi.testclient import TestClient

    from sc.main import app

    return TestClient(app)


# ---------------------------------------------------------------------------
# Routing


def test_each_kind_of_question_reaches_the_surface_that_answers_it():
    """The routing table, exercised as a reader would phrase things.

    Every one of these is a question somebody would actually type, and the
    intent decides which surfaces get read. Getting this wrong is not a
    cosmetic failure: a stock question routed to the corpus searches documents
    for a pallet count and finds nothing, and the reader is told there is no
    stock.
    """
    cases = {
        "what are its features": ChatIntent.FEATURES,
        "what is it made of": ChatIntent.FEATURES,
        "can it launch": ChatIntent.READINESS,
        "what is blocking it": ChatIntent.READINESS,
        "what images does it have": ChatIntent.MEDIA,
        "is it certified": ChatIntent.COMPLIANCE,
        "when does the certificate expire": ChatIntent.COMPLIANCE,
        "where is it stocked": ChatIntent.STOCK,
        "how many are in the warehouse": ChatIntent.STOCK,
        "what did it sell": ChatIntent.SALES,
        "how much does it cost": ChatIntent.SALES,
        "which campaigns is it in": ChatIntent.MARKETING,
        "what is it connected to": ChatIntent.CONNECTIONS,
        "tell me about this": ChatIntent.OVERVIEW,
    }
    for question, expected in cases.items():
        assert intents.classify(question, has_product=True) == expected, question


def test_a_document_speaking_outweighs_the_noun_it_speaks_about():
    """"What do the standards say about allergens" is a corpus question.

    "Allergen" is a strong FEATURES word and "standards" a strong STANDARDS
    one, so on single tokens the two tie and the record wins on declaration
    order - which answers a question about the written policy by reading the
    product's ingredient list. The phrase is what breaks the tie, and it has
    to, because the tie is not close in meaning.
    """
    assert intents.classify("what do the standards say about allergen labelling",
                            has_product=True) is ChatIntent.STANDARDS
    assert intents.classify("what does the policy say about allergens",
                            has_product=True) is ChatIntent.STANDARDS
    # And the same noun, asked about the product, still reaches the record.
    assert intents.classify("what are its allergens",
                            has_product=True) is ChatIntent.FEATURES


def test_a_word_the_table_never_spelled_out_still_routes():
    """Inflections, which is where hand-written keyword tables actually fail.

    Every one of these was a real defect found by asking the surface rather
    than by reading the table: "sell" was missing beside sold and selling,
    "blocking" beside block and blocked, "connect" beside connected. None of
    them looked like a gap until a question missed.
    """
    cases = {
        "what did it sell": ChatIntent.SALES,
        "what is blocking it": ChatIntent.READINESS,
        "what blocks it": ChatIntent.READINESS,
        "what does it connect to": ChatIntent.CONNECTIONS,
        "what problems does it have": ChatIntent.READINESS,
        "has the certificate expired": ChatIntent.COMPLIANCE,
        "what are its specifications": ChatIntent.FEATURES,
    }
    for question, expected in cases.items():
        assert intents.classify(question, has_product=True) == expected, question


def test_expanding_the_table_never_takes_a_word_from_another_intent():
    """The guard that makes the expansion safe to run at all.

    COMPLIANCE weights "market" at 1 because the word is ambiguous. Generating
    inflections without checking what is already spelled out would hand it
    "marketing" as well, and campaign questions would start coming back as
    lists of regulations. Every generated form yields to a hand-written one.
    """
    assert "marketing" in intents.KEYWORDS[ChatIntent.MARKETING]
    assert "marketing" not in intents.KEYWORDS[ChatIntent.COMPLIANCE]

    # No form is claimed twice anywhere in the expanded table.
    seen: dict[str, ChatIntent] = {}
    for intent, words in intents.KEYWORDS.items():
        for word in words:
            assert word not in seen, f"{word} claimed by {seen.get(word)} and {intent}"
            seen[word] = intent


def test_where_it_may_be_sold_is_not_what_it_sold():
    """Two questions sharing their vocabulary, separated by phrasing alone.

    "Sold" is a strong SALES word, so "which markets can it be sold in" - a
    question about lawfulness - came back with a revenue figure.
    """
    assert intents.classify("which markets can it be sold in",
                            has_product=True) is ChatIntent.COMPLIANCE
    assert intents.classify("what did it sell",
                            has_product=True) is ChatIntent.SALES


def test_a_question_about_something_else_entirely_is_not_answered():
    """An off-topic question is refused rather than answered vaguely.

    Falling back to an overview here is tempting and wrong: a reader who asked
    about directions and received a paragraph about pack sizes has been
    ignored, and could reasonably conclude the system misunderstood the
    product rather than the question.
    """
    assert intents.classify("how do I get to Milton Keynes",
                            has_product=True) is ChatIntent.UNANSWERABLE
    answer = chat.ask("how do I get to Milton Keynes", PURIFIER_SKU,
                      use_model=False)
    assert answer.grounded is False
    assert answer.sources == []
    assert answer.intent is ChatIntent.UNANSWERABLE


def test_a_question_needing_a_product_says_so_when_there_is_none():
    """"Where is it stocked" with nothing selected is missing its subject.

    Searching the corpus for it would find nothing and report that as "no
    stock recorded", which is a different and much worse answer than "which
    product?".
    """
    assert intents.classify("where is it stocked",
                            has_product=False) is ChatIntent.UNANSWERABLE
    answer = chat.ask("where is it stocked", None, use_model=False)
    assert answer.grounded is False
    assert "product" in answer.reply.lower()


# ---------------------------------------------------------------------------
# Evidence


def test_an_answer_about_stock_counts_only_this_variants_stock():
    """The regression that matters most in this file.

    Campaigns hang off the product rather than the variant, so an early
    version widened the graph walk through CORE to reach them. That also
    walked back *down* into the product's sibling variants, and their stock,
    certificates and sales arrived labelled as this one's: on VAR-01A it
    turned three stock records into a hundred and eighty-one and one
    certificate into nineteen.

    Nothing about the reply looked wrong. It was fluent, it cited sources, and
    it was wrong by sixty-fold - which is precisely the failure this surface
    exists to make impossible. So the assertion is against the graph's own
    adjacency rather than against a number somebody wrote down.
    """
    from sc.contracts import GraphNodeLabel as L
    from sc.kg import project

    graph = memory.graph()
    root = project.node_id(L.VARIANT, PURIFIER)
    attached = [other for other, _ in graph.neighbours(root)
                if graph.nodes[other].label is L.STOCK_LEVEL]

    ev = evidence.gather("where is it stocked", ChatIntent.STOCK,
                         PURIFIER_SKU)
    cited = [s for s in ev.sources if s.reference in set(attached)]
    stock_sources = [s for s in ev.sources
                     if s.reference and s.reference.startswith("StockLevel:")]

    assert attached, "the seed pack should give this variant some stock"
    assert len(stock_sources) == len(attached)
    assert len(cited) == len(attached)


def test_certificates_named_in_the_graph_match_the_record():
    """Two surfaces, one product, and no room for them to disagree.

    The record carries `compliance.certificate_ref` because a supplier sent
    it; the graph carries a Certificate node because the register did. They
    are built from different lanes by different code, and an answer that cited
    both while they said different things would be worse than one citing
    neither.
    """
    ev = evidence.gather("is it certified", ChatIntent.COMPLIANCE,
                         PURIFIER_SKU)
    from_record = [s.detail for s in ev.sources
                   if s.reference == "compliance.certificate_ref"]
    from_graph = [s.detail for s in ev.sources
                  if s.reference and s.reference.startswith("Certificate:")]
    assert from_record and from_graph

    ref = from_record[0].split(" is ", 1)[1].strip()
    assert any(ref in detail for detail in from_graph), (
        f"the record says {ref} and the graph says {from_graph}")


def test_an_unknown_product_produces_no_evidence_at_all():
    """A typo'd SKU is answered with a refusal, not with the nearest match.

    Guessing which product was meant is how a reader ends up reading a
    confident paragraph about something they did not ask about.
    """
    ev = evidence.gather("what are its features", ChatIntent.FEATURES,
                         "NO-SUCH-SKU")
    assert ev.sources == []
    assert ev.grounded is False
    assert ev.resolved is None


# ---------------------------------------------------------------------------
# Phrasing


def test_the_template_states_a_repeated_finding_once():
    """Two findings can carry the same sentence against different fields.

    Both belong in the sources, where their subjects differ. Neither benefits
    from being read out twice, and a reply that says the same sentence three
    times reads as a fault in the system rather than as three problems.
    """
    ev = evidence.Evidence(intent=ChatIntent.READINESS,
                           headline="The verdict is BLOCKED.")
    for subject in ("description", "marketing_copy", "pack_copy"):
        ev.add("readiness", "banned_phrase",
               "Description contains a medical claim", reference=subject)

    text, _spoken = reply.template("what is wrong", ev)
    assert text.lower().count("medical claim") == 1
    # ...and all three survive as citations, because they are three findings.
    assert len(ev.sources) == 3


def test_the_template_does_not_restate_its_own_headline():
    """The headline summarises the evidence, so the summarised fact is in it.

    Stating the verdict and then restating the verdict is how a surface with
    one thing to say sounds like it has two.
    """
    ev = evidence.Evidence(
        intent=ChatIntent.READINESS,
        headline="The verdict is BLOCKED, with 3 blocking findings.")
    ev.add("readiness", "Verdict", "BLOCKED: 3 of 4 findings block a launch")
    ev.add("readiness", "expiry", "the UKCA certificate expired on 2026-08-01")

    text, _spoken = reply.template("can it launch", ev)
    assert "3 of 4" not in text
    assert "expired on 2026-08-01" in text


def test_an_attribute_path_is_not_capitalised_into_something_else():
    """`compliance.sale_permitted` is an identifier, not the start of a prose
    sentence. Capitalising it names a field that does not exist."""
    ev = evidence.Evidence(intent=ChatIntent.FEATURES, headline="Two things.")
    ev.add("record", "compliance.sale_permitted",
           "compliance.sale_permitted is yes")
    text, _spoken = reply.template("what are its features", ev)
    assert "compliance.sale_permitted" in text
    assert "Compliance.sale_permitted" not in text


def test_the_spoken_answer_drops_the_attribution_the_screen_keeps():
    """The same facts, at the length each sense can take.

    On screen "as recorded by supplier-portal" is the reason to believe the
    sentence. Read aloud it is three seconds of furniture between the listener
    and the next fact, and it is the same claim either way.
    """
    ev = evidence.Evidence(intent=ChatIntent.FEATURES,
                           headline="Two attributes are recorded.")
    ev.add("record", "origin.country",
           "origin.country is Turkey, as recorded by supplier-portal")

    text, spoken = reply.template("what are its features", ev)
    assert "as recorded by supplier-portal" in text
    assert "as recorded by" not in spoken
    assert "Turkey" in spoken


def test_a_refusal_says_what_could_be_asked_instead():
    """"I cannot answer that" is half an answer.

    The missing half is what *can* be asked, and a reader left to guess it
    usually guesses wrong twice and then stops asking.
    """
    text, spoken = reply.refusal(ChatIntent.UNANSWERABLE, has_product=True)
    for capability in intents.CAPABILITIES.values():
        assert capability in text
    assert spoken and "features" in spoken


# ---------------------------------------------------------------------------
# The routes


def test_the_route_answers_and_carries_its_evidence():
    api = client()
    response = api.post("/api/chat/ask", json={
        "question": "where is it stocked", "key": PURIFIER_SKU,
        "use_model": False})
    assert response.status_code == 200

    body = response.json()
    assert body["intent"] == "STOCK"
    assert body["grounded"] is True
    assert body["sources"], "a grounded answer carries what it stands on"
    assert body["resolved"]["entity_id"] == PURIFIER
    assert body["resolved"]["sku"] == PURIFIER_SKU
    assert body["phrased_by"] == "template"
    assert body["spoken"]


def test_the_route_refuses_an_empty_question():
    api = client()
    response = api.post("/api/chat/ask", json={"question": "   "})
    assert response.status_code == 400


def test_the_route_names_what_it_can_answer():
    api = client()
    body = api.get("/api/chat/capabilities").json()
    described = {c["intent"] for c in body["capabilities"]}
    assert "FEATURES" in described
    assert "UNANSWERABLE" not in described, (
        "the refusal is not a capability to advertise")


def test_a_question_longer_than_any_real_question_is_truncated():
    """A paste is not a question, and a prompt whose size follows the input
    is a prompt whose behaviour follows the input."""
    answer = chat.ask("what are its features " + "x" * 5000, PURIFIER_SKU,
                      use_model=False)
    assert len(answer.question) <= chat.MAX_QUESTION


def test_the_chat_routes_hold_no_business_logic():
    """The house rule, applied to the two new handlers.

    A route is a translation between HTTP and a call. The moment one starts
    deciding what to look up there are two places that know how to answer a
    question, and they will disagree.
    """
    import inspect

    from sc import main

    for handler in (main.chat_ask, main.chat_capabilities):
        source = inspect.getsource(handler)
        assert "MATCH" not in source and "MERGE" not in source
        assert "KEYWORDS" not in source and "gather" not in source
        # A handler that phrases its own answer is a second phrasing engine.
        assert "sources" not in source.split('"""')[-1]
