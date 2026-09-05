"""Pydantic contracts for the webhook input and the LLM output."""

from typing import Literal, Optional

from pydantic import BaseModel, Field


class IncidentPayload(BaseModel):
    """Exact webhook input contract (see payload_contract.json).

    Field names must match the ServiceNow Business Rule payload exactly.
    """

    incident_sys_id: str = Field(min_length=1, description="ServiceNow sys_id")
    number: str = Field(min_length=1, description="e.g. INC0010001")
    short_description: str = Field(min_length=1)
    description: Optional[str] = ""
    priority: int = Field(ge=1, le=5)

    def incident_text(self) -> str:
        desc = (self.description or "").strip()
        if desc:
            return f"{self.short_description.strip()}\n{desc}"
        return self.short_description.strip()


class DecisionResponse(BaseModel):
    """Strict Gemini structured output (FR3)."""

    decision: Literal["respond", "ask", "escalate"]
    message: str = Field(min_length=1)
