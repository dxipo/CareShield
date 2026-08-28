# M5.2 — STGCN-Extend Real Fall Detection Baseline

M5.2 integrates the existing research project `STGCN-Extend` into CareShield.
The AI Worker decodes a real H6c stream, extracts COCO17 poses with a YOLO pose
model plus an independent YOLO person detector, tracks people, resamples a
two-second real observation window to 75 model frames, and runs
the real binary classifier. Results use the M4 `AlgorithmResult` contract with
`task=fall_detection` and `simulated=false`.

```text
H6c -> EZVIZ -> Backend temporary HTTP-FLV (internal Bearer auth)
     -> PyAV MediaReader -> FrameSampler -> YOLO Person + YOLO Pose
     -> Detection/Pose fusion -> stable person tracker
     -> 2 s real window -> 75 interpolated COCO17 model frames
     -> STGCN-Extend predictor/classifier -> decision debounce
     -> ResultPublisher -> Backend -> Redis -> WebSocket -> Vue
```

The browser and algorithm both use the same camera, but not the same transport:
the browser uses official low-latency EZOPEN while the Ubuntu AI Worker uses
HTTP-FLV. FFmpeg/PyAV cannot consume the private `ezopen://` protocol.

## Security boundary

- The AI Worker receives no EZVIZ AppKey, AppSecret, or AccessToken.
- The internal device and stream endpoints require the M4 Worker Bearer token.
- The internal stream endpoint requests live HTTP-FLV (`protocol=4`) from the
  existing `StreamService`; the public browser and diagnostic endpoints keep
  their own contracts.
- Playback addresses exist only in process memory. They are not placed in
  results, Redis, logs, tests, documentation, `.env`, or Git.
- Model weights are mounted from ignored `models/` and are never committed.

## Pose and tracking contracts

`UltralyticsPersonDetector` detects COCO class `person` independently from the
pose estimator. This preserves a visible person box when a horizontal or partly
occluded body no longer yields reliable keypoints. `UltralyticsPoseEstimator`
converts framework-specific results into the
CareShield-owned `PoseFrame`, `PosePerson`, `BoundingBox`, and `PoseKeypoint`
types. Coordinates are normalized to `[0, 1]`; each person contains 17 named
COCO keypoints and confidences.

The pose proposal threshold is `0.20` so a horizontal body is not discarded
solely because its whole-person proposal confidence is lower. The independent
per-keypoint reliability threshold remains `0.35`; at least six reliable joints
and the sequence-validity gate are still required before STGCN runs.

Inference uses a `960`-pixel input on the RTX 4090 to preserve more joint detail
for horizontal bodies and for people occupying a smaller part of the 1080p
camera image. The detector and tracker can retain multiple candidates, while
the M5 home baseline selects one stable `primary-person` for preview and STGCN;
this prevents transient secondary boxes from resetting the primary sequence.
If full-frame pose misses an independently detected horizontal body, the Worker
performs a real crop-level pose inference. If needed, it also tries 90-degree
crop orientations and maps any detected keypoints back to the source image.
This fallback never copies an earlier skeleton or invents keypoints.

The tracker combines IoU and normalized center distance, tolerates short pose
loss, assigns stable IDs, and preserves multiple people. `PoseSequenceStore`
maintains an independent two-second, timestamped observation buffer per active
ID. Before inference, valid `[0, 1]` coordinates are mapped to the
training preprocessing range `[-1, 1]`; missing or low-confidence keypoints are
zeroed. The input is completed to 100 frames with 25 placeholders because the
model produces those future frames internally. Roughly 30 real frames at 15 FPS
are linearly resampled to 75 observed model positions. This is temporal
alignment, not frame synthesis: it creates no new visual evidence and the UI
continues to report source, sampled, and processing FPS separately. This avoids feeding 100 live
frames and then silently ignoring the newest 25. A detected box with insufficient reliable keypoints produces
`low_pose_confidence`, never `normal`.

At least 80% of an observed window must contain a reliable pose before the
classifier can emit a safe or fall state. The live sampler targets the H6c
source rate (15 FPS); the timestamp window makes warm-up approximately two
seconds when person tracking and pose quality remain continuous. The original
processed dataset does not record a trustworthy universal source-FPS contract;
this temporal-domain difference remains a retraining and validation risk.

## STGCN-Extend model

The Worker vendors only the state-dict-compatible inference architecture needed
from the research source: STGCN++ graph backbone, future-pose decoder, and
binary classifier head. Input and output are:

```text
input:             [N, 1, 100, 17, 2]
future prediction: [N, 25, 17, 2]
class logits:      [N, 2]
```

The first 75 observed frames plus 25 predicted frames feed the classifier, as
in the source project. Class index 1 is the fall class. The current runtime
checkpoint is the first-fold best classifier supplied with the research
project; expected SHA-256:

```text
343b24d905b2237242c3e90e08687bf72eb8e0da821a9b325d3f85bcff14131e
```

Loading uses `weights_only=True` and `strict=True`. The runtime heartbeat reports
the actual checksum. The checkpoint file itself is not distributed through Git.

The research dataset contains 440 processed clips (200 fall, 240 non-fall) from
a small number of subjects. Its recorded split is not an independent
cross-subject or external validation. Consequently, the observed training
validation score must not be described as clinical or deployment accuracy.

As an integration check, the vendored architecture, original preprocessing,
`num_person=1`, supplied checkpoint, and recorded 88-sample test split reproduced
88/88 stored labels (34/34 fall and 54/54 non-fall) on the RTX 4090. This proves
checkpoint/preprocessing compatibility only; the split's subject overlap and
small sample size make the 100% figure unsuitable as a generalization claim.

## Decision and safety semantics

The raw class-1 softmax is reported as an uncalibrated `fall_score`, not a
probability. `STGCNDecisionEngine` applies configurable multi-window debounce:

```text
NORMAL -> SUSPECTED_FALL -> FALLEN -> RECOVERING -> NORMAL
```

State changes publish immediately; stable monitoring uses the existing bounded
heartbeat policy. The following states are explicitly unavailable rather than
safe: no person, low pose confidence, incomplete warm-up sequence, media loss,
model failure, or Backend delivery failure.

The `0.80` fallen threshold confirms on one classifier result because that
result already summarizes a two-second pose sequence; it is not a single-frame
rule. Scores from `0.60` to `0.80` remain `SUSPECTED_FALL`. These thresholds and
the uncalibrated score still require broader false-positive validation.

Confirmed fall alerts are latched across later `no_person`, low-confidence, or
recovering results until an operator acknowledges the current incident. Recent
non-simulated state changes are stored as a bounded, expiring Redis list for
operator review; repeated heartbeat states are deduplicated. This is diagnostic
history, not the later formal Event Center.

The preview banner is controlled only by the latched alert, not by the raw
detector state. Acknowledging an incident therefore removes `FALL DETECTED` on
the next rendered frame even if the current two-second classifier window still
has label `fallen`. A later, re-armed fall can raise a new alert.

The analysis preview is an in-memory MJPEG generated from the exact sampled
inference frames. It draws person boxes and COCO17 skeletons, and displays a red
banner only for `FALLEN`. Frames are not written to disk. It is intentionally
separate from the original EZOPEN video because the two paths have different
transport and processing latency.

Formal event persistence, SMS/phone notification, emergency contacts, and
escalation workflows are not implemented in M5.2.

## Dependencies and licenses

| Dependency/artifact | Pinned version | Purpose | License / note |
| --- | --- | --- | --- |
| PyTorch | 2.13.0+cu130 | CUDA STGCN and pose runtime | BSD-3-Clause with third-party notices |
| torchvision | 0.28.0+cu130 | Ultralytics runtime dependency | BSD-3-Clause |
| Ultralytics | 8.4.120 | YOLO26 detection and pose inference | AGPL-3.0 or Enterprise |
| YOLO26m-pose | official pretrained weight, SHA-256 `2fbf16367022256a226035695c5c389384c6706e8bb8ab8fcd0e7976f05443c4` | stronger COCO17 pose baseline | Ultralytics model licensing applies |
| YOLO26s | official pretrained weight, SHA-256 `646f8bc3fe0a656803d95c294f7852321748cb29d13466a1af8862e2db384a1b` | independent COCO person detection | Ultralytics model licensing applies |
| PyAV | 18.1.0 | FFmpeg-based HEVC/HTTP-FLV decode | BSD source; bundled FFmpeg distribution needs review |
| NumPy | 2.2.6 | sequence arrays | BSD-3-Clause plus component notices |
| STGCN-Extend source/checkpoint | research artifact supplied by project owner | fall classification | source repository contains no explicit license file; redistribution review required |

This document records engineering provenance and does not make a legal
determination. Commercial deployment requires an explicit review of Ultralytics,
the pretrained pose weight, FFmpeg build, and STGCN research artifact.

## GPU, portability, and safe testing

The default Compose deployment requests a GPU; the acceptance host must use
CUDA. The CPU override keeps the rest of CareShield portable. GPU or model
failure leaves the Worker health endpoint alive but marks Fall Detection
unavailable.

Unit tests use synthetic pose sequences and never require a real fall. Manual
validation should use a 10–15 second clip with at least three seconds upright,
a clearly visible transition, and at least five seconds lying down. It should
also cover ordinary walking, sitting, bending, and controlled safe
motions on suitable padding. Never ask an older person to perform a dangerous
fall. The baseline requires further cross-subject evaluation, threshold tuning,
false-positive analysis, and field validation before safety-critical use.

Model selection and task behavior follow the official Ultralytics documentation:
<https://docs.ultralytics.com/tasks/detect/>,
<https://docs.ultralytics.com/tasks/pose/>, and
<https://docs.ultralytics.com/modes/track/>.
