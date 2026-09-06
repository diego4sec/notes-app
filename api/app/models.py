from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, UUID as PgUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Note(Base):
    __tablename__ = "note"

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)

    # The Keycloak `sub` claim. No local user table and no FK: identity lives in
    # Keycloak, and email/name come off the token. A user directory only becomes
    # necessary for features we do not have yet.
    # ponytail: no app_user table, add one when notes get shared between users.
    owner_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)

    title: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")

    # ponytail: tags as text[] with a GIN index, not tag + note_tag tables.
    # Tags are owner-scoped, so normalising them buys no shared vocabulary.
    tags: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, default=list, server_default="{}"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
