"""Inference-only implementation matching the trained CARE-PD checkpoint."""

from __future__ import annotations

import math

import torch
import torch.nn as nn
import torch.nn.functional as F


CONCEPT_LEVELS = {
    "step_length": ("normal", "mild", "moderate", "marked"),
    "walking_speed": ("normal", "mild", "moderate", "marked"),
    "foot_lift": ("normal", "mild", "moderate", "marked"),
    "arm_swing": ("normal", "mild", "moderate", "marked"),
    "cadence": ("normal", "abnormal"),
    "step_width": ("normal", "abnormal"),
    "lateral_stability": ("normal", "abnormal"),
    "stoop_posture": ("normal", "abnormal"),
}


class PositionalEncoding(nn.Module):
    def __init__(self, dimension: int, dropout: float, max_len: int = 5000) -> None:
        super().__init__()
        self.dropout = nn.Dropout(dropout)
        encoding = torch.zeros(max_len, dimension)
        position = torch.arange(max_len, dtype=torch.float).unsqueeze(1)
        divisor = torch.exp(torch.arange(0, dimension, 2).float() * (-math.log(10000.0) / dimension))
        encoding[:, 0::2] = torch.sin(position * divisor)
        encoding[:, 1::2] = torch.cos(position * divisor)
        self.register_buffer("pe", encoding.unsqueeze(0).transpose(0, 1))

    def forward(self, value: torch.Tensor) -> torch.Tensor:
        return self.dropout(value + self.pe[: value.shape[0]])


class MotionEncoder(nn.Module):
    def __init__(self, config: dict[str, object]) -> None:
        super().__init__()
        self.latent_dim = int(config["latent_dim"])
        self.muQuery = nn.Parameter(torch.randn(1, self.latent_dim))
        self.sigmaQuery = nn.Parameter(torch.randn(1, self.latent_dim))
        self.skelEmbedding = nn.Linear(int(config["njoints"]) * int(config["nfeats"]), self.latent_dim)
        self.sequence_pos_encoder = PositionalEncoding(self.latent_dim, float(config.get("dropout", 0.1)))
        layer = nn.TransformerEncoderLayer(
            d_model=self.latent_dim,
            nhead=int(config.get("num_heads", 4)),
            dim_feedforward=int(config.get("ff_size", 1024)),
            dropout=float(config.get("dropout", 0.1)),
            activation=str(config.get("activation", "gelu")),
        )
        self.seqTransEncoder = nn.TransformerEncoder(layer, num_layers=int(config.get("num_layers", 4)))

    def forward(self, batch: dict[str, torch.Tensor]) -> torch.Tensor:
        x, y, mask = batch["x"], batch["y"], batch["mask"]
        frames, batch_size = x.shape[-1], x.shape[0]
        x = x.permute(3, 0, 1, 2).reshape(frames, batch_size, -1)
        x = self.skelEmbedding(x)
        y = y - y
        sequence = torch.cat((self.muQuery[y][None], self.sigmaQuery[y][None], x), dim=0)
        sequence = self.sequence_pos_encoder(sequence)
        prefix_mask = torch.ones((batch_size, 2), dtype=torch.bool, device=x.device)
        encoded = self.seqTransEncoder(sequence, src_key_padding_mask=~torch.cat((prefix_mask, mask), dim=1))
        return encoded[0]


class ConceptProjector(nn.Module):
    def __init__(self, latent_dim: int, hidden_dim: int) -> None:
        super().__init__()
        self.network = nn.Sequential(
            nn.Linear(latent_dim, hidden_dim), nn.GELU(), nn.Linear(hidden_dim, latent_dim)
        )

    def forward(self, embedding: torch.Tensor) -> torch.Tensor:
        return F.normalize(self.network(embedding), dim=-1)


class MedicalConceptHeads(nn.Module):
    def __init__(self, names: list[str], latent_dim: int, hidden_dim: int, temperature: float) -> None:
        super().__init__()
        self.names = tuple(names)
        counts = tuple(len(CONCEPT_LEVELS[name]) for name in names)
        self.max_classes = max(counts)
        self.logit_scale = 1.0 / temperature
        self.projectors = nn.ModuleDict(
            {name: ConceptProjector(latent_dim, hidden_dim) for name in names}
        )
        self.register_buffer("text_prototypes", torch.zeros(len(names), self.max_classes, latent_dim))
        mask = torch.zeros(len(names), self.max_classes, dtype=torch.bool)
        for index, count in enumerate(counts):
            mask[index, :count] = True
        self.register_buffer("class_mask", mask)

    def forward(self, embedding: torch.Tensor) -> torch.Tensor:
        logits = []
        for index, name in enumerate(self.names):
            projected = self.projectors[name](F.normalize(embedding, dim=-1))
            value = self.logit_scale * projected @ F.normalize(self.text_prototypes[index], dim=-1).T
            logits.append(value.masked_fill(~self.class_mask[index][None, :], -torch.inf))
        return torch.stack(logits, dim=1)


class CarePdModel(nn.Module):
    architecture_name = "carepd_encoder_only_reference_difference_v1"

    def __init__(self, config: dict[str, object]) -> None:
        super().__init__()
        model_config = config["model"]
        concept_config = config["concepts"]
        self.encoder = MotionEncoder(model_config)
        self.concept_names = tuple(concept_config["names"])
        self.concept_heads = MedicalConceptHeads(
            list(self.concept_names),
            int(model_config["latent_dim"]),
            int(concept_config["hidden_dim"]),
            float(concept_config["temperature"]),
        )
        self.register_buffer("healthy_reference", torch.zeros(int(model_config["latent_dim"])))

    def forward(self, batch: dict[str, torch.Tensor]) -> dict[str, torch.Tensor]:
        embedding = F.normalize(self.encoder(batch).float(), dim=-1)
        reference = F.normalize(self.healthy_reference.float(), dim=-1)
        relative = F.normalize(embedding - reference[None, :], dim=-1)
        return {
            "healthy_distance": 1.0 - torch.sum(embedding * reference, dim=-1),
            "concept_probabilities": self.concept_heads(relative).softmax(dim=-1),
        }


def load_model(checkpoint: str, device: torch.device) -> tuple[CarePdModel, dict[str, object]]:
    payload = torch.load(checkpoint, map_location="cpu", weights_only=True)
    config = payload.get("config")
    if not isinstance(config, dict) or payload.get("architecture") != CarePdModel.architecture_name:
        raise ValueError("Unsupported MotionCLIP checkpoint architecture")
    model = CarePdModel(config).to(device)
    model.load_state_dict(payload["state_dict"], strict=True)
    model.eval().requires_grad_(False)
    return model, config


def quaternion_to_matrix(quaternion: torch.Tensor) -> torch.Tensor:
    r, i, j, k = torch.unbind(quaternion, -1)
    scale = 2.0 / (quaternion * quaternion).sum(-1)
    values = (
        1 - scale * (j * j + k * k), scale * (i * j - k * r), scale * (i * k + j * r),
        scale * (i * j + k * r), 1 - scale * (i * i + k * k), scale * (j * k - i * r),
        scale * (i * k - j * r), scale * (j * k + i * r), 1 - scale * (i * i + j * j),
    )
    return torch.stack(values, -1).reshape(quaternion.shape[:-1] + (3, 3))


def axis_angle_to_matrix(axis_angle: torch.Tensor) -> torch.Tensor:
    angles = torch.norm(axis_angle, p=2, dim=-1, keepdim=True)
    half = 0.5 * angles
    small = angles.abs() < 1e-6
    ratio = torch.empty_like(angles)
    ratio[~small] = torch.sin(half[~small]) / angles[~small]
    ratio[small] = 0.5 - angles[small] * angles[small] / 48
    return quaternion_to_matrix(torch.cat((torch.cos(half), axis_angle * ratio), dim=-1))


def matrix_to_rotation_6d(matrix: torch.Tensor) -> torch.Tensor:
    return matrix[..., :2, :].clone().reshape(*matrix.size()[:-2], 6)
