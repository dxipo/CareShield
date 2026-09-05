"""Headless GVHMR inference adapter.

This module follows GVHMR's public demo path through tracking, ViTPose,
visual-feature extraction, optional visual odometry and HMR4D prediction.  It
stops before mesh rendering and therefore produces only ``hmr4d_results.pt``.
It must be launched with the GVHMR environment and repository on ``sys.path``.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import hydra
import torch
from hydra import compose, initialize_config_module
from tqdm import tqdm

import hmr4d.model.gvhmr.utils.endecoder  # noqa: F401
import hmr4d.network.gvhmr.relative_transformer  # noqa: F401
from hmr4d.model.gvhmr.gvhmr_pl_demo import DemoPL
from hmr4d.utils.geo.hmr_cam import convert_K_to_K4, create_camera_sensor, estimate_K, get_bbx_xys_from_xyxy
from hmr4d.utils.geo_transform import compute_cam_angvel
from hmr4d.utils.net_utils import detach_to_cpu
from hmr4d.utils.preproc import Extractor, Tracker, VitPoseExtractor
from hmr4d.utils.pylogger import Log
from hmr4d.utils.video_io_utils import get_video_lwh, get_video_reader, get_writer


def _quaternion_to_matrix(quaternions: torch.Tensor) -> torch.Tensor:
    """Convert real-first quaternions to rotation matrices without a renderer dependency."""
    r, i, j, k = torch.unbind(quaternions, -1)
    two_s = 2.0 / (quaternions * quaternions).sum(-1)
    values = (
        1 - two_s * (j * j + k * k), two_s * (i * j - k * r), two_s * (i * k + j * r),
        two_s * (i * j + k * r), 1 - two_s * (i * i + k * k), two_s * (j * k - i * r),
        two_s * (i * k - j * r), two_s * (j * k + i * r), 1 - two_s * (i * i + j * j),
    )
    return torch.stack(values, -1).reshape(quaternions.shape[:-1] + (3, 3))


def _configuration(video: Path, output_root: Path, static_camera: bool, use_dpvo: bool, focal_length_mm: int | None):
    with initialize_config_module(version_base="1.3", config_module="hmr4d.configs"):
        overrides = [
            f"video_name={video.stem}",
            f"output_root={output_root}",
            f"static_cam={static_camera}",
            "verbose=False",
            f"use_dpvo={use_dpvo}",
        ]
        if focal_length_mm is not None:
            overrides.append(f"f_mm={focal_length_mm}")
        cfg = compose(config_name="demo", overrides=overrides)
    Path(cfg.output_dir).mkdir(parents=True, exist_ok=True)
    Path(cfg.preprocess_dir).mkdir(parents=True, exist_ok=True)
    return cfg


def _copy_video_to_working_stream(video: Path, cfg) -> None:
    destination = Path(cfg.video_path)
    if destination.exists() and get_video_lwh(video)[0] == get_video_lwh(destination)[0]:
        return
    reader = get_video_reader(video)
    writer = get_writer(destination, fps=30, crf=23)
    for image in tqdm(reader, total=get_video_lwh(video)[0], desc="Preparing video"):
        writer.write_frame(image)
    writer.close()
    reader.close()


@torch.no_grad()
def _preprocess(cfg) -> None:
    paths = cfg.paths
    video = cfg.video_path
    if not Path(paths.bbx).exists():
        tracker = Tracker()
        boxes = tracker.get_one_track(video).float()
        scaled_boxes = get_bbx_xys_from_xyxy(boxes, base_enlarge=1.2).float()
        torch.save({"bbx_xyxy": boxes, "bbx_xys": scaled_boxes}, paths.bbx)
        del tracker
    else:
        scaled_boxes = torch.load(paths.bbx, map_location="cpu")["bbx_xys"]

    if not Path(paths.vitpose).exists():
        extractor = VitPoseExtractor()
        torch.save(extractor.extract(video, scaled_boxes), paths.vitpose)
        del extractor
    if not Path(paths.vit_features).exists():
        extractor = Extractor()
        torch.save(extractor.extract_video_features(video, scaled_boxes), paths.vit_features)
        del extractor

    if not cfg.static_cam and not Path(paths.slam).exists():
        if cfg.use_dpvo:
            from hmr4d.utils.preproc.slam import SLAMModel

            length, width, height = get_video_lwh(video)
            intrinsics = convert_K_to_K4(estimate_K(width, height))
            slam = SLAMModel(video, width, height, intrinsics, buffer=4000, resize=0.5)
            progress = tqdm(total=length, desc="Estimating camera motion")
            while slam.track():
                progress.update()
            progress.close()
            torch.save(slam.process(), paths.slam)
        else:
            from hmr4d.utils.preproc.relpose.simple_vo import SimpleVO

            estimator = SimpleVO(video, scale=0.5, step=8, method="sift", f_mm=cfg.f_mm)
            torch.save(estimator.compute(), paths.slam)


def _model_input(cfg) -> dict[str, torch.Tensor]:
    paths = cfg.paths
    length, width, height = get_video_lwh(cfg.video_path)
    if cfg.static_cam:
        rotation_world_to_camera = torch.eye(3).repeat(length, 1, 1)
    else:
        trajectory = torch.load(paths.slam, map_location="cpu")
        if cfg.use_dpvo:
            quaternion = torch.from_numpy(trajectory[:, [6, 3, 4, 5]])
            rotation_world_to_camera = _quaternion_to_matrix(quaternion).mT
        else:
            rotation_world_to_camera = torch.from_numpy(trajectory[:, :3, :3])
    if cfg.f_mm is None:
        camera_matrix = estimate_K(width, height).repeat(length, 1, 1)
    else:
        camera_matrix = create_camera_sensor(width, height, cfg.f_mm)[2].repeat(length, 1, 1)
    return {
        "length": torch.tensor(length),
        "bbx_xys": torch.load(paths.bbx, map_location="cpu")["bbx_xys"],
        "kp2d": torch.load(paths.vitpose, map_location="cpu"),
        "K_fullimg": camera_matrix,
        "cam_angvel": compute_cam_angvel(rotation_world_to_camera),
        "f_imgseq": torch.load(paths.vit_features, map_location="cpu"),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--static-camera", action="store_true")
    parser.add_argument("--use-dpvo", action="store_true")
    parser.add_argument("--focal-length-mm", type=int)
    args = parser.parse_args(argv)
    video = Path(args.video)
    if not video.is_file():
        raise FileNotFoundError("input video is unavailable")
    if not torch.cuda.is_available():
        raise RuntimeError("GVHMR inference requires a CUDA-capable GPU")

    cfg = _configuration(video, Path(args.output_root), args.static_camera, args.use_dpvo, args.focal_length_mm)
    _copy_video_to_working_stream(video, cfg)
    _preprocess(cfg)
    result = Path(cfg.paths.hmr4d_results)
    if not result.exists():
        data = _model_input(cfg)
        model: DemoPL = hydra.utils.instantiate(cfg.model, _recursive_=False)
        model.load_pretrained_model(cfg.ckpt_path)
        model = model.eval().cuda()
        torch.save(detach_to_cpu(model.predict(data, static_cam=cfg.static_cam)), result)
    print(result.name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
