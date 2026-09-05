from __future__ import annotations

from careshield_contracts import GaitParameterValue


PARAMETERS = {
    "cadence_spm": ("步频", "temporal", "steps/min"),
    "step_time_s": ("平均步时", "temporal", "s"),
    "stride_time_s": ("平均跨步时间", "temporal", "s"),
    "stance_time_s": ("平均支撑时间", "temporal", "s"),
    "swing_time_s": ("平均摆动时间", "temporal", "s"),
    "double_support_time_s": ("平均双支撑时间", "temporal", "s"),
    "step_length_m": ("估计步长", "spatial", "m"),
    "gait_speed_m_s": ("估计步速", "spatial", "m/s"),
    "step_width_m": ("估计步宽", "spatial", "m"),
    "arm_swing_amplitude_m": ("摆臂幅度", "spatial", "m"),
    "left_foot_clearance_m": ("左足清障高度", "spatial", "m"),
    "right_foot_clearance_m": ("右足清障高度", "spatial", "m"),
    "step_time_sd_s": ("步时标准差", "variability", "s"),
    "stride_time_sd_s": ("跨步时间标准差", "variability", "s"),
    "step_time_cv_percent": ("步时变异系数", "variability", "%"),
    "stride_time_cv_percent": ("跨步时间变异系数", "variability", "%"),
    "step_length_cv_percent": ("步长变异系数", "variability", "%"),
    "step_width_cv_percent": ("步宽变异系数", "variability", "%"),
    "step_time_symmetry_percent": ("左右步时对称指数", "variability", "%"),
    "trunk_lean_deg": ("躯干倾斜", "posture", "degree"),
    "hip_asymmetry_deg": ("髋关节不对称", "posture", "degree"),
    "knee_asymmetry_deg": ("膝关节不对称", "posture", "degree"),
    "hip_knee_asymmetry_deg": ("髋膝综合不对称", "posture", "degree"),
    "ecom_lateral_rms_m": ("eCOM 横向 RMS", "stability", "m"),
    "xcom_lateral_rms_m": ("XCoM 横向 RMS", "stability", "m"),
    "emos_min_m": ("最小估计稳定裕度", "stability", "m"),
    "emos_mean_m": ("平均估计稳定裕度", "stability", "m"),
    "emos_normalized_by_hip_width": ("髋宽归一化 eMOS", "stability", "ratio"),
}


def map_parameters(values: dict) -> list[GaitParameterValue]:
    return [
        GaitParameterValue(
            name=name,
            display_name=display_name,
            category=category,
            value=float(values[name]) if isinstance(values.get(name), (int, float)) else None,
            unit=unit,
            available=isinstance(values.get(name), (int, float)),
            unavailable_reason=(
                None
                if isinstance(values.get(name), (int, float))
                else "有效步态事件不足，当前参数无法计算"
            ),
        )
        for name, (display_name, category, unit) in PARAMETERS.items()
    ]


GAITKIT_PARAMETER_NAMES = (
    "cadence_spm", "step_time_s", "stride_time_s", "stance_time_s",
    "swing_time_s", "double_support_time_s", "step_length_m", "gait_speed_m_s",
    "step_width_m", "arm_swing_amplitude_m", "foot_lift_height_m",
    "step_time_sd_s", "stride_time_sd_s", "step_time_cv_percent",
    "stride_time_cv_percent", "step_length_cv_percent", "step_width_cv_percent",
    "step_time_symmetry_index_percent", "trunk_stoop_angle_deg",
    "hip_angle_asymmetry_deg", "knee_angle_asymmetry_deg",
    "hip_knee_asymmetry_deg", "estimated_com_ml_sway_rms_m",
    "extrapolated_com_ml_sway_rms_m", "estimated_margin_of_stability_min_m",
    "estimated_margin_of_stability_mean_m",
    "estimated_margin_of_stability_min_hip_width_normalized",
    "estimated_margin_of_stability_mean_hip_width_normalized",
)

_POSTURE_PARAMETERS = {
    "trunk_stoop_angle_deg",
    "hip_angle_asymmetry_deg",
    "knee_angle_asymmetry_deg",
    "hip_knee_asymmetry_deg",
}
_STABILITY_PARAMETERS = {
    name for name in GAITKIT_PARAMETER_NAMES
    if name.startswith("estimated_") or name.startswith("extrapolated_")
}
_TEMPORAL_PARAMETERS = set(GAITKIT_PARAMETER_NAMES[:6])
_VARIABILITY_PARAMETERS = {
    name for name in GAITKIT_PARAMETER_NAMES
    if "_sd_" in name or "_cv_" in name or name == "step_time_symmetry_index_percent"
}


def _gaitkit_category(name: str) -> str:
    if name in _TEMPORAL_PARAMETERS:
        return "temporal"
    if name in _VARIABILITY_PARAMETERS:
        return "variability"
    if name in _POSTURE_PARAMETERS:
        return "posture"
    if name in _STABILITY_PARAMETERS:
        return "stability"
    return "spatial"


def map_gaitkit_parameters(values: dict, manifest: list[dict]) -> list[GaitParameterValue]:
    """Map the versioned GaitKit manifest without inventing legacy fields."""
    manifest_by_name = {
        str(item.get("name")): item
        for item in manifest
        if isinstance(item, dict) and item.get("name")
    }
    if set(values) != set(GAITKIT_PARAMETER_NAMES):
        raise ValueError("GaitKit result does not contain the canonical 28 parameters")
    if set(manifest_by_name) != set(GAITKIT_PARAMETER_NAMES):
        raise ValueError("GaitKit metric manifest does not match the canonical parameters")

    result: list[GaitParameterValue] = []
    for name in GAITKIT_PARAMETER_NAMES:
        raw_value = values[name]
        available = isinstance(raw_value, (int, float)) and not isinstance(raw_value, bool)
        item = manifest_by_name[name]
        result.append(
            GaitParameterValue(
                name=name,
                display_name=str(item.get("display_name", name))[:120],
                category=_gaitkit_category(name),
                value=float(raw_value) if available else None,
                unit=str(item.get("unit", ""))[:32],
                available=available,
                unavailable_reason=(
                    None if available else "当前步态事件不足，无法计算该参数"
                ),
            )
        )
    return result
