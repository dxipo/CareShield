from app.fall_detection.detector import FallState
from app.fall_detection.stgcn_decision import STGCNDecisionEngine


def test_stgcn_score_requires_multiple_windows_before_fallen() -> None:
    engine = STGCNDecisionEngine(0.6, 0.8, confirmation_windows=3, recovery_windows=2)

    assert engine.update(0.9).state == FallState.SUSPECTED_FALL
    assert engine.update(0.9).state == FallState.SUSPECTED_FALL
    decision = engine.update(0.9)

    assert decision.state == FallState.FALLEN
    assert decision.state_changed is True


def test_fallen_state_recovers_only_after_persistence() -> None:
    engine = STGCNDecisionEngine(0.6, 0.8, confirmation_windows=1, recovery_windows=2)
    assert engine.update(0.9).state == FallState.FALLEN
    assert engine.update(0.1).state == FallState.RECOVERING
    assert engine.update(0.1).state == FallState.NORMAL


def test_score_is_bounded_and_thresholds_are_validated() -> None:
    engine = STGCNDecisionEngine()
    assert engine.update(2.0).score == 1.0
