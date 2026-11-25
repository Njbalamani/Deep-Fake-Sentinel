# Audio Model Storage

## Status

**Untrained.** No trained weights are bundled with this repository. The `weights/` directory contains only a placeholder file. Until you run `ml_training.training.train_audio` and produce a checkpoint, audio inference must return `INCONCLUSIVE`.

## Architecture

| Item | Value |
| --- | --- |
| Input | Mono waveform resampled to 16 kHz |
| Duration | 3 seconds by default, padded or truncated |
| Features | Log-mel spectrogram, 64 mel bands |
| Tensor shape | `[batch, 1, 64, 128]` |
| Classifier | Small convolutional network with adaptive pooling |
| Classes | `real`, `fake` |
| Loss | Cross-entropy |
| Checkpoint format | PyTorch state dict bundle |

Deterministic trimming and padding keep training and inference aligned. Sample rate, duration, mel bands, and frame count are stored in the checkpoint config.

## Expected checkpoint

```text
ml_models/audio/weights/audio_detector.pt
```

The checkpoint payload contains:

- `model_state_dict`
- `labels`
- `config`
- `epoch`
- `source_manifest`

Related generated files:

```text
ml_models/audio/weights/labels.json
ml_models/audio/weights/metrics.json
ml_models/audio/weights/evaluation.json
```

Generated files are ignored by Git. Only `.gitkeep` is tracked.

## Versioning

Use a semantic version string in the checkpoint config:

- `major`: architecture, feature shape, or label-space change.
- `minor`: retraining with compatible feature settings.
- `patch`: same data and architecture, different seed or epoch count.

Recommended naming when archiving a released checkpoint:

```text
audio_detector_v1.0.0.pt
audio_detector_v1.1.0.pt
```

The active inference filename remains `audio_detector.pt`.

## Provenance required for each checkpoint

- Manifest path and SHA-256.
- Data root path.
- Sample rate, duration, mel bands, and frame count.
- Train, validation, and test counts.
- Epochs, batch size, learning rate, seed.
- Language, codec, and noise notes from the dataset record.
- Label mapping.
- Generated `metrics.json` and `evaluation.json`.
- Checkpoint SHA-256.

## Inference rule

If `audio_detector.pt` is absent, unreadable, or lacks expected keys, inference returns:

```json
{
  "status": "INCONCLUSIVE",
  "verdict": null,
  "reason": "checkpoint_missing"
}
```

Never substitute a default verdict.

## Commands

```bash
python -m ml_training.training.train_audio --manifest D:/manifests/audio.csv --data-root D:/datasets/audio
python -m ml_training.evaluation.evaluate_audio --manifest D:/manifests/audio.csv --data-root D:/datasets/audio --split test
python -m ml_training.inference.audio_infer --input D:/evidence/sample.wav
```
