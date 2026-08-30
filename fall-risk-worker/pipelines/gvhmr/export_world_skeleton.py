"""Export GVHMR global SMPL-X parameters and a metric gait-oriented 3D skeleton."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import torch
from einops import einsum


JOINT_NAMES = [
    "pelvis", "left_hip", "right_hip", "left_knee", "right_knee",
    "left_ankle", "right_ankle", "left_heel", "right_heel", "left_toe",
    "right_toe", "spine", "neck", "head", "head_top", "left_shoulder",
    "left_elbow", "left_wrist", "right_shoulder", "right_elbow", "right_wrist",
]
SMPL_INDICES = [0, 1, 2, 4, 5, 7, 8, 7, 8, 10, 11, 3, 12, 15, 15, 16, 18, 20, 17, 19, 21]


def _canonical_rotation(joints):
    """Rotate GVHMR Y-up global coordinates to X-forward/Y-left/Z-up."""
    pelvis = joints[:, 0]
    ground_motion = pelvis[:, [0, 2]] - pelvis[0, [0, 2]]
    if len(ground_motion) < 2 or np.linalg.norm(ground_motion[-1]) < 1e-6:
        forward2 = np.array([0.0, 1.0])
    else:
        covariance = np.cov(ground_motion.T)
        forward2 = np.linalg.eigh(covariance)[1][:, -1]
        if np.dot(forward2, ground_motion[-1] - ground_motion[0]) < 0:
            forward2 *= -1
    forward = np.array([forward2[0], 0.0, forward2[1]])
    up = np.array([0.0, 1.0, 0.0])
    left = np.cross(up, forward)
    rotation = np.stack((forward, left, up), axis=-1)
    canonical = joints @ rotation
    canonical -= canonical[0, 0]
    return canonical, rotation


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gvhmr-root", type=Path, required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--skeleton-output", type=Path, required=True)
    parser.add_argument("--smplx-output", type=Path, required=True)
    parser.add_argument("--fps", type=float, default=30.0)
    args = parser.parse_args()

    gvhmr_root = args.gvhmr_root.resolve()
    sys.path.insert(0, str(gvhmr_root))
    from hmr4d.utils.smplx_utils import make_smplx

    prediction = torch.load(args.input, map_location="cpu")
    parameters = prediction["smpl_params_global"]
    device = "cuda" if torch.cuda.is_available() else "cpu"
    body_model = make_smplx("supermotion").to(device)
    smplx_to_smpl = torch.load(
        gvhmr_root / "hmr4d/utils/body_model/smplx2smpl_sparse.pt", map_location=device
    )
    joint_regressor = torch.load(
        gvhmr_root / "hmr4d/utils/body_model/smpl_neutral_J_regressor.pt", map_location=device
    )
    with torch.no_grad():
        model_output = body_model(**{name: value.to(device) for name, value in parameters.items()})
        smpl_vertices = torch.stack([torch.matmul(smplx_to_smpl, vertices) for vertices in model_output.vertices])
        joints = einsum(joint_regressor, smpl_vertices, "j v, t v c -> t j c")
        joints = joints[:, SMPL_INDICES].cpu().numpy()

    canonical, rotation = _canonical_rotation(joints)
    canonical[:, JOINT_NAMES.index("head_top")] = canonical[:, JOINT_NAMES.index("head")] + 0.55 * (
        canonical[:, JOINT_NAMES.index("head")] - canonical[:, JOINT_NAMES.index("neck")]
    )

    args.skeleton_output.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        args.skeleton_output,
        joints=canonical.astype(np.float32),
        fps=np.float32(args.fps),
        joint_names=np.asarray(JOINT_NAMES),
        coordinate_system="X-forward,Y-left,Z-up,metres; origin=first-frame pelvis",
        source="GVHMR global SMPL-X -> SMPL joint regressor",
        metadata=json.dumps({
            "gvhmr_result": str(args.input.resolve()),
            "heel_proxy": "SMPL ankle joint",
            "world_to_canonical_rotation": rotation.tolist(),
        }),
    )

    smplx_payload = {
        name: value.detach().cpu().numpy().astype(np.float32)
        for name, value in parameters.items()
    }
    smplx_payload.update({
        "fps": np.float32(args.fps),
        "coordinate_system": np.asarray("GVHMR global coordinates: Y-up, metres"),
        "source_result": np.asarray(str(args.input.resolve())),
    })
    args.smplx_output.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(args.smplx_output, **smplx_payload)


if __name__ == "__main__":
    main()
