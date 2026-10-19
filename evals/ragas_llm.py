"""Ragas judge LLM backed by the gateway.

Ragas's LLM-judged metrics (AspectCritic, Faithfulness, ...) need an LLM
that returns a Pydantic model for a prompt. That is exactly what the gateway
does with structured output, so judge calls go through HeliosGateway like
every other model call: same allowlist, same metadata log, no SDK import.
"""

from __future__ import annotations

import asyncio
from typing import TypeVar

from pydantic import BaseModel
from ragas.llms.base import InstructorBaseRagasLLM

from kyc_workflow.gateway import ModelGateway, ModelRequest

T = TypeVar("T", bound=BaseModel)

JUDGE_SYSTEM = (
    "You are an evaluation judge. Read the task carefully and answer only in the "
    "requested structure. Be strict and literal: judge what the text says, not what "
    "it might have meant."
)


class GatewayJudge(InstructorBaseRagasLLM):
    def __init__(self, gateway: ModelGateway, model: str, *, case_id: str = "EVAL-JUDGE", analyst_id: str = "EVAL"):
        self.gateway = gateway
        self.model = model
        self.case_id = case_id
        self.analyst_id = analyst_id
        self.is_async = True  # Ragas reads this to decide between generate and agenerate
        self.provider = "helios-gateway"
        self.calls = 0
        self.input_tokens = 0
        self.output_tokens = 0

    def generate(self, prompt: str, response_model: type[T]) -> T:
        response = self.gateway.complete(ModelRequest(
            case_id=self.case_id, analyst_id=self.analyst_id, model=self.model,
            system=JUDGE_SYSTEM, user=prompt, output_schema=response_model, max_tokens=4096,
        ))
        self.calls += 1
        self.input_tokens += response.usage.input_tokens
        self.output_tokens += response.usage.output_tokens
        assert isinstance(response.parsed, response_model)
        return response.parsed

    async def agenerate(self, prompt: str, response_model: type[T]) -> T:
        return await asyncio.to_thread(self.generate, prompt, response_model)

    def summary(self) -> dict:
        return {"model": self.model, "calls": self.calls,
                "input_tokens": self.input_tokens, "output_tokens": self.output_tokens}
