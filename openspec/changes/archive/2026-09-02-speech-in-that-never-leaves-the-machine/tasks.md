## 1. In-process, and optional

- [x] 1.1 Transcribe in the platform's own process rather than through the
      browser API that uploads the recording
- [x] 1.2 Import the library inside a function, so a checkout without the extra
      still imports, starts and serves every route; verify via
      `tests/test_voice.py::test_the_platform_serves_normally_with_no_speech_extra_installed`
- [x] 1.3 Answer the availability check without loading the model; verify via
      `tests/test_voice.py::test_the_status_check_never_loads_the_model`
- [x] 1.4 Say so and do not fail where the extra is absent; verify via
      `tests/test_voice.py::test_asking_for_a_transcript_without_the_extra_says_so_and_does_not_500`
- [x] 1.5 Render the microphone button only where the platform reports the
      capability available, keeping typing the primary path
- [x] 1.6 Argue the dependency exception in `requirements-voice.txt` - it breaks
      the rule the other extras keep and is 202 MB installed - rather than
      leaving it to be discovered
- [x] 1.7 Pin the native runtime to the version that does not die with an access
      violation on this processor, the crash being in native code with no Python
      traceback

## 2. Two gates against a hallucinated word

- [x] 2.1 Gate on signal level before the model is loaded, so silence costs no
      transcription; verify via
      `tests/test_voice.py::test_silence_comes_back_empty_rather_than_as_a_word`
- [x] 2.2 Gate on the model's own no-speech probability afterwards; verify via
      `tests/test_voice.py::test_a_room_with_nobody_speaking_in_it_also_comes_back_empty`
- [x] 2.3 Record the measurements behind both gates - speech at RMS 0.076
      against silence at 0.0, no-speech 0.001 against 0.713 - so neither reads as
      an arbitrary threshold
- [x] 2.4 Prefer these to voice-activity detection, whose runtime fails to
      initialise here, and because each can be explained to somebody asking why
      their recording came back empty

## 3. Refusals

- [x] 3.1 Refuse an empty recording rather than transcribing it; verify via
      `tests/test_voice.py::test_an_empty_recording_is_refused_rather_than_transcribed`
- [x] 3.2 Refuse a recording larger than a question could be, naming the
      numbers; verify via
      `tests/test_voice.py::test_a_recording_larger_than_a_question_is_refused_with_the_numbers`
- [x] 3.3 Refuse audio that is not audio, naming the reason; verify via
      `tests/test_voice.py::test_audio_that_is_not_audio_is_refused_and_names_the_reason`
- [x] 3.4 Refuse an empty body as a bad request rather than an error; verify via
      `tests/test_voice.py::test_the_route_refuses_an_empty_body_as_a_400_not_a_500`

## 4. The route

- [x] 4.1 Take the recording as a raw body and answer with what was heard, the
      browser having a blob and the endpoint wanting bytes; verify via
      `tests/test_voice.py::test_the_route_takes_a_raw_recording_and_answers_with_what_it_heard`
- [x] 4.2 Hold no transcription logic in the route; verify via
      `tests/test_voice.py::test_the_voice_routes_hold_no_transcription_logic`

## 5. Nothing on disk

- [x] 5.1 Decode in memory and write nothing to disk; verify via
      `tests/test_voice.py::test_the_audio_is_never_written_to_disk`, which
      asserts it against the module source rather than trusting it

## 6. Verification

- [x] 6.1 Verify end to end against real speech synthesised locally: two
      questions, transcribed exactly, in about two thirds of a second
- [ ] 6.2 Exercise live microphone capture end to end. It is blocked in the
      automation browser, so the capture path is verified only as far as its
      refusal - which reports that the browser blocked the microphone rather than
      failing silently
