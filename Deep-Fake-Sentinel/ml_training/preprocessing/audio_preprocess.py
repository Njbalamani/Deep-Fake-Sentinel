from pathlib import Path


def preprocess_audio(path, sample_rate=16000, duration_seconds=3.0, n_mels=64, max_frames=128):
    import librosa
    import numpy as np
    import torch

    waveform, _ = librosa.load(str(Path(path)), sr=sample_rate, mono=True)
    target_length = int(sample_rate * duration_seconds)
    if len(waveform) < target_length:
        waveform = np.pad(waveform, (0, target_length - len(waveform)))
    else:
        waveform = waveform[:target_length]
    mel = librosa.feature.melspectrogram(y=waveform, sr=sample_rate, n_mels=n_mels)
    log_mel = librosa.power_to_db(mel, ref=np.max)
    if log_mel.shape[1] < max_frames:
        log_mel = np.pad(log_mel, ((0, 0), (0, max_frames - log_mel.shape[1])), mode="constant")
    else:
        log_mel = log_mel[:, :max_frames]
    mean = float(log_mel.mean())
    std = float(log_mel.std())
    if std < 1e-6:
        std = 1.0
    log_mel = (log_mel - mean) / std
    return torch.from_numpy(log_mel).float().unsqueeze(0)
