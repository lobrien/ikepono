import os
from PIL import Image
import numpy as np
from torch.utils.data import Dataset
from torchvision import transforms
from collections import defaultdict
from sklearn.model_selection import train_test_split
import torch

from ikepono.labeledimageembedding import LabeledImageTensor


class SplittableImageDataset(Dataset):
    @classmethod
    def from_directory(cls, root_dir, transform=None, train=True, test_size=0.2, random_state=42, k=5, device = torch.device('cpu')):
        image_paths = []
        labels = []
        class_counts = defaultdict(int)

        # First pass: count images per class
        for root, _, files in os.walk(root_dir):
            for file in files:
                if file.lower().endswith(('.png', '.jpg', '.jpeg', '.tiff', '.bmp', '.gif')):
                    label = os.path.basename(os.path.dirname(os.path.join(root, file)))
                    class_counts[label] += 1

        # Second pass: keep only classes with at least k members
        for root, _, files in os.walk(root_dir):
            for file in files:
                if file.lower().endswith(('.png', '.jpg', '.jpeg', '.tiff', '.bmp', '.gif')):
                    full_path = os.path.join(root, file)
                    label = os.path.basename(os.path.dirname(full_path))

                    if class_counts[label] >= (k + k * test_size):
                        image_paths.append(full_path)
                        labels.append(label)

        return cls(image_paths, labels, transform, train, test_size, random_state, k, device)


    def __init__(self, paths, labels, transform=None, train=True, test_size=0.2, random_state=42, k=5, device = torch.device('cpu')):
        self.root_dir = None
        self.transform = transform
        self.train = train
        self.test_size = test_size
        self.random_state = random_state
        self.k = k
        self.image_paths = paths
        self.labels = labels
        self.device = device
        self.class_to_idx = {label: idx for idx, label in enumerate(np.unique(labels))}
        self.train_indices, self.test_indices = self._split_indices()


    def _split_indices(self):
        indices = np.arange(len(self.image_paths))
        labels = np.array(self.labels)
        assert indices.shape == labels.shape, "Indices and labels must have the same shape. Labels need to be repeated for each image."

        train_indices, test_indices = [], []

        for class_label in np.unique(labels):
            class_indices = indices[labels == class_label]
            n_samples = len(class_indices)

            if n_samples < self.k:  # Minimum 3 for train and 2 for test
                raise ValueError(f"Class {class_label} has fewer than 5 samples.")

            n_test = int(n_samples * self.test_size)
            n_train = n_samples - n_test

            if n_train < 3:
                n_train = 3
                n_test = n_samples - n_train

            class_train, class_test = train_test_split(
                class_indices, test_size=n_test, train_size=n_train,
                random_state=self.random_state
            )

            train_indices.extend(class_train)
            test_indices.extend(class_test)

        return train_indices, test_indices

    def __len__(self):
        if self.train:
            return len(self.train_indices)
        else:
            return len(self.test_indices)

    def __getitem__(self, idx):
        if self.train:
            idx = self.train_indices[idx]
        else:
            idx = self.test_indices[idx]

        img_path = self.image_paths[idx]
        pil_image = Image.open(img_path).convert('RGB')
        label = self.labels[idx]

        if self.transform:
            tensor_image = self.transform(pil_image)
        else:
            # Minimum xform is to tensor
            transform = transforms.Compose([transforms.ToTensor()])
            tensor_image = transform(pil_image)
        # Move it on to configuration["dataset_device"]
        tensor_image = tensor_image.to(self.device)
        return LabeledImageTensor(image=tensor_image, label=self.class_to_idx[label], source=img_path)

    @staticmethod
    def standard_transform():
        return transforms.Compose([
            transforms.Resize((224, 224)),
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
        ])
