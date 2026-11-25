# Static Model Assets

Trained model weights do **not** live in this directory. All checkpoints, label maps, and generated metrics belong under `ml_models/<modality>/weights/`.

This folder is reserved for optional browser-side assets only, such as a small WebAssembly runtime, a browser-friendly label map, or a demo thumbnail that is explicitly marked illustrative. Do not place `.pt`, `.pth`, `.ckpt`, or large binary model files here.

No browser asset is required to run DEEPFAKE SENTINEL. Inference is performed by backend training and inference tools reading local checkpoints.

See:

- `ml_models/image/README.md`
- `ml_models/video/README.md`
- `ml_models/audio/README.md`
- `docs/model-evaluation.md`
