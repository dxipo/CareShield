from datetime import datetime, timezone
from uuid import uuid4

from careshield_contracts import AlgorithmResult, AlgorithmTask

from app.publisher.result_publisher import ResultPublisher


class PipelineTestService:
    def __init__(self, publisher: ResultPublisher) -> None:
        self._publisher = publisher

    async def publish(self) -> AlgorithmResult:
        result = self.build_result()
        await self._publisher.publish(result)
        return result

    @staticmethod
    def build_result() -> AlgorithmResult:
        return AlgorithmResult(
            result_id=uuid4(),
            task=AlgorithmTask.PIPELINE_TEST,
            model_id="pipeline-tester",
            model_version="1.0",
            device_id=None,
            source_timestamp=None,
            result_timestamp=datetime.now(timezone.utc),
            label="pipeline_ok",
            score=None,
            level=None,
            latency_ms=None,
            metadata={"message": "CareShield realtime pipeline test"},
            simulated=True,
        )
