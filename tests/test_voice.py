"""Speech to text, locally.

Two things are worth testing here and neither is transcription accuracy - that
is Whisper's, not ours, and asserting on it would be asserting on a model.

The first is what happens when the optional extra is **absent**, which is the
normal case: a checkout that has not installed `requirements-voice.txt` has to
import, start and serve every route exactly as before, and say so plainly when
asked. That path is tested unconditionally, because it is the one every fresh
clone takes.

The second is the **silence gate**. Whisper hallucinates on silence - three
seconds of digital quiet transcribes as "You", reliably - and without a gate
that word lands in the question box and gets asked as a question. The usual
answer is voice-activity detection, which needs onnxruntime, whose DLL fails
to initialise on the machine this was built on. So the gate is a signal-level
check and the model's own `no_speech_prob`, both of which can be explained to
somebody asking why their recording came back empty.
"""

from __future__ import annotations

import os
import struct
import wave

import pytest

os.environ.setdefault("DB_PATH", "data/test_voice.db")
os.environ["LITELLM_BASE_URL"] = "http://127.0.0.1:4999"

from sc import db, voice  # noqa: E402
from sc.voice import whisper as whisper_mod  # noqa: E402

installed = pytest.mark.skipif(
    not voice.whisper.installed(),
    reason="faster-whisper is optional: pip install -r requirements-voice.txt")


@pytest.fixture(autouse=True)
def fresh():
    # Schema only, and deliberately no `drop=True`. Nothing here depends on
    # what is *in* the database - these are tests of a transcription module
    # and two routes - and dropping means unlinking the file, which on Windows
    # raises PermissionError if a thread the app started at boot still holds a
    # handle to it. A module that does not read the data has no business
    # deleting it.
    db.init_db()
    yield
    db.close()


def wav(path, frames: bytes) -> bytes:
    with wave.open(str(path), "w") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16000)
        handle.writeframes(frames)
    return path.read_bytes()


def client():
    from fastapi.testclient import TestClient

    from sc.main import app

    return TestClient(app)


# ---------------------------------------------------------------------------
# Absent, which is the normal case


def test_the_platform_serves_normally_with_no_speech_extra_installed():
    """The whole point of the optional extra being optional.

    `sc/voice/whisper.py` imports faster_whisper inside a function, the same
    way `sc/kg/driver.py` imports the Neo4j driver, so this holds whether or
    not the 202 MB of compiled wheels are present.
    """
    api = client()
    assert api.get("/api/health").status_code == 200
    body = api.get("/api/chat/voice").json()
    assert set(body) >= {"available", "installed", "model", "note"}
    assert isinstance(body["available"], bool)


def test_the_status_check_never_loads_the_model():
    """A status endpoint that downloaded 75 MB the first time it was polled is
    one nobody could afford to call - and the button polls it on mount."""
    whisper_mod.reset()
    voice.status()
    assert whisper_mod._model is None


def test_asking_for_a_transcript_without_the_extra_says_so_and_does_not_500(
        monkeypatch):
    """The message has to name the fix. "Voice unavailable" sends somebody to
    read the source; naming the requirements file does not."""
    whisper_mod.reset()
    # The real condition, not a stand-in for it: the package is not there.
    monkeypatch.setattr(whisper_mod, "installed", lambda: False)

    with pytest.raises(voice.VoiceUnavailable) as caught:
        voice.transcribe(b"pretend this is audio")
    message = str(caught.value)
    assert "requirements-voice.txt" in message
    # And it does not blame the recording for a missing package - decoding is
    # itself faster-whisper, so the naive ordering reports an ImportError as a
    # corrupt file and sends somebody to debug their microphone.
    assert "could not be decoded" not in message


# ---------------------------------------------------------------------------
# What is refused before anything is decoded


def test_an_empty_recording_is_refused_rather_than_transcribed():
    with pytest.raises(voice.VoiceUnavailable) as caught:
        voice.transcribe(b"")
    assert "no audio" in str(caught.value)


def test_a_recording_larger_than_a_question_is_refused_with_the_numbers():
    """A file pointed at this endpoint should fail in a way somebody can read,
    not tie up a worker thread decoding it."""
    with pytest.raises(voice.VoiceUnavailable) as caught:
        voice.transcribe(b"x" * (voice.MAX_AUDIO_BYTES + 1))
    message = str(caught.value)
    assert "KB" in message and "shorter" in message


# ---------------------------------------------------------------------------
# The silence gate


@installed
def test_silence_comes_back_empty_rather_than_as_a_word(tmp_path):
    """The defect this gate exists for.

    Three seconds of digital quiet transcribes as "You" with no gate. That is
    not a rare edge: it is what happens every time somebody presses the button
    and then changes their mind.
    """
    audio = wav(tmp_path / "silence.wav", struct.pack("<48000h", *([0] * 48000)))
    out = voice.transcribe(audio)
    assert out["heard"] is False
    assert out["text"] == ""


@installed
def test_a_room_with_nobody_speaking_in_it_also_comes_back_empty(tmp_path):
    """Low-level noise clears the amplitude gate, so the model's own
    `no_speech_prob` is what catches this one. Both gates are needed; neither
    catches both cases."""
    import random

    random.seed(7)
    frames = struct.pack("<48000h",
                         *[random.randint(-260, 260) for _ in range(48000)])
    out = voice.transcribe(wav(tmp_path / "room.wav", frames))
    assert out["level"] > voice.whisper.SILENCE_RMS, (
        "this sample is meant to clear the amplitude gate, or it tests nothing")
    assert out["heard"] is False
    assert out["text"] == ""


@installed
def test_audio_that_is_not_audio_is_refused_and_names_the_reason(tmp_path):
    with pytest.raises(voice.VoiceUnavailable) as caught:
        voice.transcribe(b"this is not a media container" * 60)
    assert "could not be decoded" in str(caught.value)


# ---------------------------------------------------------------------------
# The route


@installed
def test_the_route_takes_a_raw_recording_and_answers_with_what_it_heard(
        tmp_path):
    """The body is the recording itself rather than a multipart form: the
    browser has a Blob and this wants bytes."""
    audio = wav(tmp_path / "silence.wav", struct.pack("<32000h", *([0] * 32000)))
    api = client()
    response = api.post("/api/chat/transcribe", content=audio,
                        headers={"Content-Type": "audio/wav"})
    assert response.status_code == 200

    body = response.json()
    assert body["heard"] is False
    assert body["text"] == ""
    assert "took_seconds" in body


def test_the_route_refuses_an_empty_body_as_a_400_not_a_500():
    """A caller who posts nothing has made a mistake they can fix. A stack
    trace does not tell them which one."""
    api = client()
    response = api.post("/api/chat/transcribe", content=b"",
                        headers={"Content-Type": "audio/webm"})
    assert response.status_code == 400
    assert "no audio" in response.json()["detail"]


def test_the_voice_routes_hold_no_transcription_logic():
    """The house rule. A route is a translation between HTTP and a call."""
    import inspect

    from sc import main

    for handler in (main.chat_voice, main.chat_transcribe):
        source = inspect.getsource(handler)
        assert "WhisperModel" not in source
        assert "faster_whisper" not in source
        assert "SILENCE_RMS" not in source


def test_the_audio_is_never_written_to_disk():
    """The claim the whole feature rests on, asserted against the source.

    "The audio never leaves the machine" is worth very little if it is sitting
    in a temp file afterwards. Nothing in this module opens a file for
    writing; the bytes go from the request into BytesIO and are dropped.
    """
    import inspect

    source = inspect.getsource(whisper_mod)
    for forbidden in ('open(', 'NamedTemporaryFile', 'mkstemp', 'write_bytes'):
        assert forbidden not in source, (
            f"{forbidden} in sc/voice/whisper.py - the audio must not be "
            f"written down")
