import json

import pytest
from langchain_core.messages import AIMessage

from app.agent.model_output import parse_model_json


def test_accepts_plain_text_and_multiple_text_blocks():
    assert parse_model_json(AIMessage(content='{"ok": true}')) == {"ok": True}
    message = AIMessage(content=[{"type": "reasoning", "reasoning": "private"},
                                 {"type": "text", "text": '{"ok":'},
                                 {"type": "output_text", "text": ' true}'}])
    assert parse_model_json(message) == {"ok": True}


@pytest.mark.parametrize("content", [[], [{"type": "image", "url": "https://example.invalid"}],
                                     [{"type": "text", "text": 123}], [{"type": "reasoning"}]])
def test_rejects_missing_or_nontext_answers(content):
    with pytest.raises((ValueError, json.JSONDecodeError)):
        parse_model_json(AIMessage(content=content))


def test_rejects_final_tool_calls():
    message = AIMessage(content='{"ok": true}', tool_calls=[{"name": "unknown", "args": {}, "id": "1"}])
    with pytest.raises(ValueError):
        parse_model_json(message)
