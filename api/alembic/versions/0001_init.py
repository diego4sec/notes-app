"""initial note table

Revision ID: 0001
Revises:
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "note",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "tags",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )

    # The one index that every list query uses.
    op.create_index(
        "note_owner_updated_idx",
        "note",
        ["owner_id", sa.text("updated_at DESC")],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    # Full-text search. The expression must match app/routers/notes.py exactly.
    op.execute(
        "CREATE INDEX note_fts_idx ON note USING GIN "
        "(to_tsvector('english', title || ' ' || body))"
    )

    # Tag filtering via `tags @> ARRAY[...]`.
    op.create_index("note_tags_idx", "note", ["tags"], postgresql_using="gin")


def downgrade() -> None:
    op.drop_table("note")
