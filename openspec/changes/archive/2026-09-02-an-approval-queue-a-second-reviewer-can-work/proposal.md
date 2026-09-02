## Why

The pending-approvals count has always been right. The endpoint reads the
checkpoint behind every suspended thread, the navigation badge has always read
it, and it says two.

The screen that exists to action those two says "Nothing awaiting a decision".

Both are telling the truth about different things. Review & Audit can only ever
render one case: whichever thread identifier this browser put in local storage
when it last started a run. **So the queue is server-scoped and the view is
session-scoped**, and the gap between them is a safety-class allergen correction
on a regulated product that no second person can open, approve or reject.

That is not a display bug. Work raised at the end of one shift is counted at the
start of the next and cannot be picked up. **A human-in-the-loop gate only its
own author can see is not a gate** - it is a gate with exactly one key, held by
whoever happened to be at the keyboard, and the whole architecture is built
around that gate holding.

Nothing is missing at the back. Resuming a run by thread identifier already
works, the checkpointer is on disk so a suspended thread survives a restart, and
every panel below the decision already works on whatever run it is handed. The
missing step is the list, and the ability to choose from it.

## What Changes

- **The shell holds the queue as the array it is rather than as a number.** One
  read, two consumers: the badge counts it and the review screen lists it. That
  is what makes a badge reading three beside a screen saying there is nothing to
  do *impossible* rather than merely fixed.
- **Selecting a row loads that thread's checkpoint and adopts it.** Both the
  in-memory reference and the stored identifier move - otherwise re-planning
  would still point at whatever this browser last ran, and a reload would drop
  the reviewer back on somebody else's case.
- **Rows carry the reason to pick one over another**: severity, whether review
  is mandatory, when it was raised, how many fields move, and the product it is
  about. A reviewer with three waiting decisions chooses on the facts rather
  than by opening all three.
- **The row being worked is marked rather than removed**, and marked as disabled
  for assistive technology rather than actually disabled, because it is the row
  most likely to be tabbed back to and a disabled control leaves the tab order.
- **The empty state keeps its old words for the case where they are true.** When
  the queue is not empty it says so and points at it.

## Capabilities

### Modified Capabilities

- `run-and-review-api`: the pending list is the queue, and every surface that
  reports on it - a count and a list alike - reads that one list.

## Impact

- `frontend/src/app/App.tsx` - the queue held as an array, one read, two
  consumers.
- `frontend/src/components/Approvals.tsx` - the list, the selection, the
  adoption of the selected thread.
- `frontend/src/api.ts` - the pending read.

No server change. The endpoint, the resume route and the on-disk checkpointer
are all already correct; what was missing was a client that read the list rather
than one identifier.
