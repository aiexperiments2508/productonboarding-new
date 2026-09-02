## Why

Two claims this system makes were not quite true.

**"Nothing names a model in code."** Almost. The README said it, the tier
registry made it true for every call the graph issues, and the environment
template explained how to pin one. But two lists of aliases survived in the
gateway client as the offline fallback - `FAST_MODELS` and `REASONING_MODELS` -
along with a default embedding alias and a last-resort `"gemini-flash"` in the
registry itself. Every one of them had drifted from `litellm/config.yaml`: not
one of the six appears in the shipped configuration. So a gateway outage, the
exact case they existed for, produced a model picker whose every entry the
gateway would have refused.

**"Agents broadcast their capabilities."** Also almost. Four Agent Cards were
published, each at the address the A2A specification puts it, and each one
correct. What was missing was the directory. A peer that already knows an
agent's identifier can fetch its card; a peer that knows only the host cannot
find out what is here. Every agent broadcasting its own capability is not the
same as the estate having one, and the difference shows the moment somebody asks
"what can this system do" and has to be handed a list by a person.

There is also a new question the estate change created and did not answer.
Connecting a system records what it says it can do. Nothing said whether any of
it became callable by a model - and "the tools sync automatically" is exactly
the kind of convenience that quietly turns an allowlist into a formality.

## What Changes

- **No model identifier anywhere in application code.** The alias lists go; the
  gateway client asks the registry, which parses the shipped configuration
  rather than duplicating it. Where neither a gateway nor a configuration names
  a model, the system says no model is available instead of returning an
  invented alias - a caller handed a name will use it, and the refusal then
  surfaces from inside a run rather than where the cause is obvious.
- **A guard against the fix being undone.** A test greps the application for a
  provider alias, because reintroducing one as a "sensible default" is how the
  stale lists arrived the first time and it reads as helpful in review.
- **One discoverable directory** at `/.well-known/agent-cards.json`, built from
  the same cards it lists rather than from a separate inventory - a directory
  assembled from its own list of names drifts within a release, and drifts
  silently.
- **Implemented and reachable capabilities kept apart.** A peer is something
  this system does; a connected system is something it knows how to ask.
  Flattening them would claim this estate can do things it can only delegate.
- **What a capability may not do, stated.** The approval gate and publishing are
  deliberately not peers. A directory that merely omits them invites a reader
  to conclude they were forgotten.
- **Discovery is not admission, made mechanical.** A connected system's tools
  become visible immediately and callable never - until an operator admits
  specific ones, and only while that system is answering.

## Capabilities

### New Capabilities

- `capability-registry`: one document naming everything this estate can do, so
  that a caller who knows only the address can find out what is here.

### Modified Capabilities

- `model-gateway`: no model identifier originates in application code, and the
  absence of one is reported rather than papered over.
- `evidence-desk`: an admitted tool from a connected system joins the
  catalogue, named with its system; connecting one widens nothing.

`protocol-surfaces` is deliberately **not** modified. The directory is a new
surface rather than a change to the transports and toolset ownership that
capability describes, and folding it in would blur a boundary that spec is
careful about.

## Impact

- `sc/llm/gateway.py` - the alias lists and the embedding default removed;
  `available_models` delegates to the registry.
- `sc/llm/models.py` - the last-resort alias replaced with an explicit "no model
  available".
- `sc/a2a/directory.py` - new: the directory, built from the served cards.
- `sc/graph/evidence.py` - `admitted_tools`, and the catalogue rendering that
  names an admitted tool with its system.
- `sc/main.py` - the well-known route.
- `frontend/src/components/CapabilityBoard.tsx` - new, in System Control.
- `tests/test_directory.py` - new. `tests/test_models.py` - the grep guard and
  the no-model-available case.
