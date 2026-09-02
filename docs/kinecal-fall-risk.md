# KINECAL ST-GCN++ 跌倒风险分类

## 定位

CareShield 将两个批处理模型明确分工：KINECAL ST-GCN++ 用于跌倒风险
等级分类，MotionCLIP 用于神经运动功能模式分析。两者共享同一次 GVHMR
处理结果，但运行在不同容器中，互不加载对方模型和依赖。

```text
assessment video -> VisionMD/GVHMR -> world_skeleton_3d.npz
                                      |-> kinecal-risk-worker -> fall_risk_result
                                      `-> motionclip-worker    -> risk_result (legacy name)
```

## 模型合同

- Architecture: ST-GCN++ encoder + duration feature + action embedding/adapter + 3-class head
- Input: float32 `[N, 3, 120, 17, 1]`
- Skeleton: H36M-17
- Action: `3m-walk-Front-View` (`action_id=0` in the checkpoint)
- Labels: `NF=0`, `FHs=1`, `FHm=2`
- UI mapping: low, medium, high
- Duration normalization: global mean `17.18098258972168 s`, standard deviation
  `5.021009014678955 s`, recovered from the exact training cache
  `clip120_durglobal_age0_scopeall.pt` (461 samples).

The worker verifies the checkpoint SHA-256 before loading it. Weight files remain
under ignored `models/` storage and are mounted read-only.

## Input adaptation

The existing GVHMR export contains 21 world/canonical joints. The KINECAL worker
maps them to the checkpoint's exact H36M-17 order, reconstructs the thorax as the
shoulder midpoint, converts `X-forward/Y-left/Z-up` to Kinect-like
`X-right/Y-up/Z-depth`, interpolates isolated missing coordinates, resamples to
120 frames, centres every frame at the pelvis, and applies the same sequence
scale normalization used during training.

No EZVIZ credential, playback URL or source video is passed to this worker.

## Validation limits

The deployed v2 fold checkpoint has better held-out 3 m walk accuracy (74%) than
v1, but the reported 3 m walk high-risk recall is 0 on seven high-risk samples.
The training run also used sample-level stratified folds (`group_by_subject=false`),
so subject-level leakage between actions cannot be excluded. The very high
subject-fused metric must not be presented as expected single-video accuracy.

The result is therefore a research cohort classification rather than a clinical
diagnosis or calibrated probability. Low-confidence output is marked for review.
Adding STS-5/TUG and subject-separated retraining is recommended before clinical
or safety-critical use.

## License

The supplied source repository grants use, modification and redistribution only
for academic and non-commercial research. Commercial deployment requires a
separate rights review. Raw KINECAL data and the vendored legacy MMCV/MDetection
trees are not copied into CareShield.
