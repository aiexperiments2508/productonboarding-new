## Purpose

Transcribing a spoken question in the platform's own process, so the recording
never leaves the machine.

The browser's own recognition API would be four lines and no dependency, and in
one major browser it uploads the recording to a third party. For a system whose
whole argument is that it can say where every fact came from, that is the wrong
trade - and an invisible one, because nothing in the interface would show it.

## ADDED Requirements

### Requirement: Transcription happens in this process, and the audio is never written to disk

A spoken question SHALL be transcribed in the platform's own process. The
recording SHALL NOT be sent to any external service.

The recording SHALL be decoded in memory and SHALL NOT be written to disk. This
SHALL be asserted against the module's own source rather than assumed - "the
audio never leaves the machine" is worth very little if it is sitting in a
temporary file afterwards, and a temporary file is exactly the sort of thing a
later change adds without noticing.

#### Scenario: The audio is never written to disk

- **WHEN** the transcription module is examined
- **THEN** it writes no audio to disk
- **AND** `tests/test_voice.py::test_the_audio_is_never_written_to_disk` asserts
  it against the module source

### Requirement: The capability is optional and the platform serves without it

The recognition library SHALL be imported inside a function rather than at
module load, so an installation without it still imports, starts and serves
every route.

The availability check SHALL answer without loading the model. A status endpoint
that pulled the model weights into memory to answer "is this installed" would be
more expensive than the feature it reports on.

Where the extra is absent, a transcription request SHALL say so rather than
failing, and the interface SHALL NOT offer the control. Typing SHALL remain the
primary path.

#### Scenario: The platform serves normally with the extra absent

- **WHEN** the platform runs with no speech extra installed
- **THEN** every route still serves
- **AND** `tests/test_voice.py::test_the_platform_serves_normally_with_no_speech_extra_installed`
  asserts it

#### Scenario: The status check does not load the model

- **WHEN** availability is checked
- **THEN** the model is not loaded
- **AND** `tests/test_voice.py::test_the_status_check_never_loads_the_model`
  asserts it

#### Scenario: A request without the extra is answered, not an error

- **WHEN** a transcription is requested with the extra absent
- **THEN** the response says so and is not a server error
- **AND** `tests/test_voice.py::test_asking_for_a_transcript_without_the_extra_says_so_and_does_not_500`
  asserts it

### Requirement: Silence comes back empty, gated twice and explainably

The model transcribes digital silence as a word, reliably. Without a gate that
word lands in the question box and is asked.

A recording SHALL be gated on signal level **before the model is loaded**, and
on the model's own no-speech probability afterwards. Both SHALL return an empty
result rather than a transcription.

Voice-activity detection is the conventional answer and is not used: its runtime
does not initialise on the target machine. The two gates chosen are also
preferable in one respect that outlasts that - each **can be explained to
somebody asking why their recording came back empty**, which matters for a
feature whose failure mode is silent by definition.

The thresholds SHALL be recorded with the measurements behind them, so neither
reads as arbitrary.

#### Scenario: Digital silence transcribes as nothing

- **WHEN** a silent recording is submitted
- **THEN** the result is empty rather than a word
- **AND** `tests/test_voice.py::test_silence_comes_back_empty_rather_than_as_a_word`
  asserts it

#### Scenario: A room with nobody speaking also comes back empty

- **WHEN** a recording carrying room noise but no speech is submitted
- **THEN** the result is empty
- **AND** `tests/test_voice.py::test_a_room_with_nobody_speaking_in_it_also_comes_back_empty`
  asserts it

### Requirement: The route takes bytes, refuses by name, and holds no transcription logic

The recording SHALL be accepted as a raw body rather than a multipart form - the
browser holds a blob and the endpoint wants bytes.

An empty recording, a recording larger than a question could be, audio that is
not audio, and an empty body SHALL each be refused with a reason a caller can
act on, the size refusal naming the numbers. An empty body SHALL be a bad
request rather than a server error.

The route SHALL hold no transcription logic of its own.

#### Scenario: A raw recording is answered with what was heard

- **WHEN** a recording is posted as a raw body
- **THEN** the response carries what was heard
- **AND** `tests/test_voice.py::test_the_route_takes_a_raw_recording_and_answers_with_what_it_heard`
  asserts it

#### Scenario: Each bad recording is refused by name

- **WHEN** an empty recording, an oversized one, audio that is not audio, and an
  empty body are each submitted
- **THEN** each is refused with its reason, the size refusal naming the numbers,
  and the empty body as a bad request
- **AND** `tests/test_voice.py::test_an_empty_recording_is_refused_rather_than_transcribed`,
  `::test_a_recording_larger_than_a_question_is_refused_with_the_numbers`,
  `::test_audio_that_is_not_audio_is_refused_and_names_the_reason` and
  `::test_the_route_refuses_an_empty_body_as_a_400_not_a_500` assert each

#### Scenario: The route delegates

- **WHEN** the route body is examined
- **THEN** it holds no transcription logic
- **AND** `tests/test_voice.py::test_the_voice_routes_hold_no_transcription_logic`
  asserts it
