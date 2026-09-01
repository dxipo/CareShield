import json
import tempfile
import unittest
from pathlib import Path

from app.risk_classification import classify_risk, load_risk_thresholds


class RiskClassificationTests(unittest.TestCase):
    def test_risk_level_boundaries(self) -> None:
        thresholds = {"low_medium": 0.02, "medium_high": 0.05}
        self.assertEqual(classify_risk(0.019, thresholds), "low")
        self.assertEqual(classify_risk(0.02, thresholds), "medium")
        self.assertEqual(classify_risk(0.049, thresholds), "medium")
        self.assertEqual(classify_risk(0.05, thresholds), "high")

    def test_threshold_configuration_is_validated(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "thresholds.json"
            path.write_text(
                json.dumps({"thresholds": {"low_medium": 0.05, "medium_high": 0.02}}),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "ordered"):
                load_risk_thresholds(path)


if __name__ == "__main__":
    unittest.main()
