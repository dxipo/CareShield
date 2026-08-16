"""Development-only CLI to publish one explicitly simulated pipeline test."""

import asyncio

from app.core.config import load_worker_settings
from app.publisher.result_publisher import ResultPublisher
from app.services.pipeline_test_service import PipelineTestService


async def main() -> None:
    settings = load_worker_settings()
    if not settings.development:
        raise SystemExit("pipeline test publishing is disabled outside development")
    publisher = ResultPublisher(settings)
    try:
        result = await PipelineTestService(publisher).publish()
        print(f"pipeline_test published: {result.result_id}")
    finally:
        await publisher.close()


if __name__ == "__main__":
    asyncio.run(main())
