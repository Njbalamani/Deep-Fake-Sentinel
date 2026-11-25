def build_image_model(label_count):
    import torch
    from torchvision import models

    model = models.resnet18(weights=None)
    model.fc = torch.nn.Linear(model.fc.in_features, label_count)
    return model


def build_video_model(label_count):
    import torch
    from torchvision import models

    model = models.video.r3d_18(weights=None)
    model.fc = torch.nn.Linear(model.fc.in_features, label_count)
    return model


def build_audio_model(label_count):
    import torch

    class AudioClassifier(torch.nn.Module):
        def __init__(self, num_labels):
            super().__init__()
            self.features = torch.nn.Sequential(
                torch.nn.Conv2d(1, 16, kernel_size=3, padding=1),
                torch.nn.ReLU(),
                torch.nn.MaxPool2d(2),
                torch.nn.Conv2d(16, 32, kernel_size=3, padding=1),
                torch.nn.ReLU(),
                torch.nn.MaxPool2d(2),
                torch.nn.Conv2d(32, 64, kernel_size=3, padding=1),
                torch.nn.ReLU(),
                torch.nn.AdaptiveAvgPool2d((1, 1)),
            )
            self.classifier = torch.nn.Linear(64, num_labels)

        def forward(self, inputs):
            features = self.features(inputs)
            flattened = torch.flatten(features, 1)
            return self.classifier(flattened)

    return AudioClassifier(label_count)
