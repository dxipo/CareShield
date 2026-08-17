# M5 — Real Fall Detection Baseline

M5 adds the first real AI path to CareShield. It consumes a temporary H.265
HLS stream through an authenticated Backend boundary, runs a pretrained human
pose estimator on the AI Worker GPU, applies a transparent temporal heuristic,
and publishes the existing M4 `AlgorithmResult` contract with
`task=fall_detection` and `simulated=false`.

```text
H6c -> EZVIZ -> Backend StreamService -> authenticated temporary HLS
     -> AI Worker MediaReader -> FrameSampler -> UltralyticsPoseEstimator
     -> CareShield Pose -> FallFeatureExtractor -> TemporalFallDetector
     -> ResultPublisher -> Backend -> Redis -> WebSocket -> Vue
```

## Security boundary

- The AI Worker receives neither EZVIZ AppKey/AppSecret nor AccessToken.
- `GET /internal/media/devices` and
  `GET /internal/media/devices/{serial}/stream` require the M4 internal Bearer
  token. The latter is the only Worker API that returns a temporary address.
- Playback addresses remain in process memory. They are not written to Redis,
  `AlgorithmResult`, logs, fixtures, documentation, or Git.
- Worker and media exceptions only expose safe categories or HTTP status codes;
  response bodies and request credentials are deliberately discarded.

## Pose contract

`UltralyticsPoseEstimator` maps framework objects into CareShield-owned values:

- normalized `BoundingBox`;
- `person_id` and box confidence;
- 17 named COCO body keypoints and confidence;
- source timestamp and dimensions.

The detector never imports or receives an Ultralytics `Results` object. Multiple
persons are preserved; M5 selects the highest-confidence person as the primary
home-scene subject without making single-person input a permanent contract.

## Temporal baseline

The baseline extracts normalized torso angle, shoulder/hip orientation, hip
height and vertical velocity, body-centre velocity, box aspect ratio, horizontal
skeleton extent, body-height change, and keypoint confidence. A state machine
uses `NORMAL -> SUSPECTED_FALL -> FALLEN -> RECOVERING -> NORMAL`.

A fast downward movement plus tilt is required to enter `SUSPECTED_FALL`, and a
lying posture must persist before `FALLEN`. Static lying, bending, and sitting
must not trigger from one frame. All parameters live in `FallDetectionConfig`
and environment variables. They are engineering baseline values, not clinically
validated thresholds.

`score` is a bounded evidence score. `metadata.score_type=heuristic` explicitly
states that it is not a calibrated fall probability.

## Result policy and failure semantics

- Frame sampling follows the decoded media PTS rather than frame-arrival wall
  time. HLS segments can deliver frames in bursts, so arrival-time sampling
  would incorrectly reduce a configured 5 FPS target to roughly one frame per
  segment. Wall time remains the source for measured processing throughput.
- State changes publish immediately.
- Significant score changes may publish immediately.
- Stable monitoring publishes at a configurable low-frequency heartbeat.
- `no_person`, low pose confidence, missing media, or model failure never become
  an automatic `normal` result.
- Fall detection failure leaves Backend, Redis, WebSocket, devices, and browser
  live media running.

## Dependencies and licenses

| Dependency | Pinned version | Purpose | Upstream license / note |
| --- | --- | --- | --- |
| PyTorch | 2.13.0+cu130 | CUDA pose inference | upstream BSD-3-Clause with bundled third-party notices |
| torchvision | 0.28.0+cu130 | Ultralytics runtime dependency | BSD-3-Clause |
| Ultralytics | 8.4.120 | YOLO26 pose inference | AGPL-3.0 or Ultralytics Enterprise |
| YOLO26n-pose | official pretrained weight | 17-keypoint COCO pose | Ultralytics model licensing applies |
| PyAV | 18.1.0 | FFmpeg-based H.265/HLS decode | PyAV source is BSD; its current binary wheel bundles FFmpeg components and requires GPL distribution review |
| NumPy | 2.2.6 | image arrays | BSD-3-Clause plus bundled component notices |

Ultralytics' official documentation describes YOLO26 as the latest model family
and `yolo26n-pose.pt` as the nano real-time pose checkpoint. Because AGPL and
Enterprise are alternative licensing paths, proprietary deployment requires an
explicit license review. This project is not making a legal determination.

## GPU and portability

The default M5 Compose deployment requests all GPUs and the local acceptance
environment sets `AI_DEVICE=cuda`. `docker-compose.cpu.yml` removes that device
request for a non-GPU computer:

```bash
docker compose -f docker-compose.yml -f docker-compose.cpu.yml up -d --build
```

On CPU or when a model/stream cannot load, the Worker stays healthy but reports
Fall Detection as unavailable. Core frontend, Backend, PostgreSQL, and Redis can
also be started independently. M5 does not install or change the host NVIDIA
driver; NVIDIA Container Toolkit is a host prerequisite for the GPU deployment.

Model files remain under ignored `models/`. The runtime heartbeat reports the
actual model SHA-256, framework/CUDA versions, GPU identity, model load time and
memory use without exposing any media address.

## Safe testing

Unit tests use synthetic pose fixtures and do not require CUDA, a model, a live
camera, or a person falling. Manual validation should use ordinary movement,
sitting, bending, and only controlled safe motion on a suitable soft surface.
Never ask an older person to perform a dangerous fall.
