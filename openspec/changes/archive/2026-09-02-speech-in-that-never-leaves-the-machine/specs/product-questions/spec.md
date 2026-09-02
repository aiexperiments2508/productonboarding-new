## ADDED Requirements

### Requirement: A question may be spoken, and the panel is unchanged where it cannot be

A question SHALL be askable by voice as well as by typing, transcribed by the
platform itself.

Typing SHALL remain the primary path. Where the speech capability is not
installed, the panel SHALL work exactly as before and SHALL NOT offer the
control - the availability of an optional input is not a reason for the surface
to change shape.

A transcribed question SHALL be routed and answered by the same deterministic
path a typed one takes. Speech changes how the question arrives and nothing
about how it is answered.

Where the browser refuses microphone access, the panel SHALL report that the
browser blocked it rather than failing silently.

#### Scenario: The panel works with no speech capability installed

- **WHEN** the platform runs without the speech extra
- **THEN** the panel serves and answers typed questions as before, offering no
  microphone control
- **AND** `tests/test_voice.py::test_the_platform_serves_normally_with_no_speech_extra_installed`
  asserts the serving half; the control's absence follows from the availability
  check, asserted by `::test_the_status_check_never_loads_the_model`

#### Scenario: A blocked microphone is reported, not swallowed

- **WHEN** the browser refuses microphone access
- **THEN** the panel says the browser blocked the microphone
- **AND** this is verified by use; the automation browser blocks capture, so the
  path was exercised as far as its refusal
