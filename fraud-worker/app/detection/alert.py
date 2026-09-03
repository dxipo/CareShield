class FraudAlertLatch:
    """Silence an acknowledged alert until the detector leaves its risk state."""

    def __init__(self) -> None:
        self.active = False
        self.acknowledged = False

    def update(self, detector_alert_active: bool) -> None:
        if not detector_alert_active:
            self.active = False
            self.acknowledged = False
            return
        self.active = not self.acknowledged

    def acknowledge(self) -> None:
        if self.active:
            self.active = False
            self.acknowledged = True
