from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class NoteIn(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    body: str = Field(default="", max_length=100_000)
    tags: list[str] = Field(default_factory=list, max_length=50)


class NotePatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    body: str | None = Field(default=None, max_length=100_000)
    tags: list[str] | None = Field(default=None, max_length=50)


class NoteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    body: str
    tags: list[str]
    created_at: datetime
    updated_at: datetime


class Me(BaseModel):
    id: UUID
    email: str | None
    name: str | None
    roles: list[str]
