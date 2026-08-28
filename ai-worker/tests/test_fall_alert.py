from app.fall_detection.alert import FallAlertLatch
from app.fall_detection.detector import FallState


def test_confirmed_fall_is_latched_across_missing_or_recovering_results() -> None:
    latch = FallAlertLatch()
    latch.update(FallState.FALLEN)
    latch.update(FallState.RECOVERING)

    assert latch.active is True
    assert latch.acknowledged is False


def test_acknowledgement_silences_current_incident_until_normal_reset() -> None:
    latch = FallAlertLatch()
    latch.update(FallState.FALLEN)
    latch.acknowledge()
    latch.update(FallState.FALLEN)

    assert latch.active is False
    assert latch.acknowledged is True

    latch.update(FallState.NORMAL)
    latch.update(FallState.FALLEN)
    assert latch.active is True
    assert latch.acknowledged is False
