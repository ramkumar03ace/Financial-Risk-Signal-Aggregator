"""
Typed data models shared across the pipeline.

Using pydantic keeps the boundary between deterministic code and LLM output
strict: anything the model returns is validated into these shapes before it is
allowed to influence a score or a rendered rationale.
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class Signal(BaseModel):
    """A single risk signal fired by a deterministic rule."""

    code: str = Field(..., description="Machine code, e.g. STRUCTURING")
    label: str = Field(..., description="Human-readable rule name")
    weight: int = Field(..., description="Points this signal contributes")
    evidence: str = Field(..., description="Concrete facts that triggered the rule")


class AlertHit(BaseModel):
    """A structured hit extracted by the LLM from unstructured alert text."""

    entity_id: str = Field(..., description="customer_id this hit maps to")
    alert_type: str = Field(..., description="e.g. sanctions, adverse_media, watchlist")
    severity: str = Field(..., description="low | medium | high")
    summary: str = Field(..., description="One-line description of the hit")
    source: str = Field(default="external_alert", description="Where the hit came from")


class EntityRisk(BaseModel):
    """The aggregated risk view for one customer/entity."""

    customer_id: str
    name: str
    score: int
    tier: str
    signals: List[Signal] = Field(default_factory=list)
    alert_hits: List[AlertHit] = Field(default_factory=list)
    # Populated by the LLM layer (or its fallback).
    rationale: Optional[str] = None
    recommended_action: Optional[str] = None
    confidence: Optional[str] = None

    @property
    def num_signals(self) -> int:
        return len(self.signals)

    @property
    def signal_codes(self) -> List[str]:
        return [s.code for s in self.signals]
