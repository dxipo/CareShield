import httpx

from app.llm.ollama import OllamaAdjudicator


def test_qwen_adjudication_disables_thinking_and_parses_json() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "qwen3:4b"}]})
        payload = __import__("json").loads(request.content)
        assert payload["think"] is False
        return httpx.Response(
            200,
            json={
                "response": (
                    '{"suspicious":true,"confidence":0.91,'
                    '"reason":"存在转账和验证码要求"}'
                )
            },
        )

    client = OllamaAdjudicator("http://ollama.test", "qwen3:4b", 1)
    client._client.close()
    client._client = httpx.Client(
        base_url="http://ollama.test",
        transport=httpx.MockTransport(handler),
    )

    judgement = client.judge("请转账并告诉我验证码")

    assert judgement is not None
    assert judgement.suspicious is True
    assert judgement.confidence == 0.91
    assert len(requests) == 2
