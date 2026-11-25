# Image Model Storage

## Status

**Untrained.** No trained weights are bundled with this repository. The `weights/` directory contains only a placeholder file. Until you run `ml_training.training.train_image` and produce a checkpoint, image inference must return `INCONCLUSIVE`.

## Architecture

| Item | Value |
| --- | --- |
| Backbone | `torchvision.models.resnet18` with `weights=None` |
| Head | Linear layer with two outputs |
| Classes | `real`, `fake` |
| Input tensor | `[batch, 3, 224, 224]` |
| Preprocessing | EXIF transpose, RGB conversion, resize, center crop, ImageNet normalization |
| Loss | Cross-entropy |
| Checkpoint format | PyTorch state dict bundle |

The model is intentionally initialized without pretrained weights. This avoids shipping hidden third-party weights and keeps provenance explicit. If you choose to use a pretrained backbone, record that decision in the checkpoint config and in your evaluation report.

## Expected checkpoint

```text
ml_models/image/weights/image_detector.pt
```

The checkpoint payload contains:

- `model_state_dict`
- `labels`
- `config`
- `epoch`
- `source_manifest`

Related generated files:

```text
ml_models/image/weights/labels.json
ml_models/image/weights/metrics.json
ml_models/image/weights/evaluation.json
```

Generated files are ignored by Git. Only `.gitkeep` is tracked.

## Versioning

Use a semantic version string in the checkpoint config:

- `major`: architecture or label-space change.
- `minor`: retraining with compatible preprocessing.
- `patch`: same data and architecture, different seed or epoch count.

Recommended naming when archiving a released checkpoint:

```text
image_detector_v1.0.0.pt
image_detector_v1.1.0.pt
```

The active inference filename remains `image_detector.pt` so application code does not need to change for every retrain.

## Provenance required for each checkpoint

- Manifest path and SHA-256.
- Data root path.
- Train, validation, and test counts.
- Epochs, batch size, learning rate, seed.
- Preprocessing config.
- Label mapping.
- Generated `metrics.json` and `evaluation.json`.
- Checkpoint SHA-256.

## Inference rule

If `image_detector.pt` is absent, unreadable, or lacks expected keys, inference returns:

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
python -m ml_training.training.train_image --manifest D:/manifests/images.csv --data-root D:/datasets/images
python -m ml_training.evaluation.evaluate_image --manifest D:/manifests/images.csv --data-root D:/datasets/images --split test
python -m ml_training.inference.image_infer --input D:/evidence/sample.jpg
```
