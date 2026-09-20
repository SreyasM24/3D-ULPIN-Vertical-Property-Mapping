"""
Lightweight U-Net Architecture for Building Footprint Segmentation.
Designed for rapid, deterministic local execution, low parameter count,
and seamless ONNX export.
"""

import torch
import torch.nn as nn
import torch.nn.functional as F


class DoubleConv(nn.Module):
    """(Conv2D -> BatchNorm -> ReLU) * 2"""

    def __init__(self, in_channels: int, out_channels: int):
        super().__init__()
        self.double_conv = nn.Sequential(
            nn.Conv2d(in_channels, out_channels, kernel_size=3, padding=1, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True),
            nn.Conv2d(out_channels, out_channels, kernel_size=3, padding=1, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.double_conv(x)


class Down(nn.Module):
    """Downscaling with MaxPool2D then DoubleConv"""

    def __init__(self, in_channels: int, out_channels: int):
        super().__init__()
        self.maxpool_conv = nn.Sequential(
            nn.MaxPool2d(2),
            DoubleConv(in_channels, out_channels)
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.maxpool_conv(x)


class Up(nn.Module):
    """Upscaling with Bilinear Interpolation or ConvTranspose2d then DoubleConv"""

    def __init__(self, in_channels: int, out_channels: int, bilinear: bool = True):
        super().__init__()
        if bilinear:
            self.up = nn.Upsample(scale_factor=2, mode='bilinear', align_corners=True)
            self.conv = DoubleConv(in_channels, out_channels)
        else:
            self.up = nn.ConvTranspose2d(in_channels // 2, in_channels // 2, kernel_size=2, stride=2)
            self.conv = DoubleConv(in_channels, out_channels)
        self.bilinear = bilinear

    def forward(self, x1: torch.Tensor, x2: torch.Tensor) -> torch.Tensor:
        x1 = self.up(x1)
        x = torch.cat([x2, x1], dim=1)
        return self.conv(x)


class LightweightUNet(nn.Module):
    """
    Compact U-Net segmentation model:
    Input: [B, 3, H, W]
    Output: [B, 1, H, W] (raw logits)
    """

    def __init__(self, n_channels: int = 3, n_classes: int = 1, base_filters: int = 16, bilinear: bool = True):
        super().__init__()
        self.n_channels = n_channels
        self.n_classes = n_classes
        self.bilinear = bilinear

        f = base_filters  # e.g. 16
        self.inc = DoubleConv(n_channels, f)          # 3 -> 16
        self.down1 = Down(f, f * 2)                  # 16 -> 32
        self.down2 = Down(f * 2, f * 4)              # 32 -> 64
        self.down3 = Down(f * 4, f * 8)              # 64 -> 128 (bottleneck)
        self.up1 = Up(f * 8 + f * 4, f * 4, bilinear) # (128+64)->64
        self.up2 = Up(f * 4 + f * 2, f * 2, bilinear) # (64+32)->32
        self.up3 = Up(f * 2 + f, f, bilinear)         # (32+16)->16
        self.outc = nn.Conv2d(f, n_classes, kernel_size=1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x1 = self.inc(x)
        x2 = self.down1(x1)
        x3 = self.down2(x2)
        x4 = self.down3(x3)
        x = self.up1(x4, x3)
        x = self.up2(x, x2)
        x = self.up3(x, x1)
        logits = self.outc(x)
        return logits

    def predict_mask(self, x: torch.Tensor, threshold: float = 0.5) -> torch.Tensor:
        """Helper for probability prediction and thresholding."""
        logits = self.forward(x)
        probs = torch.sigmoid(logits)
        return (probs > threshold).float()
