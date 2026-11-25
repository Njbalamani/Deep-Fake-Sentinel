import os
import wave

import numpy as np
from django.conf import settings

from .inference import MODEL_VERSION, predict_audio
from .models import AudioAnalysis

HEURISTIC_NOTE = "Heuristic evidence only; not authenticity proof."
FRAME_SIZE = 1024
HOP_SIZE = 512
MAX_FRAMES = 900


def _media_path(media):
    field = getattr(media, "file", None)
    if not field:
        return None
    try:
        path = field.path
    except (ValueError, OSError, NotImplementedError):
        return None
    if not path or not os.path.isfile(path):
        return None
    return path


def _indicator(code, severity, detail, value=None, kind="heuristic"):
    return {
        "code": code,
        "kind": kind,
        "severity": severity,
        "detail": detail,
        "value": value,
        "note": HEURISTIC_NOTE if kind == "heuristic" else "Derived from the configured model checkpoint.",
    }


def _load_with_wave(path):
    with wave.open(path, "rb") as handle:
        sample_rate = handle.getframerate()
        channels = handle.getnchannels()
        width = handle.getsampwidth()
        frames = handle.readframes(handle.getnframes())
    if width == 1:
        samples = np.frombuffer(frames, dtype=np.uint8).astype(np.float32) - 128.0
    elif width == 2:
        samples = np.frombuffer(frames, dtype="<i2").astype(np.float32)
    elif width == 4:
        samples = np.frombuffer(frames, dtype="<i4").astype(np.float32)
    else:
        raise ValueError("Unsupported PCM sample width")
    samples = samples / max(1.0, float(np.max(np.abs(samples))))
    if channels > 1:
        samples = samples.reshape(-1, channels).mean(axis=1)
    return samples.astype(np.float32), sample_rate, "wave_numpy"


def _load_audio(path):
    try:
        import librosa

        samples, sample_rate = librosa.load(path, sr=None, mono=True)
        return np.asarray(samples, dtype=np.float32), int(sample_rate), "librosa"
    except Exception:
        pass
    try:
        import soundfile

        samples, sample_rate = soundfile.read(path, dtype="float32", always_2d=False)
        if samples.ndim > 1:
            samples = samples.mean(axis=1)
        return np.asarray(samples, dtype=np.float32), int(sample_rate), "soundfile"
    except Exception:
        pass
    try:
        return _load_with_wave(path)
    except Exception:
        return None


def _framed(samples):
    if samples.size < FRAME_SIZE:
        padded = np.pad(samples, (0, FRAME_SIZE - samples.size))
    else:
        padded = samples
    count = min(MAX_FRAMES, 1 + (padded.size - FRAME_SIZE) // HOP_SIZE)
    return np.stack([padded[offset * HOP_SIZE : offset * HOP_SIZE + FRAME_SIZE] for offset in range(max(1, count))])


def _numpy_spectral_features(samples, sample_rate):
    frames = _framed(samples)
    window = np.hanning(FRAME_SIZE).astype(np.float32)
    spectrum = np.abs(np.fft.rfft(frames * window, axis=1))
    power = spectrum**2
    frequencies = np.fft.rfftfreq(FRAME_SIZE, 1.0 / max(1, sample_rate))
    centroid = float(np.mean(np.sum(frequencies[None, :] * power, axis=1) / np.maximum(np.sum(power, axis=1), 1e-10)))
    flatness = float(
        np.mean(np.exp(np.mean(np.log(power + 1e-10), axis=1)) / np.maximum(np.mean(power, axis=1), 1e-10))
    )
    log_power = np.log(power + 1e-10)
    bins = log_power.shape[1]
    coefficients = np.arange(13)[:, None]
    positions = np.arange(bins)[None, :]
    dct_matrix = np.cos(np.pi * coefficients * (positions + 0.5) / bins)
    mfcc = log_power @ dct_matrix.T
    return centroid, flatness, mfcc


def _compute_features(samples, sample_rate, backend):
    duration = float(samples.size / sample_rate) if sample_rate > 0 else 0.0
    rms = float(np.sqrt(np.mean(samples**2))) if samples.size else 0.0
    zero_crossing = float(np.mean(np.abs(np.diff(np.sign(samples)))) / 2.0) if samples.size > 1 else 0.0
    if backend == "librosa":
        import librosa

        mfcc = np.asarray(librosa.feature.mfcc(y=samples, sr=sample_rate, n_mfcc=13))
        centroid = float(np.mean(librosa.feature.spectral_centroid(y=samples, sr=sample_rate)))
        flatness = float(np.mean(librosa.feature.spectral_flatness(y=samples)))
    else:
        centroid, flatness, mfcc = _numpy_spectral_features(samples, sample_rate)
    return {
        "duration_seconds": duration,
        "sample_rate": int(sample_rate),
        "rms": rms,
        "zero_crossing_rate_mean": zero_crossing,
        "spectral_centroid_mean": centroid,
        "spectral_flatness_mean": flatness,
        "mfcc_mean": [float(value) for value in np.mean(mfcc, axis=1)[:13]],
        "mfcc_std": [float(value) for value in np.std(mfcc, axis=1)[:13]],
        "feature_backend": backend,
    }


def _suspicious_segments(samples, sample_rate):
    if sample_rate <= 0 or samples.size == 0:
        return []
    window_size = max(1, int(sample_rate))
    energies = []
    for start in range(0, samples.size, window_size):
        window = samples[start : start + window_size]
        energies.append(float(np.sqrt(np.mean(window**2))) if window.size else 0.0)
    if len(energies) < 3:
        return []
    median = float(np.median(energies))
    deviation = float(np.median(np.abs(np.asarray(energies) - median))) or 1e-9
    segments = []
    for index, energy in enumerate(energies):
        if abs(energy - median) > 2.5 * 1.4826 * deviation:
            segments.append(
                {
                    "start_seconds": round(index * window_size / sample_rate, 3),
                    "end_seconds": round(min((index + 1) * window_size, samples.size) / sample_rate, 3),
                    "rms": energy,
                    "reason": "deterministic_energy_outlier",
                    "basis": "heuristic",
                    "note": HEURISTIC_NOTE,
                }
            )
        if len(segments) >= 50:
            break
    return segments


def _analysis_dir():
    root = os.path.join(str(getattr(settings, "MEDIA_ROOT", "")), "analysis", "audio")
    os.makedirs(root, exist_ok=True)
    return root


def _relative_path(path):
    root = str(getattr(settings, "MEDIA_ROOT", ""))
    try:
        return os.path.relpath(path, root).replace("\\", "/")
    except ValueError:
        return os.path.basename(path)


def _save_waveform(samples, target):
    from PIL import Image, ImageDraw

    width, height = 800, 300
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    draw.line((0, height // 2, width, height // 2), fill=(190, 190, 190))
    if samples.size:
        buckets = np.array_split(np.abs(samples), min(width, samples.size))
        envelope = [float(np.max(bucket)) for bucket in buckets]
        peak = max(envelope) or 1.0
        for index, amplitude in enumerate(envelope):
            extent = int((amplitude / peak) * (height // 2 - 10))
            draw.line((index, height // 2 - extent, index, height // 2 + extent), fill=(40, 90, 160))
    image.save(target, format="PNG")


def _save_spectrogram(samples, sample_rate, target):
    from PIL import Image

    frames = _framed(samples)
    window = np.hanning(FRAME_SIZE).astype(np.float32)
    spectrum = np.abs(np.fft.rfft(frames * window, axis=1))
    magnitudes = np.log(spectrum + 1e-6)
    minimum = float(np.min(magnitudes))
    maximum = float(np.max(magnitudes))
    scaled = (magnitudes - minimum) / max(1e-9, maximum - minimum)
    array = np.flipud((scaled * 255).astype(np.uint8))
    image = Image.fromarray(array, mode="L").convert("RGB").resize((800, 300))
    image.save(target, format="PNG")


def analyze_audio(media):
    path = _media_path(media)
    features = {}
    suspicious_segments = []
    indicators = []
    prediction = None
    waveform_path = ""
    spectrogram_path = ""
    backend = "unavailable"
    samples = np.array([], dtype=np.float32)
    sample_rate = 0

    if path is None:
        indicators.append(
            _indicator(
                "media_unavailable", "INFO", "The stored audio file is not readable at its current path.", kind="model"
            )
        )
    else:
        loaded = _load_audio(path)
        if loaded is None:
            indicators.append(
                _indicator(
                    "audio_decode_failed", "INFO", "No available audio backend could decode this file.", kind="model"
                )
            )
        else:
            samples, sample_rate, backend = loaded
            features = _compute_features(samples, sample_rate, backend)
            suspicious_segments = _suspicious_segments(samples, sample_rate)
            try:
                directory = _analysis_dir()
                stem = str(media.pk).replace("-", "")
                waveform = os.path.join(directory, "%s_waveform.png" % stem)
                spectrogram = os.path.join(directory, "%s_spectrogram.png" % stem)
                _save_waveform(samples, waveform)
                _save_spectrogram(samples, sample_rate, spectrogram)
                waveform_path = _relative_path(waveform)
                spectrogram_path = _relative_path(spectrogram)
            except Exception as exc:
                indicators.append(
                    _indicator(
                        "visualization_unavailable", "INFO", "Waveform or spectrogram could not be written: %s" % exc
                    )
                )
            indicators.extend(
                [
                    _indicator("audio_backend", "INFO", "Backend used to decode and extract audio features.", backend),
                    _indicator(
                        "suspicious_segments",
                        "LOW" if suspicious_segments else "INFO",
                        "Energy outliers measured deterministically; not evidence of manipulation.",
                        len(suspicious_segments),
                    ),
                    _indicator(
                        "mfcc_features",
                        "INFO",
                        "MFCC statistics extracted from the audio signal.",
                        {
                            "mfcc_mean": features["mfcc_mean"],
                            "mfcc_std": features["mfcc_std"],
                        },
                    ),
                ]
            )
            prediction = predict_audio(path)
            if prediction is not None and not prediction.get("checkpoint_id"):
                prediction = None

    checkpoint_name = ""
    checkpoint_path = ""
    checkpoint_id = ""
    checkpoint_sha256 = ""
    preprocessing_config = {}
    if prediction is None:
        model_status = (
            "UNTRAINED" if path is not None and features else ("UNAVAILABLE" if path is None else "UNTRAINED")
        )
        verdict = "INCONCLUSIVE"
        confidence = None
        model_version = "untrained"
        indicators.append(
            _indicator(
                "model_unavailable",
                "INFO",
                "No trained audio checkpoint was applied; no prediction was produced.",
                kind="model",
            )
        )
    else:
        model_status = "TRAINED"
        verdict = prediction["verdict"]
        confidence = prediction["confidence"]
        model_version = prediction.get("model_version", MODEL_VERSION)
        checkpoint_name = prediction.get("checkpoint", "")
        checkpoint_path = prediction.get("checkpoint_path", "")
        checkpoint_id = prediction.get("checkpoint_id", "")
        checkpoint_sha256 = prediction.get("checkpoint_sha256", "")
        preprocessing_config = prediction.get("preprocessing_config", {})
        indicators.append(
            _indicator(
                "model_prediction",
                "INFO",
                "Prediction produced by the configured audio checkpoint.",
                prediction["verdict"],
                kind="model",
            )
        )
        indicators.append(
            _indicator(
                "checkpoint_id",
                "INFO",
                "Stable identifier of the applied audio checkpoint.",
                checkpoint_id,
                kind="model",
            )
        )

    record, _ = AudioAnalysis.objects.update_or_create(
        media=media,
        defaults={
            "model_version": model_version,
            "model_status": model_status,
            "verdict": verdict,
            "confidence": confidence,
            "checkpoint_name": checkpoint_name,
            "checkpoint_path": checkpoint_path,
            "checkpoint_id": checkpoint_id,
            "checkpoint_sha256": checkpoint_sha256,
            "preprocessing_config": preprocessing_config,
            "duration_seconds": float(features.get("duration_seconds", 0.0)),
            "sample_rate": int(features.get("sample_rate", 0)),
            "waveform_path": waveform_path,
            "spectrogram_path": spectrogram_path,
            "features": features,
            "suspicious_segments": suspicious_segments,
            "indicators": indicators,
        },
    )
    return record
