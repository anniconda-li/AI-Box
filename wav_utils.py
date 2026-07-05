import math
import sys
import wave
from array import array
from pathlib import Path


WAV_SAMPLE_RATE = 16000
WAV_SAMPLE_WIDTH = 2
WAV_CHANNELS = 1


class WavFormatError(ValueError):
    pass


def validate_device_wav(path: Path) -> dict[str, int | float]:
    try:
        with wave.open(str(path), "rb") as wav_file:
            channels = wav_file.getnchannels()
            sample_width = wav_file.getsampwidth()
            frame_rate = wav_file.getframerate()
            frame_count = wav_file.getnframes()
            compression = wav_file.getcomptype()
    except (EOFError, wave.Error) as exc:
        raise WavFormatError(f"invalid WAV file: {exc}") from exc

    if compression != "NONE":
        raise WavFormatError("WAV must use PCM encoding")
    if channels != WAV_CHANNELS:
        raise WavFormatError("WAV must be mono")
    if sample_width != WAV_SAMPLE_WIDTH:
        raise WavFormatError("WAV must be 16-bit")
    if frame_rate != WAV_SAMPLE_RATE:
        raise WavFormatError("WAV sample rate must be 16000 Hz")

    return {
        "channels": channels,
        "sample_width": sample_width,
        "sample_rate": frame_rate,
        "frames": frame_count,
        "duration_seconds": frame_count / frame_rate if frame_rate else 0.0,
    }


def wav_rms(path: Path) -> float:
    with wave.open(str(path), "rb") as wav_file:
        frames = wav_file.readframes(wav_file.getnframes())

    if not frames:
        return 0.0

    samples = array("h")
    samples.frombytes(frames)
    if sys.byteorder != "little":
        samples.byteswap()
    if not samples:
        return 0.0

    square_sum = sum(sample * sample for sample in samples)
    return math.sqrt(square_sum / len(samples))


def looks_like_silence(path: Path, rms_threshold: float = 80.0) -> bool:
    return wav_rms(path) < rms_threshold


def write_silence_wav(path: Path, duration_seconds: float = 0.4) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame_count = max(1, int(WAV_SAMPLE_RATE * duration_seconds))
    silence = b"\x00\x00" * frame_count
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(WAV_CHANNELS)
        wav_file.setsampwidth(WAV_SAMPLE_WIDTH)
        wav_file.setframerate(WAV_SAMPLE_RATE)
        wav_file.writeframes(silence)
