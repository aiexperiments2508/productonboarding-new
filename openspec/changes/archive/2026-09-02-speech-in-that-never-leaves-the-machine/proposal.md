## Why

The Ask panel takes typed questions and speaks its answers back. Speech *in* is
the obvious next step, and there is a four-line way to do it: the browser's own
speech recognition API, no dependency, no server work.

**In one major browser that API uploads the recording to Google.** For a system
whose entire argument is that it can say where every fact came from, sending a
user's audio to a third party to find out what they said is the wrong trade -
and it is the kind of trade that is invisible once made, because nothing in the
interface would indicate it.

So the recognition has to run in the platform's own process, which means a
dependency, which is where this gets awkward: the dependency rule the other
extras keep says a pure-Python dependency that does something untestable is
worth taking and a compiled one is not. **This fails that test four times over,
and it is taken anyway.** The rule exists to stop taking a compiled wheel for
something that could be hand-rolled, and speech recognition is not that.

## What Changes

- **Speech in, transcribed in the platform's own process.** Nothing is uploaded.
- **Optional and off until installed.** The recognition library is imported
  inside a function, exactly as the graph driver imports its database driver, so
  a checkout without the extra still imports, starts and serves every route. The
  availability endpoint answers that it is unavailable and the button does not
  render. **Typing is the primary path and always was.**
- **The requirements file argues the exception rather than leaving it to be
  discovered.** It breaks the rule the other extras keep, it is 202 MB
  installed, and both are written down where somebody deciding whether to
  install it will read them.
- **The native runtime is pinned to a known-good version.** A later one loads
  the model and dies with an access violation on the processor this was built
  on - no traceback, because the crash is in native code. A version that
  segfaults is not one to leave floating.
- **Two gates against hallucinated speech.** The model transcribes three seconds
  of digital silence as a word, reliably, and without a gate that word lands in
  the question box and gets asked. Voice-activity detection is the usual answer
  and needs a runtime whose library fails to initialise on this machine, so the
  gate is **signal level, checked before the model is even loaded**, and the
  model's own no-speech probability afterwards. Measured: speech at RMS 0.076
  against silence at 0.0, and no-speech 0.001 against 0.713. Neither gate is a
  close call, and unlike voice-activity detection each can be explained to
  somebody asking why their recording came back empty.
- **The recording is posted as a raw body** rather than a multipart form - the
  browser has a blob and the endpoint wants bytes - and is decoded in memory.
  **Nothing is written to disk, and a test asserts that against the module
  source** rather than trusting it, because "the audio never leaves the machine"
  is worth very little if it is sitting in a temporary file afterwards.

## Capabilities

### New Capabilities

- `voice-input`: transcribing a spoken question in-process, gated against
  silence, with nothing written to disk and nothing uploaded.

### Modified Capabilities

- `product-questions`: a question may be spoken as well as typed, and the panel
  works unchanged where the extra is not installed.

## Impact

- `sc/voice/whisper.py` - the transcription, the two gates, the in-memory
  decode.
- `sc/main.py` - the availability check and the transcription route, holding no
  transcription logic.
- `requirements-voice.txt` - the dependency, the pin, and the argument for both.
- `frontend/src/components/chat/` - the microphone button, rendered only where
  the platform reports the capability available.
- `tests/test_voice.py`.
