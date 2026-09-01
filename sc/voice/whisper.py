"""Local speech-to-text. The audio never leaves this process.

Everything here is arranged around one property: `faster_whisper` is imported
inside a function, never at module scope. The package is a 202 MB optional
extra, and a checkout without it has to import, start and serve normally - so
nothing above this line may depend on it existing.
"""

from __future__ import annotations

import io
import os
import threading
import time

#: Refused above this. A question is a sentence, and a sentence is a few
#: seconds of Opus - well under a megabyte. Anything larger is a file somebody
#: has pointed at this endpoint, and decoding it would tie up a worker thread
#: for as long as it takes rather than failing in a way they can read.
MAX_AUDIO_BYTES = 8 * 1024 * 1024

#: Below this root-mean-square amplitude the recording is treated as silence
#: and the model is not run at all.
#:
#: This exists because Whisper hallucinates on silence: three seconds of
#: digital quiet transcribes as "You", every time, and without a gate that
#: word lands in the question box and gets asked. Measured on this machine,
#: speech sits at RMS 0.076 and digital silence at 0.0, so the threshold has
#: nearly two orders of magnitude of headroom either side - it cannot plausibly
#: reject somebody speaking quietly.
SILENCE_RMS = 0.002

#: ...and the model's own opinion, for a recording that has signal in it but no
#: speech - a room, a cough, a knocked microphone. Silence scored 0.713 here
#: and speech scored 0.001, so this is not a close call either.
#:
#: Between them these two do the job voice-activity detection would have done,
#: without making onnxruntime load-bearing - and unlike VAD, each one can be
#: explained to somebody asking why their recording came back empty.
NO_SPEECH_PROB = 0.6

#: The default model. `base.en` is ~75 MB and transcribes a spoken question in
#: well under a second on CPU; `tiny.en` is half the size and noticeably worse
#: at product vocabulary, which is the only vocabulary this hears. Overridable
#: because the right answer depends on the machine, and a directory path works
#: here too - which is how an air-gapped install skips the download entirely.
DEFAULT_MODEL = "base.en"

#: int8 on CPU. float16 is a GPU compute type and asking for it on CPU makes
#: faster-whisper fall back with a warning rather than fail, which is a
#: confusing way to get slower.
DEFAULT_COMPUTE = "int8"


class VoiceUnavailable(RuntimeError):
    """Raised when transcription was asked for and cannot be done.

    Carries the reason rather than a boolean, because "not installed", "the
    model could not be fetched" and "that audio would not decode" need three
    different things doing about them.
    """


_lock = threading.Lock()
_model = None
_load_error: str | None = None


def _settings() -> dict:
    return {
        "model": os.environ.get("WHISPER_MODEL", DEFAULT_MODEL),
        "device": os.environ.get("WHISPER_DEVICE", "cpu"),
        "compute_type": os.environ.get("WHISPER_COMPUTE", DEFAULT_COMPUTE),
    }


def _vad_enabled() -> bool:
    return os.environ.get("WHISPER_VAD", "").strip().lower() in {"1", "true", "yes"}


def installed() -> bool:
    """Whether the optional extra is present. Cheap, and does no loading."""
    from importlib.util import find_spec

    try:
        return find_spec("faster_whisper") is not None
    except (ImportError, ValueError):
        return False


def _load():
    """The model, loaded once and kept.

    Loading takes about a second and the first call also downloads ~75 MB, so
    it happens on first use rather than at startup: a platform that paused for
    a model download before serving its first request would be paying for a
    feature most sessions never touch.

    A failure is cached too. Retrying a download that failed once, on every
    request, turns a broken network into a hung page.
    """
    global _model, _load_error

    if _model is not None:
        return _model
    if _load_error is not None:
        raise VoiceUnavailable(_load_error)

    with _lock:
        if _model is not None:
            return _model
        if _load_error is not None:
            raise VoiceUnavailable(_load_error)
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            _load_error = ("speech-to-text is not installed - "
                           "pip install -r requirements-voice.txt")
            raise VoiceUnavailable(_load_error) from exc

        settings = _settings()
        try:
            _model = WhisperModel(settings["model"], device=settings["device"],
                                  compute_type=settings["compute_type"])
        except Exception as exc:
            _load_error = (f"could not load the {settings['model']} model: "
                           f"{exc}")
            raise VoiceUnavailable(_load_error) from exc
        return _model


def available() -> bool:
    """Installed *and* loadable. Does not load: see `status` for that."""
    return installed() and _load_error is None


def status() -> dict:
    """What the microphone button needs to know before it renders itself.

    Deliberately does not load the model. A status endpoint that took a second
    and downloaded 75 MB the first time it was polled would be a status
    endpoint nobody could afford to call.
    """
    settings = _settings()
    return {
        "available": available(),
        "installed": installed(),
        "loaded": _model is not None,
        "model": settings["model"],
        "device": settings["device"],
        "compute_type": settings["compute_type"],
        "vad": _vad_enabled(),
        "max_bytes": MAX_AUDIO_BYTES,
        "error": _load_error,
        # Said plainly because it is the reason this is here rather than four
        # lines of the browser's own SpeechRecognition API.
        "note": ("audio is transcribed in this process and is never uploaded "
                 "anywhere"),
    }


def transcribe(audio: bytes, *, language: str | None = "en") -> dict:
    """One recording, as text. Raises VoiceUnavailable rather than returning
    an empty string, because silence and "this did not work" are different.

    The bytes go straight to faster-whisper, which decodes them with PyAV -
    so whatever the browser's MediaRecorder produced (Opus in WebM on Chrome,
    Opus in Ogg on Firefox) is handled without this module knowing which.
    Nothing is written to disk on the way.
    """
    if not audio:
        raise VoiceUnavailable("no audio was received")
    if len(audio) > MAX_AUDIO_BYTES:
        raise VoiceUnavailable(
            f"that recording is {len(audio) // 1024} KB and the limit is "
            f"{MAX_AUDIO_BYTES // 1024} KB - ask a shorter question")

    # Checked before decoding, because decoding is itself faster-whisper: on a
    # checkout without the extra the ImportError surfaces from _decode and
    # reads "that audio could not be decoded", which blames the recording for
    # a missing package and sends somebody to debug their microphone.
    if not installed():
        raise VoiceUnavailable("speech-to-text is not installed - "
                               "pip install -r requirements-voice.txt")

    started = time.time()
    try:
        samples = _decode(audio)
    except Exception as exc:
        raise VoiceUnavailable(
            f"that audio could not be decoded: {exc}") from exc

    # Gate before the model is even loaded, not after it has spoken. Running
    # Whisper on silence does not produce nothing - it produces a plausible
    # short word - and somebody who pressed the button by accident should not
    # trigger a 75 MB download to be told so.
    level = _rms(samples)
    if level < SILENCE_RMS:
        return _nothing_heard(samples, started, level)

    model = _load()
    try:
        segments, info = model.transcribe(
            samples, language=language,
            # One beam. This is transcribing a six-word question, not a
            # lecture, and beam search buys accuracy on long-range structure
            # there is none of here - at several times the latency, on the
            # one path where a reader is watching a spinner.
            beam_size=1,
            # Voice-activity detection trims the silence either side of
            # somebody reaching for the button. It is off by default because
            # it is the one part of this that needs onnxruntime, whose DLL
            # fails to initialise on the machine this was built on - and a
            # nicety that trims a little latency is not worth making a second
            # compiled dependency load-bearing. Set WHISPER_VAD=1 to use it
            # where it works.
            vad_filter=_vad_enabled())
        kept = [s for s in segments
                if getattr(s, "no_speech_prob", 0.0) < NO_SPEECH_PROB]
        text = " ".join(segment.text.strip() for segment in kept).strip()
    except VoiceUnavailable:
        raise
    except Exception as exc:
        raise VoiceUnavailable(f"that audio could not be decoded: {exc}") from exc

    return {
        "text": text,
        # False when the recording held no speech. The caller shows "I did not
        # hear anything" rather than asking an empty question, which is a
        # different thing from a question that could not be answered.
        "heard": bool(text),
        "language": getattr(info, "language", language) or "",
        "audio_seconds": round(float(getattr(info, "duration", 0.0)), 2),
        "took_seconds": round(time.time() - started, 2),
        "level": round(level, 5),
        "model": _settings()["model"],
    }


def _decode(audio: bytes):
    """The recording as 16 kHz mono float samples.

    Decoded here rather than inside `model.transcribe` so the level can be
    measured before the model runs, and so it is decoded once rather than
    twice. faster-whisper accepts the array directly.
    """
    from faster_whisper.audio import decode_audio

    return decode_audio(io.BytesIO(audio))


def _rms(samples) -> float:
    import numpy as np

    if len(samples) == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(samples, dtype="float64"))))


def _nothing_heard(samples, started: float, level: float) -> dict:
    return {
        "text": "",
        "heard": False,
        "language": "",
        "audio_seconds": round(len(samples) / 16000, 2),
        "took_seconds": round(time.time() - started, 2),
        "level": round(level, 5),
        "model": _settings()["model"],
    }


def reset() -> None:
    """Drop the loaded model and any cached failure. For tests."""
    global _model, _load_error
    with _lock:
        _model = None
        _load_error = None
