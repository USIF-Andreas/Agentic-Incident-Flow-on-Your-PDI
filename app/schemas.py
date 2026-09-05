from pydantic import BaseModel, Field
from typing import Literal


class IncidentPayload(BaseModel):
    # Field names must match the Business Rule payload exactly.

    incident_sys_id: str = Field(min_length=1)
    number: str = Field(min_length=1)
    short_description: str = Field(min_length=1)
    description: str | None = ""
    priority: int = Field(ge=1, le=5)


class DecisionResponse(BaseModel):
    decision: Literal["respond", "ask", "escalate"]
    message: str = Field(min_length=1)
