from app.services.parameter_catalog import (
    GAITKIT_PARAMETER_NAMES,
    PARAMETERS,
    map_gaitkit_parameters,
    map_parameters,
)


def test_catalog_contains_exactly_28_real_parameters() -> None:
    values = {name: float(index) for index, name in enumerate(PARAMETERS)}
    result = map_parameters(values)
    assert len(result) == 28
    assert all(parameter.available for parameter in result)


def test_missing_parameter_remains_unavailable_instead_of_becoming_zero() -> None:
    result = map_parameters({})
    assert len(result) == 28
    assert all(parameter.value is None for parameter in result)
    assert all(not parameter.available for parameter in result)


def test_gaitkit_native_contract_maps_exactly_28_without_fabricating_legacy_fields() -> None:
    values = {name: float(index) for index, name in enumerate(GAITKIT_PARAMETER_NAMES)}
    values["foot_lift_height_m"] = None
    manifest = [
        {"name": name, "display_name": name, "unit": "m", "group": "test"}
        for name in GAITKIT_PARAMETER_NAMES
    ]

    result = map_gaitkit_parameters(values, manifest)

    assert len(result) == 28
    assert {item.name for item in result} == set(GAITKIT_PARAMETER_NAMES)
    assert "left_foot_clearance_m" not in {item.name for item in result}
    foot_lift = next(item for item in result if item.name == "foot_lift_height_m")
    assert foot_lift.available is False
    assert foot_lift.value is None
