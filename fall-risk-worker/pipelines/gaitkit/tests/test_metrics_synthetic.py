"""合成数据指标测试：28 项参数在"已知真值步行"上的数值断言。

期望值推导（详见 tests/synth.py 注释）：
- 步频 = 60/0.6 = 100 spm；步时 0.6 s；跨步 1.2 s；支撑 0.72 s；摆动 0.48 s；
- 双支撑 = 2×0.12 = 0.24 s；步长 = 1.0×0.6 = 0.6 m；步速 = 0.6/0.6 = 1.0 m/s；
- 步宽 = 0.18 m；摆臂 = 0.6 m；抬脚 = 0.05 m；躯干前倾 = atan(0.25) ≈ 14.0362°；
- 髋/膝/髋膝不对称 = 10°；所有 SD/CV/对称指数 = 0；
- 零摆动：eCOM/XCoM RMS = 0，eMOS min/mean = 0.09 m，归一化 = 0.09/0.18 = 0.5；
- 摆动 0.02 m：eCOM RMS = 0.02/√2 ≈ 0.014142；XCoM RMS =
  0.02×sqrt(0.5×(1+Ω²/ω²)) ≈ 0.026515（Ω=2π/1.2，ω²=9.81/0.9=10.9）。
  Savitzky-Golay 平滑对 1/1.2 Hz 正弦的幅值衰减 ~0.12%、np.gradient 对速度的
  衰减 ~0.5%、PCA 行进轴微偏引入的线性趋势 ~0.3%，合计容差取 1.5%。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

from gaitkit.metrics import (
    CANONICAL_METRICS,
    CORE8,
    METRIC_REGISTRY,
    RISK_EXT20,
    XSENS_COMPARABLE21,
    compute_all,
)
from synth import (
    ASYMMETRY_DEG,
    DS_COMPONENT_S,
    FOOT_LIFT_M,
    HIP_WIDTH_M,
    STANCE_TIME_S,
    STEP_TIME_S,
    STRIDE_TIME_S,
    SWING_TIME_S,
    TRUNK_TILT_DEG,
    make_explicit_events,
    make_oscillating_ankle_walk,
    make_synthetic_walk,
)

TEMPORAL_METRICS = (
    "cadence_spm", "step_time_s", "stride_time_s", "stance_time_s", "swing_time_s",
    "double_support_time_s", "step_time_sd_s", "stride_time_sd_s",
    "step_time_cv_percent", "stride_time_cv_percent", "step_time_symmetry_index_percent",
)


class RegistryCompletenessTests(unittest.TestCase):
    def test_registry_has_28_metrics_in_canonical_order(self) -> None:
        self.assertEqual(len(METRIC_REGISTRY), 28)
        self.assertEqual(tuple(m.name for m in METRIC_REGISTRY), CANONICAL_METRICS)
        self.assertEqual(len(CORE8), 8)
        self.assertEqual(len(RISK_EXT20), 20)
        self.assertEqual(len(XSENS_COMPARABLE21), 21)
        for metric in METRIC_REGISTRY:
            self.assertTrue(metric.formula.strip(), metric.name)
            self.assertTrue(metric.cn_name.strip(), metric.name)
            self.assertTrue(metric.unit.strip(), metric.name)
            self.assertIn(metric.tier, ("core", "extended"))
            if metric.tier == "core":
                self.assertIn(metric.name, CORE8)
            else:
                self.assertIn(metric.name, RISK_EXT20)


class TemporalMetricTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.metrics = compute_all(make_synthetic_walk(), make_explicit_events())

    def test_cadence_step_stride(self) -> None:
        self.assertAlmostEqual(self.metrics["cadence_spm"], 100.0, places=9)
        self.assertAlmostEqual(self.metrics["step_time_s"], STEP_TIME_S, places=9)
        self.assertAlmostEqual(self.metrics["stride_time_s"], STRIDE_TIME_S, places=9)

    def test_phase_times(self) -> None:
        self.assertAlmostEqual(self.metrics["stance_time_s"], STANCE_TIME_S, places=9)
        self.assertAlmostEqual(self.metrics["swing_time_s"], SWING_TIME_S, places=9)
        self.assertAlmostEqual(self.metrics["double_support_time_s"], 2.0 * DS_COMPONENT_S, places=9)

    def test_zero_variability_and_symmetry(self) -> None:
        for name in ("step_time_sd_s", "stride_time_sd_s", "step_time_cv_percent",
                     "stride_time_cv_percent", "step_time_symmetry_index_percent",
                     "step_length_cv_percent", "step_width_cv_percent"):
            self.assertAlmostEqual(self.metrics[name], 0.0, places=9, msg=name)


class SpatialMetricTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.metrics = compute_all(make_synthetic_walk(), make_explicit_events())

    def test_step_length_and_speed(self) -> None:
        self.assertAlmostEqual(self.metrics["step_length_m"], 0.6, places=9)
        self.assertAlmostEqual(self.metrics["gait_speed_m_s"], 1.0, places=9)

    def test_step_width_arm_swing_foot_lift(self) -> None:
        self.assertAlmostEqual(self.metrics["step_width_m"], HIP_WIDTH_M, places=9)
        self.assertAlmostEqual(self.metrics["arm_swing_amplitude_m"], 0.6, places=9)
        self.assertAlmostEqual(self.metrics["foot_lift_height_m"], FOOT_LIFT_M, places=9)

    def test_trunk_stoop(self) -> None:
        self.assertAlmostEqual(self.metrics["trunk_stoop_angle_deg"], TRUNK_TILT_DEG, places=6)

    def test_joint_angle_asymmetry(self) -> None:
        # 推导：右大腿前倾 10° → 髋屈曲差 = 10°；右小腿相对大腿再转 10° → 膝角差 = 10°。
        self.assertAlmostEqual(self.metrics["knee_angle_asymmetry_deg"], ASYMMETRY_DEG, places=6)
        self.assertAlmostEqual(self.metrics["hip_angle_asymmetry_deg"], ASYMMETRY_DEG, places=6)
        self.assertAlmostEqual(self.metrics["hip_knee_asymmetry_deg"], ASYMMETRY_DEG, places=6)


class StabilityMetricTests(unittest.TestCase):
    def test_zero_sway_exact_values(self) -> None:
        metrics = compute_all(make_synthetic_walk(sway_m=0.0), make_explicit_events())
        self.assertAlmostEqual(metrics["estimated_com_ml_sway_rms_m"], 0.0, places=12)
        self.assertAlmostEqual(metrics["extrapolated_com_ml_sway_rms_m"], 0.0, places=12)
        self.assertAlmostEqual(metrics["estimated_margin_of_stability_min_m"], 0.09, places=9)
        self.assertAlmostEqual(metrics["estimated_margin_of_stability_mean_m"], 0.09, places=9)
        self.assertAlmostEqual(
            metrics["estimated_margin_of_stability_min_hip_width_normalized"], 0.09 / HIP_WIDTH_M, places=9
        )
        self.assertAlmostEqual(
            metrics["estimated_margin_of_stability_mean_hip_width_normalized"], 0.09 / HIP_WIDTH_M, places=9
        )

    def test_lateral_sway_rms_matches_inverted_pendulum_model(self) -> None:
        sway = 0.02
        metrics = compute_all(make_synthetic_walk(sway_m=sway), make_explicit_events())
        omega = 2.0 * np.pi / STRIDE_TIME_S
        pendulum_omega_sq = 9.81 / 0.9  # 腿长 0.9 m
        expected_ecom = sway / np.sqrt(2.0)
        expected_xcom = sway * np.sqrt(0.5 * (1.0 + omega ** 2 / pendulum_omega_sq))
        self.assertAlmostEqual(metrics["estimated_com_ml_sway_rms_m"], expected_ecom, delta=expected_ecom * 0.015)
        self.assertAlmostEqual(
            metrics["extrapolated_com_ml_sway_rms_m"], expected_xcom, delta=expected_xcom * 0.015
        )
        # 摆动幅度 (~0.038 m) 小于踝边界 0.09 m：裕度仍为正且小于静止情形。
        self.assertGreater(metrics["estimated_margin_of_stability_min_m"], 0.0)
        self.assertLess(metrics["estimated_margin_of_stability_min_m"], 0.09)


class GroundingGateTests(unittest.TestCase):
    def test_non_grounded_trajectory_yields_nan_spatial_but_valid_temporal(self) -> None:
        trajectory = make_synthetic_walk(world_grounded=False)
        metrics = compute_all(trajectory, make_explicit_events())
        grounded = [m.name for m in METRIC_REGISTRY if m.requires_grounding]
        temporal = [m.name for m in METRIC_REGISTRY if not m.requires_grounding]
        self.assertEqual(len(grounded), 17)
        self.assertEqual(len(temporal), 11)
        for name in grounded:
            self.assertTrue(np.isnan(metrics[name]), name)
        for name in temporal:
            self.assertTrue(np.isfinite(metrics[name]), name)
        self.assertAlmostEqual(metrics["cadence_spm"], 100.0, places=9)
        self.assertEqual(set(temporal), set(TEMPORAL_METRICS))


class AnalyticDetectorIntegrationTests(unittest.TestCase):
    """事件检测（解析式）+ 指标计算的端到端数值检查。"""

    def test_detected_events_and_metrics(self) -> None:
        from gaitkit.events import AnalyticEventDetector

        trajectory = make_oscillating_ankle_walk()
        events = AnalyticEventDetector().detect(trajectory, 1700.0)
        # 推导：右 HS 于 0.3+1.2k（10 次），左 HS 于 0.9+1.2k（10 次），整帧命中。
        self.assertEqual(len(events.right_down), 10)
        self.assertEqual(len(events.left_down), 10)
        np.testing.assert_allclose(events.right_down, 0.3 + 1.2 * np.arange(10), atol=1e-9)
        np.testing.assert_allclose(events.left_down, 0.9 + 1.2 * np.arange(10), atol=1e-9)
        metrics = compute_all(trajectory, events)
        self.assertAlmostEqual(metrics["cadence_spm"], 100.0, places=9)
        self.assertAlmostEqual(metrics["step_length_m"], 0.6, places=9)

    def test_analytic_detector_rejects_non_grounded(self) -> None:
        from gaitkit.events import AnalyticEventDetector

        trajectory = make_oscillating_ankle_walk()
        ungrounded = type(trajectory)(
            trajectory.time_s, trajectory.joints, trajectory.source, False, 2, "SYN02", "synthetic"
        )
        with self.assertRaises(ValueError):
            AnalyticEventDetector().detect(ungrounded, 1700.0)


class VisionMDDetectorAvailabilityTests(unittest.TestCase):
    def test_available_flag_and_error_message(self) -> None:
        from gaitkit.events import VisionMDEventDetector

        detector = VisionMDEventDetector()
        available, hint = detector.available()
        if not available:
            self.assertIn("gait_transformer", hint)
            with self.assertRaises(RuntimeError) as ctx:
                detector.detect(make_synthetic_walk(), 1700.0)
            self.assertIn("gait_transformer", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
