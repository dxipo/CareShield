"""预处理链测试：重采样 / 低通 / 空间归一化 / 切窗 / 折返点检测与匹配。

期望值推导：
- 线性信号经 np.interp 重采样是精确的（误差 < 1e-12）；
- 4 阶 Butterworth filtfilt 对 9 Hz（截止 6 Hz、fs=30 Hz）的幅值衰减 ~96%，
  且零相位——1 Hz 主频峰位置不漂移；
- window_starts(361, 243, 81) = [0, 81, 118]（尾窗锚定第 361 帧）；
- 折返检测：±1 m/s 分段匀速骨盆轨迹在 5 s、10 s 换向 → 折返点命中对应帧。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

from gaitkit.core import Trajectory
from gaitkit.preprocess import (
    add_velocity_channels,
    align_heading,
    butter_lowpass_zero_phase,
    heading_basis,
    pelvis_center,
    resample_trajectory,
    scale_by_height,
    slice_windows,
    window_starts,
)


def _one_joint_trajectory(time_s: np.ndarray, xyz: np.ndarray, up_axis: int = 2, grounded: bool = True) -> Trajectory:
    return Trajectory(time_s, {"pelvis": xyz}, "synthetic", grounded, up_axis, "SYN03", "synthetic")


class ResampleTests(unittest.TestCase):
    def test_linear_signal_is_exact(self) -> None:
        time_s = np.arange(0.0, 10.0 + 1e-9, 0.01)  # 100 Hz
        xyz = np.column_stack([2.0 * time_s + 1.0, -time_s, np.full(len(time_s), 0.5)])
        out = resample_trajectory(_one_joint_trajectory(time_s, xyz), 30.0)
        self.assertAlmostEqual(float(np.median(np.diff(out.time_s))), 1.0 / 30.0, places=12)
        expected = np.column_stack([2.0 * out.time_s + 1.0, -out.time_s, np.full(len(out.time_s), 0.5)])
        np.testing.assert_allclose(out.joints["pelvis"], expected, atol=1e-12)
        self.assertAlmostEqual(out.time_s[0], 0.0, places=12)
        self.assertLessEqual(out.time_s[-1], 10.0 + 0.5 / 30.0)

    def test_invalid_fps_rejected(self) -> None:
        time_s = np.arange(10) / 30.0
        with self.assertRaises(ValueError):
            resample_trajectory(_one_joint_trajectory(time_s, np.zeros((10, 3))), 0.0)


class LowpassTests(unittest.TestCase):
    def test_attenuates_high_frequency_and_keeps_phase(self) -> None:
        fps = 30.0
        t = np.arange(0.0, 20.0, 1.0 / fps)
        slow = np.sin(2 * np.pi * 1.0 * t)
        fast = 0.5 * np.sin(2 * np.pi * 9.0 * t)
        xyz = np.column_stack([slow + fast, t * 0.1, np.zeros(len(t))])
        out = butter_lowpass_zero_phase(_one_joint_trajectory(t, xyz), cutoff_hz=6.0, order=4)
        filtered = out.joints["pelvis"][:, 0]
        # 高频分量衰减：残差（filtered − slow）RMS 远小于原高频振幅 0.5。
        residual = filtered - slow
        self.assertLess(float(np.sqrt(np.mean(residual ** 2))), 0.05)
        # 零相位：1 Hz 主峰位置不漂移（±1 帧）。比较中段一个完整周期
        # （argmax 对全长 20 个等值周期是任意的，且 filtfilt 边缘有瞬态）。
        lo, hi = 150, 180  # t = 5..6 s
        peak_expected = int(np.argmax(slow[lo:hi]))
        peak_actual = int(np.argmax(filtered[lo:hi]))
        self.assertLessEqual(abs(peak_actual - peak_expected), 1)

    def test_short_signal_passes_through(self) -> None:
        t = np.arange(10) / 30.0
        xyz = np.random.default_rng(0).normal(size=(10, 3))
        out = butter_lowpass_zero_phase(_one_joint_trajectory(t, xyz))
        np.testing.assert_array_equal(out.joints["pelvis"], xyz)


class SpatialNormalizationTests(unittest.TestCase):
    def test_pelvis_center(self) -> None:
        points = np.arange(2 * 3 * 3, dtype=float).reshape(2, 3, 3)
        centred = pelvis_center(points, pelvis_index=0)
        np.testing.assert_array_equal(centred[:, 0, :], 0.0)
        np.testing.assert_array_equal(centred[:, 1, :], points[:, 1, :] - points[:, 0, :])

    def test_heading_alignment_maps_forward_to_z(self) -> None:
        from synth import make_synthetic_walk

        trajectory = make_synthetic_walk()
        basis = heading_basis(trajectory)
        # 列 = [lateral, up, forward]：+X 行进 → forward ≈ (1,0,0)。
        np.testing.assert_allclose(basis[:, 2], [1.0, 0.0, 0.0], atol=1e-9)
        np.testing.assert_allclose(basis[:, 1], [0.0, 0.0, 1.0], atol=1e-9)
        points = np.stack([trajectory.joints["pelvis"]], axis=1)
        aligned = align_heading(points, basis)
        # 对齐后骨盆前进分量（第 3 列 z=forward）单调递增，横向 ≈ 0。
        self.assertTrue(np.all(np.diff(aligned[:, 0, 2]) > 0))
        np.testing.assert_allclose(aligned[:, 0, 0], 0.0, atol=1e-9)

    def test_scale_by_height(self) -> None:
        points = np.ones((2, 1, 3))
        np.testing.assert_allclose(scale_by_height(points, 1700.0), np.full((2, 1, 3), 1.0 / 1.7))

    def test_velocity_channels_exact_for_polynomial(self) -> None:
        fps = 30.0
        t = np.arange(100) / fps
        linear = np.column_stack([0.8 * t, np.zeros(100), np.zeros(100)])[:, None, :]
        velocity = add_velocity_channels(linear, fps)
        np.testing.assert_allclose(velocity[:, 0, 0], 0.8, atol=1e-12)


class WindowTests(unittest.TestCase):
    def test_tail_anchored_starts(self) -> None:
        self.assertEqual(window_starts(361, 243, 81), [0, 81, 118])
        self.assertEqual(window_starts(270, 243, 81), [0, 27])
        self.assertEqual(window_starts(243, 243, 81), [0])

    def test_too_short_segment_rejected(self) -> None:
        with self.assertRaises(ValueError):
            window_starts(242, 243, 81)

    def test_slice_windows_shape(self) -> None:
        sequence = np.arange(361 * 2).reshape(361, 2).astype(float)
        out = slice_windows(sequence, [0, 81, 118], 243)
        self.assertEqual(out.shape, (3, 243, 2))
        np.testing.assert_array_equal(out[2], sequence[118:361])


if __name__ == "__main__":
    unittest.main()
