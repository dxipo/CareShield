# MotionCLIP Worker

Independent, long-lived GPU inference boundary for the CARE-PD explainable
MotionCLIP model. It reads only GVHMR parameter artifacts from the shared
fall-risk volume; it never receives camera credentials or playback URLs.

The inference-only architecture required by the trained checkpoint is kept in
this service, so deployment does not depend on an uncommitted external source
checkout. The checkpoint and isolated PyTorch runtime remain operator-provided
and Git-ignored.

The default profile reports a continuous healthy-reference distance, eight
gait concepts, and a low/medium/high research risk grade. The ordered thresholds
come from the CARE-PD-like training-split calibration bundled in `config/`.
They are not independently clinically validated and the distance is not a fall
probability.
