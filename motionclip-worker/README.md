# MotionCLIP Worker

Independent, long-lived GPU inference boundary for the CARE-PD explainable
MotionCLIP model. It reads only GVHMR parameter artifacts from the shared
fall-risk volume; it never receives camera credentials or playback URLs.

The inference-only architecture required by the trained checkpoint is kept in
this service, so deployment does not depend on an uncommitted external source
checkout. The checkpoint and isolated PyTorch runtime remain operator-provided
and Git-ignored.

The default profile reports a continuous healthy-reference distance and eight
gait concepts. It is research-only and has no independently validated clinical
risk thresholds, so `risk_level` remains `null`.
