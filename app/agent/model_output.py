"""Parse final model text without relaxing downstream evidence validation."""
import json


def parse_model_json(message) -> object:
    """Accept model text or text blocks; reject tool calls and non-text outputs."""
    if getattr(message, "tool_calls", None) or getattr(message, "invalid_tool_calls", None):
        raise ValueError("Final response contains tool calls")
    content = message.content
    if isinstance(content, str):
        text = content
    elif isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") in {"text", "output_text"} and isinstance(block.get("text"), str):
                parts.append(block["text"])
            elif isinstance(block, dict) and block.get("type") == "reasoning":
                # Reasoning is not a final answer and is never included in output.
                continue
            else:
                raise ValueError("Unsupported response content block")
        text = "".join(parts)
    else:
        raise ValueError("Unsupported response content")
    return json.loads(text)
