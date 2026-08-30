# CareShield VisionMD-Gait integration

This directory contains the minimal executable subset supplied by the project's
existing `risk_firststage/VisionMD-Gait-Standalone-28` research code. The original
backend license is preserved as `LICENSE` (GPL-2.0).

The bundled Gait Transformer weight is `backend/app/analysis/models/gait_transformer/assets/model_v0.2.h5`.
The MeTRAbs SavedModel is not committed. Prepare the official non-commercial model
once in the ignored `models/fall-risk/visionmd/metrabs_local_s` directory and mount
it read-only at runtime.

MeTRAbs and its released models are limited to non-commercial use due to their
training datasets. Product use requires a separate license review.
