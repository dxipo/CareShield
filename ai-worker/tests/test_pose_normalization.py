from types import SimpleNamespace

from app.fall_detection.pose_estimator import UltralyticsPoseEstimator


class FakeTensor:
    def __init__(self, value):
        self.value = value

    def detach(self):
        return self

    def cpu(self):
        return self

    def tolist(self):
        return self.value


def test_ultralytics_output_is_normalized_to_careshield_pose_schema() -> None:
    points = [[index / 20, index / 40] for index in range(17)]
    result = SimpleNamespace(
        boxes=SimpleNamespace(
            xyxy=FakeTensor([[100, 50, 500, 950]]),
            conf=FakeTensor([0.92]),
        ),
        keypoints=SimpleNamespace(
            xyn=FakeTensor([points]),
            conf=FakeTensor([[0.8] * 17]),
        ),
    )

    persons = UltralyticsPoseEstimator._normalize(result, width=1000, height=1000)

    assert len(persons) == 1
    assert persons[0].person_id == "person-1"
    assert persons[0].bbox.x1 == 0.1
    assert persons[0].bbox.y2 == 0.95
    assert len(persons[0].keypoints) == 17
    assert persons[0].keypoint("left_hip").confidence == 0.8
