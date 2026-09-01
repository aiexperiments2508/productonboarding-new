"""Turning speech into a question, on this machine and nowhere else.

The Ask panel takes typing as its primary path and always will. This is the
other way in, and the one constraint that shaped it is that the audio does not
leave the machine: the browser's own `SpeechRecognition` API would have been
four lines and no dependency, and in Chrome it uploads the recording to
Google's servers. For a system whose entire argument is that it can say where
every fact came from, that was the wrong trade.

So the model runs here. `whisper.py` imports `faster_whisper` *inside* a
function, exactly as `sc/kg/driver.py` imports the Neo4j driver, which means a
checkout without `requirements-voice.txt` installed still imports, still
starts, and still serves every route - `GET /api/chat/voice` simply answers
`available: false` and the microphone button never renders.
"""

from __future__ import annotations

from sc.voice.whisper import (  # noqa: F401
    MAX_AUDIO_BYTES,
    VoiceUnavailable,
    available,
    status,
    transcribe,
)
