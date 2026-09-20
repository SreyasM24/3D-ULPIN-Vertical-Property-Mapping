"""
Reproducible Training Pipeline for Building Footprint Segmentation.
Trains LightweightUNet on SpaceNet 1 Rio dataset using disjoint tile splits.
"""

import os
import sys
sys.path.insert(0, os.path.abspath('.'))
import json
import random
import time
from datetime import datetime, timezone
import numpy as np
from PIL import Image

import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader
from app.ml.models.unet import LightweightUNet


# ---------------------------------------------------------------------------
# 1. Dataset with Deterministic Preprocessing and Augmentations
# ---------------------------------------------------------------------------

class SpaceNetSegmentationDataset(Dataset):
    def __init__(
        self,
        tile_names,
        processed_dir: str,
        target_size: tuple = (256, 256),
        is_train: bool = False
    ):
        self.tile_names = tile_names
        self.processed_dir = processed_dir
        self.img_dir = os.path.join(processed_dir, 'images')
        self.mask_dir = os.path.join(processed_dir, 'masks')
        self.target_size = target_size
        self.is_train = is_train

        # Map tile name to filenames
        all_imgs = os.listdir(self.img_dir)
        self.samples = []
        for tname in tile_names:
            matched = [f for f in all_imgs if tname in f]
            if matched:
                img_file = matched[0]
                mask_file = img_file.replace('.png', '_mask.png')
                self.samples.append((img_file, mask_file, tname))

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        img_file, mask_file, tname = self.samples[idx]
        img_path = os.path.join(self.img_dir, img_file)
        mask_path = os.path.join(self.mask_dir, mask_file)

        # 1. Load Image and Resize
        img = Image.open(img_path).convert('RGB')
        img = img.resize(self.target_size, Image.BILINEAR)
        img_arr = np.array(img, dtype=np.float32) / 255.0  # Normalize to [0, 1]

        # 2. Load Mask and Resize with NEAREST to preserve binary values
        mask = Image.open(mask_path).convert('L')
        mask = mask.resize(self.target_size, Image.NEAREST)
        mask_arr = (np.array(mask, dtype=np.float32) > 127).astype(np.float32)

        # 3. Augmentations (Train Split Only)
        if self.is_train:
            # Random horizontal flip
            if random.random() > 0.5:
                img_arr = np.fliplr(img_arr)
                mask_arr = np.fliplr(mask_arr)
            # Random vertical flip
            if random.random() > 0.5:
                img_arr = np.flipud(img_arr)
                mask_arr = np.flipud(mask_arr)
            # Random 90 deg rotation
            k = random.randint(0, 3)
            if k > 0:
                img_arr = np.rot90(img_arr, k)
                mask_arr = np.rot90(mask_arr, k)

        # Convert to Channel-First Tensors [C, H, W]
        img_tensor = torch.from_numpy(img_arr.copy().transpose(2, 0, 1))
        mask_tensor = torch.from_numpy(mask_arr.copy()).unsqueeze(0)  # [1, H, W]

        return img_tensor, mask_tensor, tname


# ---------------------------------------------------------------------------
# 2. Segmentation Loss (BCE + Soft Dice Loss)
# ---------------------------------------------------------------------------

class BCEDiceLoss(nn.Module):
    def __init__(self, bce_weight: float = 0.5, smooth: float = 1.0):
        super().__init__()
        self.bce = nn.BCEWithLogitsLoss()
        self.bce_weight = bce_weight
        self.smooth = smooth

    def forward(self, logits: torch.Tensor, targets: torch.Tensor) -> torch.Tensor:
        bce_loss = self.bce(logits, targets)
        probs = torch.sigmoid(logits)
        intersection = (probs * targets).sum(dim=(-2, -1))
        union = probs.sum(dim=(-2, -1)) + targets.sum(dim=(-2, -1))
        dice = (2.0 * intersection + self.smooth) / (union + self.smooth)
        dice_loss = (1.0 - dice).mean()
        return self.bce_weight * bce_loss + (1.0 - self.bce_weight) * dice_loss


# ---------------------------------------------------------------------------
# 3. Metrics Calculation
# ---------------------------------------------------------------------------

def calculate_metrics(logits: torch.Tensor, targets: torch.Tensor, threshold: float = 0.5):
    probs = torch.sigmoid(logits)
    preds = (probs > threshold).float()

    preds_flat = preds.view(-1)
    targets_flat = targets.view(-1)

    tp = (preds_flat * targets_flat).sum().item()
    fp = (preds_flat * (1.0 - targets_flat)).sum().item()
    fn = ((1.0 - preds_flat) * targets_flat).sum().item()
    tn = ((1.0 - preds_flat) * (1.0 - targets_flat)).sum().item()

    precision = (tp + 1e-7) / (tp + fp + 1e-7)
    recall = (tp + 1e-7) / (tp + fn + 1e-7)
    f1 = 2.0 * precision * recall / (precision + recall + 1e-7)
    iou = (tp + 1e-7) / (tp + fp + fn + 1e-7)
    pixel_acc = (tp + tn) / (tp + tn + fp + fn)

    return {
        'iou': iou,
        'dice': f1,
        'precision': precision,
        'recall': recall,
        'pixel_accuracy': pixel_acc,
        'tp': int(tp),
        'fp': int(fp),
        'fn': int(fn),
        'tn': int(tn)
    }


# ---------------------------------------------------------------------------
# 4. Main Training Pipeline
# ---------------------------------------------------------------------------

def train_model(
    data_dir: str = 'data/ml/processed/building_segmentation',
    split_path: str = 'data/ml/manifests/segmentation_split.json',
    output_dir: str = 'models/checkpoints',
    epochs: int = 35,
    batch_size: int = 4,
    lr: float = 1e-3,
    seed: int = 42,
    target_size: tuple = (256, 256)
):
    os.makedirs(output_dir, exist_ok=True)

    # Set seeds
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)

    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print(f"Training on device: {device}")

    # Load Split
    with open(split_path, 'r') as f:
        split = json.load(f)

    train_tiles = split['train']
    val_tiles = split['validation']

    print(f"Train samples: {len(train_tiles)}, Val samples: {len(val_tiles)}")

    train_ds = SpaceNetSegmentationDataset(train_tiles, data_dir, target_size=target_size, is_train=True)
    val_ds = SpaceNetSegmentationDataset(val_tiles, data_dir, target_size=target_size, is_train=False)

    train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True, drop_last=False)
    val_loader = DataLoader(val_ds, batch_size=batch_size, shuffle=False)

    # Initialize Model, Loss, Optimizer
    model = LightweightUNet(n_channels=3, n_classes=1, base_filters=16).to(device)
    criterion = BCEDiceLoss(bce_weight=0.5)
    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, mode='max', factor=0.5, patience=4)

    best_val_iou = -1.0
    best_epoch = 0
    history = []
    start_time = time.time()

    best_checkpoint_path = os.path.join(output_dir, 'best_building_unet.pt')
    final_checkpoint_path = os.path.join(output_dir, 'final_building_unet.pt')

    for epoch in range(1, epochs + 1):
        # --- Training ---
        model.train()
        train_loss = 0.0
        train_metrics_sum = {'iou': 0.0, 'dice': 0.0, 'precision': 0.0, 'recall': 0.0, 'pixel_accuracy': 0.0}

        for imgs, masks, _ in train_loader:
            imgs = imgs.to(device)
            masks = masks.to(device)

            optimizer.zero_grad()
            logits = model(imgs)
            loss = criterion(logits, masks)
            loss.backward()
            optimizer.step()

            train_loss += loss.item() * len(imgs)
            m = calculate_metrics(logits, masks)
            for k in train_metrics_sum:
                train_metrics_sum[k] += m[k] * len(imgs)

        total_train = len(train_ds)
        train_loss /= total_train
        train_metrics = {k: v / total_train for k, v in train_metrics_sum.items()}

        # --- Validation ---
        model.eval()
        val_loss = 0.0
        val_metrics_sum = {'iou': 0.0, 'dice': 0.0, 'precision': 0.0, 'recall': 0.0, 'pixel_accuracy': 0.0}

        with torch.no_grad():
            for imgs, masks, _ in val_loader:
                imgs = imgs.to(device)
                masks = masks.to(device)
                logits = model(imgs)
                loss = criterion(logits, masks)

                val_loss += loss.item() * len(imgs)
                m = calculate_metrics(logits, masks)
                for k in val_metrics_sum:
                    val_metrics_sum[k] += m[k] * len(imgs)

        total_val = len(val_ds)
        val_loss /= total_val
        val_metrics = {k: v / total_val for k, v in val_metrics_sum.items()}

        scheduler.step(val_metrics['iou'])

        is_best = val_metrics['iou'] > best_val_iou
        if is_best:
            best_val_iou = val_metrics['iou']
            best_epoch = epoch
            torch.save({
                'epoch': epoch,
                'model_state_dict': model.state_dict(),
                'optimizer_state_dict': optimizer.state_dict(),
                'val_metrics': val_metrics,
                'config': {
                    'architecture': 'LightweightUNet',
                    'base_filters': 16,
                    'input_size': target_size,
                    'seed': seed,
                    'lr': lr
                }
            }, best_checkpoint_path)

        epoch_record = {
            'epoch': epoch,
            'train_loss': round(train_loss, 4),
            'train_iou': round(train_metrics['iou'], 4),
            'train_dice': round(train_metrics['dice'], 4),
            'val_loss': round(val_loss, 4),
            'val_iou': round(val_metrics['iou'], 4),
            'val_dice': round(val_metrics['dice'], 4),
            'val_precision': round(val_metrics['precision'], 4),
            'val_recall': round(val_metrics['recall'], 4),
            'val_pixel_accuracy': round(val_metrics['pixel_accuracy'], 4),
            'lr': float(optimizer.param_groups[0]['lr']),
            'is_best': is_best
        }
        history.append(epoch_record)

        print(f"Epoch [{epoch:02d}/{epochs:02d}] "
              f"Loss: {train_loss:.4f} | Tr-IoU: {train_metrics['iou']:.3f} | "
              f"Val-Loss: {val_loss:.4f} | Val-IoU: {val_metrics['iou']:.3f} | Val-Dice: {val_metrics['dice']:.3f}"
              f"{' *BEST*' if is_best else ''}")

    total_time_s = round(time.time() - start_time, 2)

    # Save final model
    torch.save({
        'epoch': epochs,
        'model_state_dict': model.state_dict(),
        'val_metrics': val_metrics
    }, final_checkpoint_path)

    training_meta = {
        'training_completed_at': datetime.now(timezone.utc).isoformat(),
        'total_training_time_seconds': total_time_s,
        'device': str(device),
        'epochs': epochs,
        'best_epoch': best_epoch,
        'best_val_iou': round(best_val_iou, 4),
        'batch_size': batch_size,
        'initial_learning_rate': lr,
        'random_seed': seed,
        'target_resolution': list(target_size),
        'architecture': 'LightweightUNet (DoubleConv, Down, Up, 488,001 params)',
        'loss': '0.5 * BCEWithLogits + 0.5 * SoftDice',
        'history': history
    }

    with open(os.path.join(output_dir, 'training_history.json'), 'w') as f:
        json.dump(training_meta, f, indent=2)

    print(f"\n--- Training Complete in {total_time_s}s ---")
    print(f"Best Epoch: {best_epoch} with Val IoU: {best_val_iou:.4f}")
    print(f"Saved best checkpoint: {best_checkpoint_path}")
    return training_meta


if __name__ == '__main__':
    train_model()
