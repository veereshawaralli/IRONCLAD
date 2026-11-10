from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Agent(StrEnum):
    WATCHER = "watcher"
    DIAGNOSTICIAN = "diagnostician"
    SURGEON = "surgeon"
    SUPERVISOR = "supervisor"


class Incident(StrictModel):
    source: Literal["log", "ci", "issue"] = "log"
    severity: Literal["low", "medium", "high", "critical"]
    summary: str = Field(min_length=1, max_length=1000)
    fingerprint: str


class Evidence(StrictModel):
    path: str
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    text: str


class Diagnosis(StrictModel):
    hypothesis: str = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)
    evidence: list[Evidence] = Field(min_length=1)


class Edit(StrictModel):
    path: str
    old: str = Field(min_length=1)
    new: str
    rationale: str = Field(min_length=1)


class Proposal(StrictModel):
    edits: list[Edit] = Field(min_length=1, max_length=5)
    summary: str


class Message(StrictModel):
    version: Literal[1] = 1
    run_id: str
    seq: int = Field(ge=1)
    agent: Agent
    kind: Literal["incident", "diagnosis", "proposal", "escalated"]
    payload: dict[str, object]
    timestamp: str
    duration_ms: int = Field(ge=0)


class Guardrails(StrictModel):
    max_files: int = Field(default=5, ge=1, le=5)
    max_steps: int = Field(default=3, ge=1, le=3)
    max_input_chars: int = Field(default=24000, ge=1000, le=100000)
    max_output_tokens: int = Field(default=1200, ge=128, le=4000)
    max_model_calls: int = Field(default=4, ge=1, le=6)
    dollar_budget: float = Field(default=0.50, gt=0)
