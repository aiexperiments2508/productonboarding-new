## Context

Every decision here follows from one sentence: the audio never leaves the
machine. That rules out the cheap implementation, forces a dependency the
project's own rules would otherwise refuse, and turns "nothing is written to
disk" into a property that has to be asserted rather than intended.

## Decisions

### The browser's own recognition API is refused

It is four lines and no dependency. In one major browser it also **uploads the
recording to Google**.

For a system whose whole argument is that it can say where every fact came from,
sending a user's audio to a third party to find out what they said is the wrong
trade. It is also invisible once made: nothing in the interface would show it,
and nobody reviewing the feature later would find it without reading the API's
documentation.

### The dependency rule is broken deliberately, and the requirements file says so

The rule the other extras keep is that a **pure-Python dependency that does
something we cannot meaningfully test is worth taking; a compiled one is not**.
This fails that four times over and is 202 MB installed.

The rule exists to stop taking a compiled wheel for something that could be
hand-rolled. Speech recognition is not that. So the exception is argued in the
requirements file itself rather than left for somebody to discover and wonder
about - a rule broken silently reads as a rule nobody was applying.

### Optional, and off until installed

The library is imported **inside a function**, exactly as the graph driver
imports its database driver. A checkout without the extra still imports, starts
and serves every route; the availability endpoint answers that it is
unavailable, and the button does not render.

Typing is the primary path and always was. This is an addition to a working
surface, not a new way in.

The availability check must not load the model - a status endpoint that pulled
202 MB of weights into memory to answer "is this installed" would make the
check more expensive than the feature.

### The native runtime is pinned

A later version loads the model and dies with an access violation on the
processor this was built on, with **no Python traceback, because the crash is in
native code**. A version that segfaults on the hardware in front of us is not
one to leave floating on a range specifier.

### Two gates, neither of them voice-activity detection

The model hallucinates on silence: three seconds of digital quiet transcribes as
a word, reliably. Without a gate that word lands in the question box and gets
asked.

Voice-activity detection is the usual answer. It needs a runtime whose library
fails to initialise on this machine, so it is not available.

So there are two gates instead:

- **signal level, checked before the model is even loaded** - which is also the
  cheap one, and rejects silence without paying for a transcription;
- **the model's own no-speech probability**, afterwards.

Measured, neither is a close call: speech at RMS 0.076 against silence at 0.0,
and no-speech 0.001 against 0.713. And unlike voice-activity detection, each can
be **explained to somebody asking why their recording came back empty**, which
matters for a feature whose failure mode is silent by definition.

### Raw body, in-memory decode, and a test that reads the source

The recording is posted as a raw body rather than a multipart form: the browser
has a blob and the endpoint wants bytes, and a form encoding in between is
ceremony.

It is decoded in memory. **Nothing is written to disk, and the test asserts that
against the module source** rather than trusting it - "the audio never leaves
the machine" is worth very little if it is sitting in a temporary file
afterwards, and that is exactly the sort of thing a later refactor adds without
noticing.

## Risks / Trade-offs

- **202 MB and a compiled dependency**, against the project's own stated rule.
  Argued rather than hidden.
- **Live microphone capture was exercised only as far as its refusal.** The
  automation browser blocks it, so the capture path is verified up to the point
  where it reports that the browser blocked the microphone - which it does
  rather than failing silently. End-to-end transcription was verified against
  real speech synthesised locally: two questions, transcribed exactly, in about
  two thirds of a second.
- **A signal-level gate is a threshold.** It is far from the measured values on
  both sides, but a very quiet speaker in a very quiet room is the case that
  would test it.

## Open Questions

- The gate thresholds are measured on one machine's microphone. They are not
  close calls there; whether they stay comfortable across hardware is not known.
