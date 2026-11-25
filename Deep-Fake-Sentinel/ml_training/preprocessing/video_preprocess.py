from pathlib import Path


def sample_video_indices(frame_count, num_frames):
    if frame_count <= 0 or num_frames <= 0:
        return []
    if num_frames == 1:
        return [0]
    last = frame_count - 1
    return [min(last, round(index * last / float(num_frames - 1))) for index in range(num_frames)]


def load_video_frames(path, num_frames=16, image_size=224):
    import cv2
    import torch
    from PIL import Image

    from ml_training.preprocessing.image_preprocess import preprocess_pil_image

    capture = cv2.VideoCapture(str(Path(path)))
    if not capture.isOpened():
        raise ValueError(f"Unable to open video: {path}")
    try:
        frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        indices = sample_video_indices(frame_count, num_frames)
        if not indices:
            raise ValueError(f"Video has no readable frames: {path}")
        frames = []
        read_count = 0
        last_tensor = None
        for target in indices:
            while read_count <= target:
                ok, frame = capture.read()
                if not ok:
                    break
                read_count += 1
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                last_tensor = preprocess_pil_image(Image.fromarray(rgb), image_size=image_size)
            if read_count > target and last_tensor is not None:
                frames.append(last_tensor)
            elif frames:
                frames.append(frames[-1])
            else:
                frames.append(torch.zeros((3, image_size, image_size), dtype=torch.float32))
    finally:
        capture.release()
    while len(frames) < num_frames:
        frames.append(frames[-1])
    return torch.stack(frames[:num_frames], dim=1)


def preprocess_video(path, num_frames=16, image_size=224):
    return load_video_frames(path, num_frames=num_frames, image_size=image_size)
