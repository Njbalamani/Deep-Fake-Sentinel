from pathlib import Path

MEAN = (0.485, 0.456, 0.406)
STD = (0.229, 0.224, 0.225)


def preprocess_pil_image(image, image_size=224, mean=MEAN, std=STD):
    import torch
    from PIL import ImageOps
    from torchvision.transforms import functional as image_transforms

    image = ImageOps.exif_transpose(image).convert("RGB")
    image = image_transforms.resize(image, image_size)
    image = image_transforms.center_crop(image, image_size)
    tensor = image_transforms.to_tensor(image)
    mean_tensor = torch.tensor(mean, dtype=torch.float32).view(3, 1, 1)
    std_tensor = torch.tensor(std, dtype=torch.float32).view(3, 1, 1)
    return (tensor - mean_tensor) / std_tensor


def load_image(path, image_size=224):
    from PIL import Image

    with Image.open(Path(path)) as image:
        return preprocess_pil_image(image, image_size=image_size)


def preprocess_image(path, image_size=224):
    return load_image(path, image_size=image_size)
