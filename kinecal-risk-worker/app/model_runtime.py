"""Inference-only ST-GCN++ architecture matching the KINECAL checkpoint."""

from __future__ import annotations

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F


def _normalize_digraph(matrix: np.ndarray) -> np.ndarray:
    degree = np.sum(matrix, axis=0)
    inverse = np.zeros_like(matrix)
    for index, value in enumerate(degree):
        if value > 0:
            inverse[index, index] = value ** -1
    return matrix @ inverse


def _edge_matrix(edges: list[tuple[int, int]], nodes: int) -> np.ndarray:
    matrix = np.zeros((nodes, nodes), dtype=np.float32)
    for source, target in edges:
        matrix[target, source] = 1
    return matrix


def graph_h36m17() -> np.ndarray:
    inward = [
        (1, 0), (2, 1), (3, 2), (4, 0), (5, 4), (6, 5),
        (7, 0), (8, 7), (9, 8), (10, 9), (11, 8), (12, 11),
        (13, 12), (14, 8), (15, 14), (16, 15),
    ]
    identity = _edge_matrix([(i, i) for i in range(17)], 17)
    inside = _normalize_digraph(_edge_matrix(inward, 17))
    outside = _normalize_digraph(_edge_matrix([(j, i) for i, j in inward], 17))
    return np.stack((identity, inside, outside)).astype(np.float32)


class UnitGCN(nn.Module):
    def __init__(self, in_channels: int, out_channels: int, adjacency: np.ndarray, with_res: bool = True):
        super().__init__()
        self.num_subsets = adjacency.shape[0]
        self.A = nn.Parameter(torch.tensor(adjacency, dtype=torch.float32))
        self.conv = nn.Conv2d(in_channels, out_channels * self.num_subsets, 1)
        self.bn = nn.BatchNorm2d(out_channels)
        self.act = nn.ReLU(inplace=True)
        self.down = (
            nn.Sequential(nn.Conv2d(in_channels, out_channels, 1), nn.BatchNorm2d(out_channels))
            if with_res and in_channels != out_channels
            else nn.Identity() if with_res else None
        )

    def forward(self, value: torch.Tensor) -> torch.Tensor:
        n, _, t, v = value.shape
        residual = 0 if self.down is None else self.down(value)
        value = self.conv(value).view(n, self.num_subsets, -1, t, v)
        value = torch.einsum("nkctv,kvw->nctw", value, self.A).contiguous()
        return self.act(self.bn(value) + residual)


class UnitTCN(nn.Module):
    def __init__(self, in_channels: int, out_channels: int, kernel_size: int = 9,
                 stride: int = 1, dilation: int = 1, dropout: float = 0.0,
                 norm: bool = True):
        super().__init__()
        padding = (kernel_size + (kernel_size - 1) * (dilation - 1) - 1) // 2
        self.conv = nn.Conv2d(
            in_channels, out_channels, (kernel_size, 1), stride=(stride, 1),
            padding=(padding, 0), dilation=(dilation, 1),
        )
        self.bn = nn.BatchNorm2d(out_channels) if norm else nn.Identity()
        self.drop = nn.Dropout(dropout, inplace=True)

    def forward(self, value: torch.Tensor) -> torch.Tensor:
        return self.drop(self.bn(self.conv(value)))


class MSTCN(nn.Module):
    def __init__(self, in_channels: int, out_channels: int, stride: int = 1, dropout: float = 0.0):
        super().__init__()
        configuration = [(3, 1), (3, 2), (3, 3), (3, 4), ("max", 3), "1x1"]
        middle = out_channels // len(configuration)
        remainder = out_channels - middle * (len(configuration) - 1)
        branches = []
        for index, item in enumerate(configuration):
            channels = remainder if index == 0 else middle
            if item == "1x1":
                branches.append(nn.Conv2d(in_channels, channels, 1, stride=(stride, 1)))
            elif item[0] == "max":
                branches.append(nn.Sequential(
                    nn.Conv2d(in_channels, channels, 1), nn.BatchNorm2d(channels),
                    nn.ReLU(inplace=True),
                    nn.MaxPool2d((item[1], 1), stride=(stride, 1), padding=(1, 0)),
                ))
            else:
                branches.append(nn.Sequential(
                    nn.Conv2d(in_channels, channels, 1), nn.BatchNorm2d(channels),
                    nn.ReLU(inplace=True),
                    UnitTCN(channels, channels, item[0], stride=stride, dilation=item[1], norm=False),
                ))
        self.branches = nn.ModuleList(branches)
        self.transform = nn.Sequential(
            nn.BatchNorm2d(out_channels), nn.ReLU(inplace=True),
            nn.Conv2d(out_channels, out_channels, 1),
        )
        self.bn = nn.BatchNorm2d(out_channels)
        self.drop = nn.Dropout(dropout, inplace=True)

    def forward(self, value: torch.Tensor) -> torch.Tensor:
        return self.drop(self.bn(self.transform(torch.cat([branch(value) for branch in self.branches], dim=1))))


class STGCNPPBlock(nn.Module):
    def __init__(self, in_channels: int, out_channels: int, adjacency: np.ndarray,
                 stride: int = 1, residual: bool = True, dropout: float = 0.0):
        super().__init__()
        self.gcn = UnitGCN(in_channels, out_channels, adjacency)
        self.tcn = MSTCN(out_channels, out_channels, stride=stride, dropout=dropout)
        if not residual:
            self.residual = None
        elif in_channels == out_channels and stride == 1:
            self.residual = nn.Identity()
        else:
            self.residual = UnitTCN(in_channels, out_channels, kernel_size=1, stride=stride)
        self.relu = nn.ReLU(inplace=True)

    def forward(self, value: torch.Tensor) -> torch.Tensor:
        residual = 0 if self.residual is None else self.residual(value)
        return self.relu(self.tcn(self.gcn(value)) + residual)


class STGCNPPEncoder(nn.Module):
    def __init__(self, adjacency: np.ndarray, in_channels: int = 3, base_channels: int = 64):
        super().__init__()
        channels = [base_channels] * 4 + [base_channels * 2] * 3 + [base_channels * 4] * 3
        strides = [1, 1, 1, 1, 2, 1, 1, 2, 1, 1]
        self.data_bn = nn.BatchNorm1d(in_channels * adjacency.shape[1])
        blocks = []
        previous = in_channels
        for index, (channels_out, stride) in enumerate(zip(channels, strides)):
            blocks.append(STGCNPPBlock(
                previous, channels_out, adjacency, stride=stride, residual=index != 0
            ))
            previous = channels_out
        self.gcn = nn.ModuleList(blocks)
        self.output_channels = channels[-1]

    def forward(self, value: torch.Tensor) -> torch.Tensor:
        n, c, t, v, m = value.shape
        value = value.permute(0, 4, 3, 1, 2).contiguous().view(n * m, v * c, t)
        value = self.data_bn(value)
        value = value.view(n, m, v, c, t).permute(0, 1, 3, 4, 2).contiguous()
        value = value.view(n * m, c, t, v)
        for block in self.gcn:
            value = block(value)
        return value.view(n, m, self.output_channels, value.shape[-2], value.shape[-1]).mean(1)


class ActionAdapterRiskClassifier(nn.Module):
    def __init__(self, *, num_actions: int, adapter_dim: int, adapter_scale: float):
        super().__init__()
        self.encoder = STGCNPPEncoder(graph_h36m17())
        self.adapter_scale = adapter_scale
        self.action_embed = nn.Embedding(num_actions, adapter_dim)
        self.adapter = nn.Sequential(
            nn.Linear(257 + adapter_dim, 128), nn.ReLU(inplace=True),
            nn.Dropout(0.1), nn.Linear(128, 257),
        )
        self.cls_head = nn.Sequential(
            nn.Linear(257, 128), nn.ReLU(inplace=True), nn.Dropout(0.2),
            nn.Linear(128, 3),
        )

    def forward(self, value: torch.Tensor, duration: torch.Tensor, action_id: torch.Tensor) -> torch.Tensor:
        features = F.adaptive_avg_pool2d(self.encoder(value), 1).flatten(1)
        features = torch.cat((features, duration), dim=1)
        delta = self.adapter(torch.cat((features, self.action_embed(action_id)), dim=1))
        return self.cls_head(features + self.adapter_scale * delta)
