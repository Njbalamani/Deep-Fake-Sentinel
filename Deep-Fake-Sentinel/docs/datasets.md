# Dataset Guidance for DEEPFAKE SENTINEL

## Golden rule

**Do not auto-download large datasets.** DEEPFAKE SENTINEL training tools only read local CSV manifests. No script in this repository downloads a dataset, fetches model weights, or creates a synthetic dataset on your behalf. Acquire data manually through official channels, record the license and access date, and keep the data outside version control.

## Why manifests only

Manifests make data usage explicit and auditable. A manifest is a CSV with exactly these columns:

```text
path,label,split
real/0001.jpg,real,train
fake/0001.jpg,fake,train
real/0002.jpg,real,val
```

- `path` is relative to the `--data-root` passed to training, evaluation, or inference tooling.
- `label` is normally `real` or `fake`. Training scripts map common synonyms such as `0`, `1`, `authentic`, and `manipulated`.
- `split` is one of `train`, `val`, or `test`.
- Each row must point to a file that already exists locally.

The manifest builders scan local folders only. They never contact a network.

## Supported datasets

| Dataset | Modality | Typical use | Access and licensing caution |
| --- | --- | --- | --- |
| FaceForensics++ | Image and video | Face manipulation detection research. | Obtain from the official source. Review the dataset's research-use terms, sequence-level licenses, and any restrictions on redistribution or commercial use before training. |
| Celeb-DF | Video | Deepfake video detection and cross-dataset testing. | Subject to publisher terms. Confirm permission for your intended use, especially commercial deployment or public benchmark publication. |
| DFDC | Video | Large-scale deepfake detection benchmark. | Access is typically controlled by an agreement. Follow that agreement, protect participant privacy, and do not redistribute data outside allowed channels. |
| ASVspoof | Audio | Spoofed speech and replay detection. | Challenge editions have distinct rules and evaluation protocols. Record which edition you used and obey its redistribution restrictions. |

This list is informational. It is not legal advice. The repository does not verify that you have permission to use a dataset.

## Recommended record for each dataset

Keep a local, private record next to your dataset, outside Git:

```text
Dataset name: FaceForensics++
Source: official project page
Access date: YYYY-MM-DD
License or agreement version: as provided by source
Allowed use: research / internal evaluation / other
Redistribution permitted: no
Manifests generated: images.csv, videos.csv
Notes: compression level, frame extraction settings, language, subject scope
```

Never commit this record if it contains credentials, agreement identifiers, or personal data.

## Local folder layout examples

### Images

```text
D:/datasets/images/
├── train/
│   ├── real/
│   └── fake/
├── val/
│   ├── real/
│   └── fake/
└── test/
    ├── real/
    └── fake/
```

Alternative class-first layout:

```text
D:/datasets/images/
├── real/
└── fake/
```

With the class-first layout, the manifest builder uses a deterministic hash split unless `--split-mode dir` finds explicit split directories.

### Videos

```text
D:/datasets/videos/
├── train/
│   ├── real/
│   └── fake/
├── val/
│   ├── real/
│   └── fake/
└── test/
    ├── real/
    └── fake/
```

### Audio

```text
D:/datasets/audio/
├── train/
│   ├── real/
│   └── fake/
├── val/
│   ├── real/
│   └── fake/
└── test/
    ├── real/
    └── fake/
```

## Building manifests

From the repository root:

```bash
python -m ml_training.datasets.prepare_image_manifest --dataset-root D:/datasets/images --output D:/manifests/images.csv --split-mode dir
python -m ml_training.datasets.prepare_video_manifest --dataset-root D:/datasets/videos --output D:/manifests/videos.csv --split-mode dir
python -m ml_training.datasets.prepare_audio_manifest --dataset-root D:/datasets/audio --output D:/manifests/audio.csv --split-mode dir
```

If no split directories exist:

```bash
python -m ml_training.datasets.prepare_image_manifest --dataset-root D:/datasets/images --output D:/manifests/images.csv --split-mode hash --train-frac 0.7 --val-frac 0.15
```

Hash splitting is deterministic: the same file path always lands in the same split for the same seed. It reduces accidental reshuffling but is not a substitute for subject-level separation.

## Split discipline

- Keep `test` completely untouched during training and threshold tuning.
- Use `val` for early stopping, checkpoint selection, and threshold choice.
- Avoid subject overlap between train and test where identities are involved.
- For video, avoid clips from the same source video in different splits.
- For audio, avoid recordings from the same speaker and session in different splits.
- Record which manifest hash was used for each training run.

## Privacy and ethical cautions

- Synthetic-media datasets can contain faces and voices of real people.
- Do not upload dataset samples to third-party services.
- Do not use optional LLM explanation features with dataset media unless explicitly approved.
- Redact or exclude sensitive subjects when policy requires it.
- Respect takedown requests and dataset-specific deletion obligations.

## What not to do

- Do not add a downloader script to `ml_training/`.
- Do not commit dataset archives, archives of frames, or extracted audio.
- Do not copy dataset files into `static/`.
- Do not cite a paper's reported accuracy as this project's measured accuracy.
- Do not train on a dataset whose license forbids your intended use.

## Related documents

- [Model evaluation](model-evaluation.md)
- [Architecture](architecture.md)
- [Training workflow in README](../README.md#13-training-and-evaluation-workflow)
