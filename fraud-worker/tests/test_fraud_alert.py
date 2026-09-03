from app.detection.alert import FraudAlertLatch


def test_acknowledgement_silences_current_fraud_incident() -> None:
    alert = FraudAlertLatch()
    alert.update(True)
    assert alert.active is True

    alert.acknowledge()
    alert.update(True)
    assert alert.active is False
    assert alert.acknowledged is True


def test_normal_state_rearms_next_fraud_incident() -> None:
    alert = FraudAlertLatch()
    alert.update(True)
    alert.acknowledge()
    alert.update(False)
    alert.update(True)

    assert alert.active is True
    assert alert.acknowledged is False
