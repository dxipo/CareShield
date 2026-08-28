from __future__ import annotations

import torch
from torch import nn

from app.fall_detection.stgcn_extend.graph import CocoGraph


class UnitTCN(nn.Module):
    def __init__(
        self,
        in_channels: int,
        out_channels: int,
        kernel_size: int = 9,
        stride: int = 1,
        dilation: int = 1,
        dropout: float = 0,
    ) -> None:
        super().__init__()
        padding = (kernel_size + (kernel_size - 1) * (dilation - 1) - 1) // 2
        self.conv = nn.Conv2d(
            in_channels,
            out_channels,
            kernel_size=(kernel_size, 1),
            padding=(padding, 0),
            stride=(stride, 1),
            dilation=(dilation, 1),
        )
        self.bn = nn.BatchNorm2d(out_channels)
        self.drop = nn.Dropout(dropout, inplace=True)

    def forward(self, value: torch.Tensor) -> torch.Tensor:
        return self.drop(self.bn(self.conv(value)))


class MultiScaleTCN(nn.Module):
    def __init__(self, in_channels: int, out_channels: int, stride: int = 1) -> None:
        super().__init__()
        configurations: tuple[tuple[int | str, int] | str, ...] = (
            (3, 1), (3, 2), (3, 3), (3, 4), ("max", 3), "1x1",
        )
        branch_count = len(configurations)
        mid_channels = out_channels // branch_count
        first_channels = out_channels - mid_channels * (branch_count - 1)
        activation = nn.ReLU()
        branches: list[nn.Module] = []
        for index, configuration in enumerate(configurations):
            channels = first_channels if index == 0 else mid_channels
            if configuration == "1x1":
                branches.append(
                    nn.Conv2d(in_channels, channels, kernel_size=1, stride=(stride, 1))
                )
                continue
            kernel, dilation = configuration
            if kernel == "max":
                branches.append(
                    nn.Sequential(
                        nn.Conv2d(in_channels, channels, kernel_size=1),
                        nn.BatchNorm2d(channels),
                        activation,
                        nn.MaxPool2d(
                            kernel_size=(dilation, 1),
                            stride=(stride, 1),
                            padding=(1, 0),
                        ),
                    )
                )
            else:
                branches.append(
                    nn.Sequential(
                        nn.Conv2d(in_channels, channels, kernel_size=1),
                        nn.BatchNorm2d(channels),
                        activation,
                        UnitTCN(
                            channels,
                            channels,
                            kernel_size=int(kernel),
                            stride=stride,
                            dilation=int(dilation),
                        ),
                    )
                )
        self.branches = nn.ModuleList(branches)
        self.transform = nn.Sequential(
            nn.BatchNorm2d(out_channels),
            activation,
            nn.Conv2d(out_channels, out_channels, kernel_size=1),
        )
        self.bn = nn.BatchNorm2d(out_channels)
        self.drop = nn.Dropout(0, inplace=True)

    def forward(self, value: torch.Tensor) -> torch.Tensor:
        merged = torch.cat([branch(value) for branch in self.branches], dim=1)
        return self.drop(self.bn(self.transform(merged)))


class UnitGCN(nn.Module):
    def __init__(
        self,
        in_channels: int,
        out_channels: int,
        adjacency: torch.Tensor,
        *,
        adaptive: str = "init",
        with_res: bool = True,
    ) -> None:
        super().__init__()
        self.num_subsets = adjacency.size(0)
        self.adaptive = adaptive
        self.A = nn.Parameter(adjacency.clone())
        self.bn = nn.BatchNorm2d(out_channels)
        self.act = nn.ReLU(inplace=True)
        self.conv = nn.Conv2d(in_channels, out_channels * self.num_subsets, 1)
        if with_res and in_channels != out_channels:
            self.down: nn.Module | None = nn.Sequential(
                nn.Conv2d(in_channels, out_channels, 1),
                nn.BatchNorm2d(out_channels),
            )
        elif with_res:
            self.down = nn.Identity()
        else:
            self.down = None

    def forward(self, value: torch.Tensor) -> torch.Tensor:
        batch, _, time, vertices = value.shape
        residual: torch.Tensor | int = self.down(value) if self.down is not None else 0
        projected = self.conv(value).view(
            batch,
            self.num_subsets,
            -1,
            time,
            vertices,
        )
        projected = torch.einsum("nkctv,kvw->nctw", projected, self.A).contiguous()
        return self.act(self.bn(projected) + residual)


class STGCNBlock(nn.Module):
    def __init__(
        self,
        in_channels: int,
        out_channels: int,
        adjacency: torch.Tensor,
        *,
        stride: int = 1,
        residual: bool = True,
    ) -> None:
        super().__init__()
        self.gcn = UnitGCN(
            in_channels,
            out_channels,
            adjacency,
            adaptive="init",
            with_res=True,
        )
        self.tcn = MultiScaleTCN(out_channels, out_channels, stride=stride)
        self.relu = nn.ReLU()
        if not residual:
            self.residual: nn.Module | None = None
        elif in_channels == out_channels and stride == 1:
            self.residual = nn.Identity()
        else:
            self.residual = UnitTCN(
                in_channels,
                out_channels,
                kernel_size=1,
                stride=stride,
            )

    def forward(self, value: torch.Tensor) -> torch.Tensor:
        residual: torch.Tensor | int = (
            self.residual(value) if self.residual is not None else 0
        )
        return self.relu(self.tcn(self.gcn(value)) + residual)


class STGCNBackbone(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        adjacency = torch.tensor(CocoGraph().A, dtype=torch.float32)
        self.data_bn = nn.BatchNorm1d(2 * 17)
        stage_channels = (64, 64, 128, 128, 256, 256)
        modules: list[nn.Module] = []
        in_channels = 2
        for index, out_channels in enumerate(stage_channels, start=1):
            modules.append(
                STGCNBlock(
                    in_channels,
                    out_channels,
                    adjacency.clone(),
                    stride=2 if index in (3, 5) else 1,
                    residual=index != 1,
                )
            )
            in_channels = out_channels
        self.gcn = nn.ModuleList(modules)

    def forward(self, value: torch.Tensor) -> torch.Tensor:
        if value.dim() == 4:
            value = value.unsqueeze(1)
        batch, persons, time, vertices, channels = value.size()
        normalized = value.permute(0, 1, 3, 4, 2).contiguous()
        normalized = self.data_bn(normalized.view(batch * persons, vertices * channels, time))
        normalized = (
            normalized.view(batch, persons, vertices, channels, time)
            .permute(0, 1, 3, 4, 2)
            .contiguous()
            .view(batch * persons, channels, time, vertices)
        )
        for block in self.gcn:
            normalized = block(normalized)
        return normalized.reshape((batch, persons) + normalized.shape[1:])


class DecoderLayer(nn.Module):
    def __init__(self, in_channels: int, out_channels: int) -> None:
        super().__init__()
        self.block = nn.Sequential(
            nn.Conv2d(in_channels, out_channels, kernel_size=3, padding=1),
            nn.BatchNorm2d(out_channels),
            nn.Dropout(0, inplace=True),
        )

    def forward(self, value: torch.Tensor) -> torch.Tensor:
        return self.block(value)


class PredictionDecoder(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.txcnns = nn.ModuleList(
            [DecoderLayer(10, 25)] + [DecoderLayer(25, 25) for _ in range(3)]
        )
        self.gcn = nn.Conv2d(256, 2, 1)
        self.prelus = nn.ModuleList([nn.PReLU() for _ in range(4)])

    def forward(self, value: torch.Tensor) -> torch.Tensor:
        value = self.gcn(value).permute(0, 2, 1, 3)
        value = self.prelus[0](self.txcnns[0](value))
        for index in range(1, len(self.txcnns)):
            value = self.prelus[index](self.txcnns[index](value)) + value
        return value


class ClassifierHead(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.classifier = nn.Sequential(nn.Linear(256, 2))

    def forward(self, value: torch.Tensor) -> torch.Tensor:
        return self.classifier(value)


class STGCNExtend(nn.Module):
    """Production form of the paper model, preserving checkpoint key names."""

    def __init__(self) -> None:
        super().__init__()
        self.backbone = STGCNBackbone()
        self.pred_decoder = PredictionDecoder()
        self.classifier = ClassifierHead()
        self.pool = nn.AdaptiveAvgPool2d(1)

    def forward(self, value: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        if value.shape != (value.shape[0], 1, 100, 17, 2):
            raise ValueError("STGCN-Extend expects [N,1,100,17,2]")
        batch, persons = value.shape[:2]
        encoded = self.backbone(value[:, :, -65:-25, :, :]).squeeze(1)
        predicted = self.pred_decoder(encoded).permute(0, 1, 3, 2)
        observed = value[:, 0, :-25, :, :]
        recognition_input = torch.cat((observed, predicted), dim=1)
        features = self.backbone(recognition_input)
        logits = self.classifier(self.pool(features).reshape(batch * persons, -1))
        return predicted, logits
