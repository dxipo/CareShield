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


def test_alert_remains_visible_for_minimum_duration_after_detector_recovers() -> None:
    now = [100.0]
    latch = FallAlertLatch(15.0, clock=lambda: now[0])

    latch.update(FallState.FALLEN)
    now[0] += 5.0
    latch.update(FallState.NORMAL)
    assert latch.active is True

    now[0] += 10.0
    latch.update(FallState.NORMAL)
    assert latch.active is False


def test_operator_can_acknowledge_before_minimum_duration() -> None:
    latch = FallAlertLatch(15.0, clock=lambda: 100.0)
    latch.update(FallState.FALLEN)
    latch.acknowledge()

    assert latch.active is False
    assert latch.acknowledged is True
