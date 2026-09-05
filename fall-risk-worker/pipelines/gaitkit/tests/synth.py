"""测试共用的合成步态数据构造器（全部期望值有解析推导，见各函数注释）。

设计（所有测试共享的"已知真值步行"）：
- 30 Hz，12 s（361 帧，t = 0..12.0）；Z-up（up_axis=2），沿 +X 行走；
- 骨盆 x = v·t（v = 1.0 m/s 匀速），z = 1.0 m，y 可选小幅横向摆动；
- 步时 0.6 s → 步频 100 spm；跨步 1.2 s；支撑 0.72 s；摆动 0.48 s；
  双支撑分量 0.12 s → double_support_time_s = 2×0.12 = 0.24 s；
- 步长 = v×0.6 = 0.6 m；步速 = 0.6/0.6 = 1.0 m/s；步宽 = 0.18 m；
- 抬脚高度 = 0.05 m（踝竖直振幅 0.05 正弦）；摆臂 = 0.6 m（腕-骨盆峰峰值）；
- 躯干前倾 = atan(0.2/0.8) ≈ 14.0362°；左右腿姿态差构造出髋/膝不对称各 10°；
- 腿长 = 0.9 m；髋宽 = 0.18 m；零摆动时 eCOM/XCoM RMS = 0，eMOS = 0.09 m，
  髋宽归一化 eMOS = 0.5。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

from gaitkit.core import GaitEvents, Trajectory

FPS = 30.0
DURATION_S = 12.0
SPEED_M_S = 1.0
STEP_TIME_S = 0.6          # 步时 → 步频 100 spm
STRIDE_TIME_S = 1.2        # 跨步 = 2×步时
STANCE_TIME_S = 0.72       # 支撑 = 60% 跨步
SWING_TIME_S = 0.48        # 摆动 = 跨步 − 支撑
DS_COMPONENT_S = 0.12      # 双支撑分量 = 支撑 − 步时
LEG_LENGTH_M = 0.9         # 腿长（|髋−膝| + |膝−踝|）
HIP_WIDTH_M = 0.18         # 髋宽 = 步宽（踝与髋同横向坐标）
FOOT_LIFT_M = 0.05         # 踝竖直振幅
ARM_SWING_M = 0.6          # 腕-骨盆行进轴峰峰值 = 2×0.3
TRUNK_TILT_DEG = float(np.degrees(np.arctan(0.25)))  # ≈ 14.03624°
ASYMMETRY_DEG = 10.0       # 右腿大腿前倾 10° → 髋/膝不对称各 10°


def make_explicit_events(duration_s: float = DURATION_S) -> GaitEvents:
    """与合成轨迹配套的"真值"事件（直接给定，绕过检测器以隔离指标数学）。

    推导：左 HS 于 0, 1.2, ...；右 HS 于 0.6, 1.8, ...；TO = 同侧 HS + 0.72。
    交替 HS 间隔恒为 0.6 s；右 HS 后 0.12 s 左 TO、左 HS 后 0.12 s 右 TO
    （0.12 ≤ 0.5 计入双支撑分量；首末边缘分量按参考实现规则自然排除：
    左 HS=0 时其后右 TO=1.32 超出 0.5 s 窗，右 HS=11.4 时左 TO 差 0.52 s 同理）。

    HS 时刻按帧号生成（36 帧 = 1.2 s、18 帧 = 0.6 s @30Hz），与轨迹时间轴
    逐位一致——否则 arange 的浮点累积会使 mask 端点偏移 1 帧，
    抬脚高度等"端点值"类参数出现 1e-3 量级偏差。
    """
    n_frames = int(round(duration_s * FPS)) + 1
    stride_frames = int(round(STRIDE_TIME_S * FPS))   # 36
    left_hs = np.arange(0, n_frames, stride_frames) / FPS
    right_hs = np.arange(stride_frames // 2, n_frames, stride_frames) / FPS
    left_to = left_hs + STANCE_TIME_S
    right_to = right_hs + STANCE_TIME_S
    return GaitEvents(
        left_down=left_hs, right_down=right_hs, left_up=left_to, right_up=right_to,
        detector="synthetic_ground_truth",
    )


def make_synthetic_walk(
    sway_m: float = 0.0,
    speed_m_s: float = SPEED_M_S,
    duration_s: float = DURATION_S,
    fps: float = FPS,
    world_grounded: bool = True,
    participant: str = "SYN01",
    view: str = "synthetic",
) -> Trajectory:
    """构造 17 关节合成步行轨迹（世界系，Z-up，沿 +X）。

    运动学推导（期望值的来源）：

    - 骨盆 (v·t, sway, 1.0)：行进轴 PCA 第一主成分 = +X（摆动幅度 0.02 时
      横向方差 ~2e-4 远小于行进方差 12，轴偏斜 ~3e-4 rad，对稳定性 RMS 测试
      的影响 < 1%，已在容差内）；
    - 左大腿竖直、右大腿前倾 10°、右小腿前倾 20°：
      膝角右 = 180° − (20°−10°) = 170°（∠(髋−膝, 踝−膝) = 180°−小腿相对大腿转角），
      膝角左 = 180° → 膝不对称 = 10°；
      髋屈曲右 = 180° − ∠(躯干, 右大腿) = 14.036°+10°，左 = 14.036° → 髋不对称 = 10°；
    - 小腿长度以 L(t) = 0.45 − A·sin(2πt/1.2) 变化（方向不变！），使踝竖直
      振幅恰为 0.05 m 且膝角严格恒定——左 A=0.05，右 A=0.05/cos20°；
    - 躯干 = (0.2, 0, 0.8) 常量 → 前倾角 atan(0.25) ≈ 14.0362°；
    - 腕 = 骨盆 + (±0.3·sin(2πt/1.2), ±0.2, 0.35) → 相对骨盆行进轴峰峰值 0.6 m
      （12 s 恰含 10 个完整周期，正弦取到 ±1 的采样点）。
    """
    n_frames = int(round(duration_s * fps)) + 1
    t = np.arange(n_frames) / fps
    omega = 2.0 * np.pi / STRIDE_TIME_S

    pelvis = np.column_stack([speed_m_s * t, sway_m * np.sin(omega * t), np.ones(n_frames)])

    def at(offset):
        return pelvis + np.asarray(offset, dtype=float)

    s10, c10 = np.sin(np.radians(10.0)), np.cos(np.radians(10.0))
    s20, c20 = np.sin(np.radians(20.0)), np.cos(np.radians(20.0))
    lift_phase = np.sin(omega * t)[:, None]

    left_hip = at((0.0, HIP_WIDTH_M / 2, 0.0))
    right_hip = at((0.0, -HIP_WIDTH_M / 2, 0.0))
    left_knee = left_hip + np.asarray((0.0, 0.0, -0.45))
    right_knee = right_hip + 0.45 * np.asarray((s10, 0.0, -c10))
    # 小腿长度振荡（方向固定）→ 踝竖直振幅精确 0.05 m，膝角严格恒定。
    left_shank_len = 0.45 - FOOT_LIFT_M * lift_phase
    right_shank_len = 0.45 - (FOOT_LIFT_M / c20) * lift_phase
    left_ankle = left_knee + left_shank_len * np.asarray((0.0, 0.0, -1.0))
    right_ankle = right_knee + right_shank_len * np.asarray((s20, 0.0, -c20))

    trunk = np.asarray((0.2, 0.0, 0.8))
    left_shoulder = at((0.2, 0.2, 0.8))
    right_shoulder = at((0.2, -0.2, 0.8))
    swing_phase = np.sin(omega * t)[:, None]
    left_wrist = pelvis + np.column_stack([0.3 * swing_phase[:, 0], np.full(n_frames, 0.25), np.full(n_frames, 0.35)])
    right_wrist = pelvis + np.column_stack([-0.3 * swing_phase[:, 0], np.full(n_frames, -0.25), np.full(n_frames, 0.35)])

    joints = {
        "pelvis": pelvis,
        "left_hip": left_hip,
        "right_hip": right_hip,
        "left_knee": left_knee,
        "right_knee": right_knee,
        "left_ankle": left_ankle,
        "right_ankle": right_ankle,
        "spine": pelvis + 0.3 * trunk,
        "neck": pelvis + 0.8 * trunk,
        "nose": pelvis + 0.9 * trunk + np.asarray((0.05, 0.0, 0.05)),
        "head": pelvis + 0.9 * trunk,
        "left_shoulder": left_shoulder,
        "right_shoulder": right_shoulder,
        "left_elbow": left_shoulder + np.asarray((0.0, 0.1, -0.25)),
        "right_elbow": right_shoulder + np.asarray((0.0, -0.1, -0.25)),
        "left_wrist": left_wrist,
        "right_wrist": right_wrist,
    }
    time_s = t
    return Trajectory(
        time_s=time_s,
        joints=joints,
        source="synthetic",
        world_grounded=world_grounded,
        up_axis=2,
        participant=participant,
        view=view,
    )


def make_oscillating_ankle_walk(
    duration_s: float = DURATION_S,
    fps: float = FPS,
    speed_m_s: float = SPEED_M_S,
) -> Trajectory:
    """为解析式事件检测器构造的轨迹：踝在行进轴上相对骨盆正弦摆动。

    推导：左/右踝相对骨盆前向位移 = 0.3·sin(2πt/1.2 + π) / 0.3·sin(2πt/1.2)。
    前向极值（HS）右 = 0.3+1.2k、左 = 0.9+1.2k；其后局部极小（TO）各滞后 0.6 s。
    正弦周期恰为 1.2 s、30 Hz 采样下极值落在整帧上（0.3 s = 9 帧），
    detrend 对整周期正弦的斜率修正 ~5e-3 m/s，峰值帧不偏移（< 1 帧）。
    """
    n_frames = int(round(duration_s * fps)) + 1
    t = np.arange(n_frames) / fps
    omega = 2.0 * np.pi / STRIDE_TIME_S
    pelvis = np.column_stack([speed_m_s * t, np.zeros(n_frames), np.ones(n_frames)])

    def leg(side_y: float, phase: float) -> dict:
        hip = pelvis + np.asarray((0.0, side_y, 0.0))
        ankle = pelvis + np.column_stack([
            0.3 * np.sin(omega * t + phase),
            np.full(n_frames, side_y),
            np.full(n_frames, -0.9),
        ])
        knee = (hip + ankle) / 2.0
        return {"hip": hip, "knee": knee, "ankle": ankle}

    left = leg(0.09, np.pi)
    right = leg(-0.09, 0.0)
    joints = {
        "pelvis": pelvis,
        "left_hip": left["hip"], "right_hip": right["hip"],
        "left_knee": left["knee"], "right_knee": right["knee"],
        "left_ankle": left["ankle"], "right_ankle": right["ankle"],
    }
    return Trajectory(
        time_s=t,
        joints=joints,
        source="synthetic",
        world_grounded=True,
        up_axis=2,
        participant="SYN02",
        view="synthetic",
    )
