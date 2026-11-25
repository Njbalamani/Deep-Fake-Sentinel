# Video Model Storage

## Status

**Untrained.** No trained weights are bundled with this repository. The `weights/` directory contains only a placeholder file. Until you run `ml_training.training.train_video` and produce a checkpoint, video inference must return `INCONCLUSIVE`.

## Architecture

| Item | Value |
| --- | --- |
| Backbone | `torchvision.models.video.r3d_18` with `weights=None` |
| Head | Linear layer with two outputs |
| Classes | `real`, `fake` |
| Input tensor | `[batch, 3, frames, height, width]` |
| Default frames | 16 uniformly sampled frames |
| Default size | 224x224 |
| Preprocessing | OpenCV decode, uniform sampling, per-frame resize and normalization |
| Loss | Cross-entropy |
| Checkpoint format | PyTorch state dict bundle |

Uniform frame sampling is deterministic. If a clip has fewer frames than requested, the last decoded frame is repeated. Clip-level prediction is produced from the 3D backbone head.

## Expected checkpoint

```text
ml_models/video/weights/video_detector.pt
```

The checkpoint payload contains:

- `model_state_dict`
- `labels`
- `config`
- `epoch`
- `source_manifest`

Related generated files:

```text
ml_models/video/weights/labels.json
ml_models/video/weights/metrics.json
ml_models/video/weights/evaluation.json
```

Generated files are ignored by Git. Only `.gitkeep` is tracked.

## Versioning

Use a semantic version string in the checkpoint config:

- `major`: architecture, frame count, or label-space change.
- `minor`: retraining with compatible sampling.
- `patch`: same data and architecture, different seed or epoch count.

Recommended naming when archiving a released checkpoint:

```text
video_detector_v1.0.0.pt
video_detector_v1.1.0.pt
```

The active inference filename remains `video_detector.pt`.

## Provenance required for each checkpoint

- Manifest path and SHA-256.
- Data root path.
- Frame count and image size.
- Train, validation, and test counts.
- Epochs, batch size, learning rate, seed.
- Codec and compression notes from the dataset record.
- Label mapping.
- Generated `metrics.json` and `evaluation.json`.
- Checkpoint SHA-256.

## Inference rule

If `video_detector.pt` is absent, unreadable, or lacks expected keys, inference returns:

```json
{
  "status": "INCONCLUSIVE",
  "verdict": null,
  "reason": "checkpoint_missing"
}
```

Never substitute a default verdict.

## Resource notes

Video training is memory intensive. Reduce `--batch-size`, `--frames`, or `--image-size` if needed. Keep those values in the checkpoint config because inference must use the same settings.

## Commands

```bash
python -m ml_training.training.train_video --manifest D:/manifests/videos.csv --data-root D:/datasets/videos
python -m ml_training.evaluation.evaluate_video --manifest D:/manifests/videos.csv --data-root D:/datasets/videos --split test
python -m ml_training.inference.video_infer --input D:/evidence/sample.mp4
```
