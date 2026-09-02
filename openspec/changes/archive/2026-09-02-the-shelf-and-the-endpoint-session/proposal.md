## Why

Three faults, found by using the build rather than by testing it. Two predate
the bulk change and the third is a latent one it walked into.

**The shop has an empty shelf on every channel.** The storefront names four
SKUs in a constant, and the assortment rebrand renamed every one of them. All
four stopped existing, so the listing lookup correctly answers "not found" four
times and the page says the channel is not carrying any of these lines. True,
and useless: the channels are carrying two hundred and eighty-one, a hundred
and sixty-one and a hundred and twenty lines respectively.

The fix is not a corrected list. **A downstream application should not hold a
copy of the catalogue**, and any list written down there is a list that is
wrong the next time a product is renamed.

**Every price is blank, for the same reason one layer down.** The shop keys its
prices by SKU; the generator keys them by variant. A SKU is a brand's name for
a thing and changes when the brand does.

**The vendor portal hangs on "Loading…", and the cause is the client.** Two
concurrent calls to one endpoint deadlock it permanently. The shared endpoint
opens its MCP session inside whichever HTTP request happens to arrive first,
and the streamable-HTTP transport runs its reader in the task that opened it -
so the session belongs to that request's task, and the moment the request
finishes the reader is inside a scope nobody is in any more. The next call gets
a session whose replies nobody is reading, waits for ever, and holds the
endpoint while it does.

It needs two calls to overlap, which is why it survived three releases: a page
load made one call, and the background poller only overlapped it when a supplier
had something being watched. The bulk change added a second call on page load
and made it certain - a page that had worked for three versions stopped working,
and the reason was in a file that change never touched.

And one gap that is worse than a missing feature. The bulk change makes a
bundle propose new lines, gives each its own submission, puts them in the
Proposed lane and says in three places that a reviewer accepts them. **A
reviewer cannot.** The acceptance function exists, the route exists, the lane
renders - and there is no control anywhere in the interface that calls it, so
the last step of the journey is a shell command. Every surface says the decision
is available and the one place it would be taken is empty.

## What Changes

- **A seventh read on the publication server: what a channel is carrying.** The
  shop asks rather than holding a list. It is scoped to the asking system, like
  the impact read and for the same reason - the lookup deliberately will not
  confirm a SKU a channel does not carry, which is what stops a marketplace
  discovering by exhaustive guessing what the print channel has. Telling a
  channel what is on its own shelf is not that act.
- **Ordered by the catalogue's own order** rather than by SKU. Sorting by SKU
  orders a shop by brand prefix, which is alphabetical rather than meaningful
  and puts a jersey top above the product the demonstration is about.
- **Prices keyed the way the generator keys them**, and a line with no price
  shows none - which is the honest rendering of a price this system does not
  model.
- **The endpoint session is owned by a task of its own, for its whole life.**
  Callers hand it work and wait for an answer; a caller that goes away - a
  browser that navigated, a request that timed out - takes nothing down with it,
  because the call is shielded from its cancellation. A call that does not answer
  inside thirty seconds gives up and the session is reopened, so an endpoint
  wedged some other way recovers instead of needing a process restart. Reusing
  the session now actually works: warm calls go from about two hundred and fifty
  milliseconds to about fifteen.
- **The decision on a proposed line.** The drawer for a card in the Proposed
  lane opens with it. It asks for a name, because accepting a line means the
  retailer takes on responsibility for what it says about something it has never
  sold. The SKU is optional - left empty the platform mints one - and the name
  and category are not asked for at all, because they came from the supplier and
  a reviewer should accept the line they were shown rather than retype it.
- **What it says afterwards is the part worth keeping.** An accepted line
  arrives with no attributes and no imagery, so it goes straight to being with
  its supplier and reads as incomplete - and the confirmation says so, rather
  than reporting a product created and letting somebody discover later that it
  holds nothing. Accepting is also not publishing, and the panel says that too.

## Capabilities

### Modified Capabilities

- `review-and-publish`: a channel may ask what it is carrying, scoped to itself
  and in the catalogue's own order.
- `protocol-surfaces`: the shared endpoint owns its session for the session's
  whole life, so concurrent callers and cancelled ones cannot wedge it.
- `bulk-onboarding`: the decision a reviewer takes on a proposed line is
  reachable from the interface that claims it is available.

## Impact

- `sc/estate/publication_server.py` - the shelf read, scoped to the asking
  system.
- `apps/storefront/server.py`, `web/shop.js` - the shop asks instead of holding
  a list, and keys prices the way the generator does.
- `apps/_mcp.py` - the session lives in a task of its own; calls are shielded
  and time out.
- `frontend/src/components/...` - the acceptance panel, first in the drawer on a
  proposal.
- `tests/test_publication.py`, `tests/test_app_boundary.py`.
