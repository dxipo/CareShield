from dataclasses import replace
from importlib import import_module

import pytest
from fastapi import HTTPException


def test_internal_control_credentials_are_required(monkeypatch) -> None:
    main = import_module("app.main")
    monkeypatch.setattr(
        main,
        "settings",
        replace(main.settings, shared_token="test-internal-token"),
    )

    main.require_internal_credentials("Bearer test-internal-token")
    with pytest.raises(HTTPException) as error:
        main.require_internal_credentials("Bearer wrong-token")
    assert error.value.status_code == 401
    assert "wrong-token" not in str(error.value.detail)
    assert "test-internal-token" not in str(error.value.detail)
