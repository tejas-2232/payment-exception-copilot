from uuid import uuid4

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, LLMResult

from app.agent.metrics import ModelMetricsCallback
from app.api.main import app


def add_call(callback, input_tokens, output_tokens, cached=0):
    run_id = uuid4()
    callback.on_chat_model_start({}, [], run_id=run_id)
    chunk = ChatGenerationChunk(message=AIMessageChunk(content="", tool_call_chunks=[{"name": "get_case", "args": "{}", "id": "1", "index": 0}]))
    callback.on_llm_new_token("", chunk=chunk, run_id=run_id)
    usage = {"input_tokens": input_tokens, "output_tokens": output_tokens,
             "total_tokens": input_tokens + output_tokens, "input_token_details": {"cache_read": cached}}
    callback.on_llm_end(LLMResult(generations=[[ChatGeneration(message=AIMessage(content="", usage_metadata=usage))]]), run_id=run_id)


def test_accumulates_multiple_calls_and_cached_cost(monkeypatch):
    monkeypatch.setenv("OPENAI_MODEL", "fictional-model")
    monkeypatch.setenv("MODEL_PRICING_MODEL", "fictional-model")
    monkeypatch.setenv("MODEL_INPUT_PRICE_PER_MILLION_USD", "2")
    monkeypatch.setenv("MODEL_CACHED_INPUT_PRICE_PER_MILLION_USD", "0.5")
    monkeypatch.setenv("MODEL_OUTPUT_PRICE_PER_MILLION_USD", "8")
    callback = ModelMetricsCallback()
    add_call(callback, 1000, 100, 400)
    add_call(callback, 2000, 200, 600)
    result = callback.result(250)
    assert result.model_calls == 2
    assert result.first_model_output_ms is not None
    assert (result.input_tokens, result.output_tokens, result.cached_input_tokens) == (3000, 300, 1000)
    assert abs(result.estimated_cost_usd - 0.0069) < 1e-10


def test_unknown_usage_or_prices_do_not_report_zero(monkeypatch):
    monkeypatch.delenv("MODEL_PRICING_MODEL", raising=False)
    callback = ModelMetricsCallback()
    add_call(callback, 100, 10)
    assert callback.result(10).estimated_cost_usd is None
    missing = ModelMetricsCallback()
    run_id = uuid4()
    missing.on_chat_model_start({}, [], run_id=run_id)
    missing.on_llm_end(LLMResult(generations=[[ChatGeneration(message=AIMessage(content="ok"))]]), run_id=run_id)
    result = missing.result(10)
    assert result.input_tokens is None and result.estimated_cost_usd is None
    assert result.first_model_output_ms is None


def test_cached_usage_requires_cached_price_and_matching_model(monkeypatch):
    monkeypatch.setenv("OPENAI_MODEL", "model-a")
    monkeypatch.setenv("MODEL_PRICING_MODEL", "model-b")
    monkeypatch.setenv("MODEL_INPUT_PRICE_PER_MILLION_USD", "1")
    monkeypatch.setenv("MODEL_OUTPUT_PRICE_PER_MILLION_USD", "1")
    monkeypatch.delenv("MODEL_CACHED_INPUT_PRICE_PER_MILLION_USD", raising=False)
    callback = ModelMetricsCallback()
    add_call(callback, 20, 5, 10)
    assert callback.result(10).estimated_cost_usd is None
    monkeypatch.setenv("MODEL_PRICING_MODEL", "model-a")
    assert callback.result(10).estimated_cost_usd is None


def test_offline_investigation_reports_no_model_cost(monkeypatch):
    monkeypatch.delenv("INVESTIGATION_PROVIDER", raising=False)
    response = TestClient(app).post("/investigations", json={"case_id": "CASE-001"})
    assert response.status_code == 200
    metrics = response.json()["metrics"]
    assert metrics["model_calls"] == 0
    assert metrics["estimated_cost_usd"] == 0
    assert metrics["first_model_output_ms"] is None
    assert metrics["total_duration_ms"] >= 0


def test_streaming_chat_model_reports_first_output_and_usage(monkeypatch):
    import httpx
    from langchain_openai import ChatOpenAI

    monkeypatch.setenv("OPENAI_MODEL", "test-model")
    monkeypatch.setenv("MODEL_PRICING_MODEL", "test-model")
    monkeypatch.setenv("MODEL_INPUT_PRICE_PER_MILLION_USD", "2")
    monkeypatch.setenv("MODEL_OUTPUT_PRICE_PER_MILLION_USD", "8")
    monkeypatch.setenv("MODEL_CACHED_INPUT_PRICE_PER_MILLION_USD", "1")
    data = (
        'data: {"id":"chatcmpl-test","object":"chat.completion.chunk","created":1,"model":"test-model","choices":[{"index":0,"delta":{"role":"assistant","content":"Hello"},"finish_reason":null}]}\n\n'
        'data: {"id":"chatcmpl-test","object":"chat.completion.chunk","created":1,"model":"test-model","choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}\n\n'
        'data: {"id":"chatcmpl-test","object":"chat.completion.chunk","created":1,"model":"test-model","choices":[],"usage":{"prompt_tokens":100,"completion_tokens":10,"total_tokens":110,"prompt_tokens_details":{"cached_tokens":20}}}\n\n'
        'data: [DONE]\n\n'
    )
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, content=data, headers={"content-type": "text/event-stream"})))
    model = ChatOpenAI(model="test-model", api_key="not-a-real-key", http_client=client,
                       streaming=True, stream_usage=True, max_retries=0)
    callback = ModelMetricsCallback()
    result = model.invoke("hello", config={"callbacks": [callback]})
    assert result.content == "Hello"
    metrics = callback.result(100)
    assert metrics.first_model_output_ms is not None
    assert metrics.model_calls == 1
    assert (metrics.input_tokens, metrics.output_tokens, metrics.cached_input_tokens) == (100, 10, 20)
    assert abs(metrics.estimated_cost_usd - 0.00026) < 1e-10


def test_full_agent_workflow_with_streaming_tool_calls():
    import json
    import httpx
    from langchain_openai import ChatOpenAI
    from app.agent.langchain_agent import investigate_with_agent
    from app.api.main import load_cases

    actions = iter([
        ("get_case", {}),
        ("get_partner_profile", {}),
        ("search_partner_procedures", {"query": "missing beneficiary bank identifier"}),
        None,
    ])
    def reply(request):
        action = next(actions)
        if action:
            name, args = action
            delta = {"role": "assistant", "tool_calls": [{"index": 0, "id": f"call_{name}", "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}]}
            finish = "tool_calls"
        else:
            delta = {"role": "assistant", "content": json.dumps({"category": "missing_bank_identifier", "passage_ids": ["P-01-001"], "source_ids": ["payment.beneficiary_bank_identifier"]})}
            finish = "stop"
        chunks = [
            {"id": "test", "object": "chat.completion.chunk", "created": 1, "model": "test-model", "choices": [{"index": 0, "delta": delta, "finish_reason": None}]},
            {"id": "test", "object": "chat.completion.chunk", "created": 1, "model": "test-model", "choices": [{"index": 0, "delta": {}, "finish_reason": finish}]},
            {"id": "test", "object": "chat.completion.chunk", "created": 1, "model": "test-model", "choices": [], "usage": {"prompt_tokens": 100, "completion_tokens": 10, "total_tokens": 110}},
        ]
        content = "".join("data: " + json.dumps(chunk) + "\n\n" for chunk in chunks) + "data: [DONE]\n\n"
        return httpx.Response(200, content=content, headers={"content-type": "text/event-stream"})

    client = httpx.Client(transport=httpx.MockTransport(reply))
    model = ChatOpenAI(model="test-model", api_key="not-a-real-key", http_client=client,
                       streaming=True, stream_usage=True, max_retries=0)
    result = investigate_with_agent(load_cases()[0], model)
    assert result.category == "missing_bank_identifier"
    assert result.metrics.model_calls == 4
    assert result.metrics.input_tokens == 400 and result.metrics.output_tokens == 40
    assert result.metrics.first_model_output_ms is not None
