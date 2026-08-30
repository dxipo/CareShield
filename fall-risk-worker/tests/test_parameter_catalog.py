from app.services.parameter_catalog import PARAMETERS, map_parameters


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
