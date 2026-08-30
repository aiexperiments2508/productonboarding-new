## MODIFIED Requirements

### Requirement: The fallback list is parsed from the shipped configuration

Where the gateway cannot answer, the model list SHALL be parsed from the shipped
gateway configuration rather than duplicated in code, so it cannot drift from
what the gateway would actually serve. The listing SHALL say whether it came from
the gateway or from the fallback, and SHALL carry the reason it fell back, so a
stale list is never presented as current.

**No model identifier SHALL appear in application code at all** - not as a
default, not as a last-resort fallback, and not as a tier hint's example. Two
such lists survived in the client for exactly this purpose and both had gone
stale against the shipped configuration, so an outage produced a picker whose
every entry the gateway would have refused. A wrong answer offered confidently
is worse than none.

Where neither the gateway nor the configuration names a model, the system SHALL
say that no model is available rather than returning an invented alias. A caller
handed a name will use it, and the refusal then surfaces from inside a run
instead of at the point where the cause is obvious.

#### Scenario: With no gateway reachable the list is the shipped aliases

- **WHEN** the model list is refreshed against an unreachable gateway
- **THEN** the listing reports the fallback as its source, carries an error, and
  holds exactly the aliases named in the shipped configuration, including at
  least one embedding model
- **AND** `tests/test_models.py::test_fallback_is_parsed_from_the_shipped_config`
  asserts each, against the file rather than against a hard-coded alias

#### Scenario: No model identifier is written in the application

- **WHEN** the application's own modules are searched for a model identifier
- **THEN** none appears outside the shipped gateway configuration and the
  environment
- **AND** `tests/test_models.py::test_no_model_is_named_in_application_code`
  asserts the absence

#### Scenario: With nothing served and nothing configured, the answer is none

- **WHEN** a tier is resolved with no gateway reachable and no configuration
  present
- **THEN** the caller is told no model is available, and no alias is returned
- **AND** `tests/test_models.py::test_no_model_available_is_said_rather_than_invented`
  asserts both
