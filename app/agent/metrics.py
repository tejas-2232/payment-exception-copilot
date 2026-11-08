"""Per-investigation model usage and first generated-output timing."""
import os
from decimal import Decimal, InvalidOperation
from threading import Lock
from time import perf_counter

from langchain_core.callbacks import BaseCallbackHandler

from app.schemas import InvestigationMetrics


class ModelMetricsCallback(BaseCallbackHandler):
    """Track each model call independently; no prompts or credentials are stored."""

    def __init__(self):
        self.lock = Lock()
        self.started = {}
        self.first_output_ms = None
        self.usage = []
        self.completed = 0
        self.failed = 0

    def on_chat_model_start(self, serialized, messages, *, run_id, **kwargs):
        with self.lock:
            self.started[run_id] = perf_counter()

    def on_llm_start(self, serialized, prompts, *, run_id, **kwargs):
        with self.lock:
            self.started[run_id] = perf_counter()

    def on_llm_new_token(self, token, *, chunk=None, run_id, **kwargs):
        message = getattr(chunk, "message", None)
        tool_chunks = getattr(message, "tool_call_chunks", None) or []
        generated = bool(token) or any(c.get("args") or c.get("name") for c in tool_chunks)
        if generated:
            with self.lock:
                if self.first_output_ms is None and run_id in self.started:
                    self.first_output_ms = (perf_counter() - self.started[run_id]) * 1000

    def on_llm_end(self, response, *, run_id, **kwargs):
        with self.lock:
            self.completed += 1
            generations = response.generations
            message = getattr(generations[0][0], "message", None) if generations and generations[0] else None
            usage = getattr(message, "usage_metadata", None)
            self.usage.append(usage)

    def on_llm_error(self, error, *, run_id, **kwargs):
        with self.lock:
            self.failed += 1

    def result(self, elapsed_ms):
        with self.lock:
            metrics = InvestigationMetrics(total_duration_ms=round(elapsed_ms, 1),
                first_model_output_ms=round(self.first_output_ms, 1) if self.first_output_ms is not None else None,
                model_calls=self.completed + self.failed, pricing_status="Usage unavailable")
            if self.failed or not self.usage or any(not isinstance(u, dict) or
                    not isinstance(u.get("input_tokens"), int) or not isinstance(u.get("output_tokens"), int)
                    for u in self.usage):
                return metrics
            metrics.input_tokens = sum(u["input_tokens"] for u in self.usage)
            metrics.output_tokens = sum(u["output_tokens"] for u in self.usage)
            metrics.cached_input_tokens = sum((u.get("input_token_details") or {}).get("cache_read", 0) or 0 for u in self.usage)
            if metrics.input_tokens < 0 or metrics.output_tokens < 0 or not 0 <= metrics.cached_input_tokens <= metrics.input_tokens:
                metrics.pricing_status = "Invalid usage data"
                return metrics
            configured_model = os.getenv("OPENAI_MODEL", "").strip()
            if not configured_model or os.getenv("MODEL_PRICING_MODEL", "").strip() != configured_model:
                metrics.pricing_status = "Configure pricing for the selected model"
                return metrics
            prices = []
            for key in ("MODEL_INPUT_PRICE_PER_MILLION_USD", "MODEL_OUTPUT_PRICE_PER_MILLION_USD", "MODEL_CACHED_INPUT_PRICE_PER_MILLION_USD"):
                value = os.getenv(key)
                try:
                    parsed = Decimal(value) if value is not None and value.strip() else None
                    if parsed is not None and (not parsed.is_finite() or parsed < 0):
                        raise InvalidOperation
                except (InvalidOperation, ValueError):
                    metrics.pricing_status = "Invalid pricing configuration"
                    return metrics
                prices.append(parsed)
            input_price, output_price, cached_price = prices
            if input_price is None or output_price is None or (metrics.cached_input_tokens and cached_price is None):
                metrics.pricing_status = "Configure model prices to estimate cost"
                return metrics
            amount = (Decimal(metrics.input_tokens - metrics.cached_input_tokens) * input_price +
                      Decimal(metrics.cached_input_tokens) * (cached_price or Decimal(0)) +
                      Decimal(metrics.output_tokens) * output_price) / Decimal(1_000_000)
            metrics.estimated_cost_usd = float(amount)
            metrics.pricing_status = "Estimated from configured prices; assumes no unreported cached tokens"
            return metrics
