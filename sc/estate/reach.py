"""What a payload is about.

An event's payload names the things it concerns, and it does not do so in one
way. The tape predates the estate: a supplier feed says ``entity_id``, a
channel acknowledgement says ``variant_id`` and ``listing_id``, a specification
document and an email both say ``entities`` as a list and ``product`` as a
scalar. All of them are naming products; only the first spelling was ever read.

That single omission is why six of the eleven systems drew on the Ingest Fabric
as boxes with no connectors. ``marketplace-connector`` and ``imaging-dam`` had
delivered dozens of events and every one of them said ``variant_id``;
``label-artwork``, ``regulatory-feed``, ``market-signals`` and
``translation-service`` had delivered documents and emails and every one of
them said ``entities``. The map was not wrong about the estate - it was reading
one of five spellings and reporting the other four as silence.

Two callers need this and they must not answer it differently: the map, which
asks "which sources has this system fed", and the arrival window, which asks
"which products did anything arrive for between these dates". A second copy
would drift, and the first thing it would drift about is the spelling nobody
remembered to add.

Resolution is two bounded hops and deliberately not a graph walk: a listing
names a variant, a variant names a product, a product names a supplier. Nothing
here follows an edge it was not handed.
"""

from __future__ import annotations

#: Payload keys that carry an identifier directly. Order is not significance -
#: every one of them is read, because an event can name a variant and a listing
#: and mean both.
SCALAR_KEYS = ("entity_id", "product_id", "variant_id", "product", "listing_id")

#: Payload keys that carry a list of identifiers.
LIST_KEYS = ("entities", "applies_to")


def refs_of(payload: dict) -> list[str]:
    """Every identifier this payload names, in a stable order.

    Deduplicated, because a channel status names its variant twice - once
    directly and once through its listing - and counting it twice would make
    one delivery look like two.
    """
    found: list[str] = []
    for key in SCALAR_KEYS:
        value = payload.get(key)
        if isinstance(value, str) and value and value not in found:
            found.append(value)
    for key in LIST_KEYS:
        values = payload.get(key)
        if isinstance(values, list):
            for value in values:
                if isinstance(value, str) and value and value not in found:
                    found.append(value)
    return found


def products_of(base, payload: dict) -> set[str]:
    """The products this payload concerns.

    A listing resolves through its variant; a variant through the catalog; a
    product is already one. Anything that resolves to nothing - a channel id, a
    document id, a rule - is dropped rather than guessed at, because an event
    about a document is genuinely not an event about a product.
    """
    products: set[str] = set()
    for ref in refs_of(payload):
        listing = base.listings.get(ref)
        if listing is not None:
            ref = listing.variant_id
        product = base.product_of_variant.get(ref, ref)
        if product in base.products:
            products.add(product)
    return products


def suppliers_of(base, payload: dict) -> set[str]:
    """The sources this payload concerns.

    ``payload["supplier"]`` is honoured directly when it is present and names a
    supplier the catalog has - a specification document says whose document it
    is, and resolving that through the product would be a longer way to the
    same answer that fails when the document names no product yet.
    """
    suppliers: set[str] = set()
    named = payload.get("supplier")
    if isinstance(named, str) and named in _known_suppliers(base):
        suppliers.add(named)
    for product_id in products_of(base, payload):
        supplier = getattr(base.products.get(product_id), "supplier", None)
        if supplier:
            suppliers.add(supplier)
    return suppliers


def _known_suppliers(base) -> set[str]:
    """Which supplier ids the catalog actually has.

    Derived from the products rather than read off a supplier table, because
    there is no supplier table - a supplier is a node on the map and an
    attribute of a product. Checking rather than trusting matters here: the
    tape carries a ``supplier`` key on documents, and a payload naming a
    supplier the catalog has never heard of should draw no edge rather than a
    line to nowhere.
    """
    return {p.supplier for p in base.products.values() if p.supplier}
