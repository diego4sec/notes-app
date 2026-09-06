from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.auth import User, current_user
from app.db import get_db
from app.models import Note
from app.schemas import Me, NoteIn, NoteOut, NotePatch

router = APIRouter()

# Must stay textually identical to the expression in the GIN index, or Postgres
# will not use it. See alembic/versions/0001_init.py.
_FTS_MATCH = text(
    "to_tsvector('english', note.title || ' ' || note.body)"
    " @@ websearch_to_tsquery('english', :q)"
)


def _owned(db: Session, user: User, note_id: UUID) -> Note:
    note = db.scalar(
        select(Note).where(
            Note.id == note_id,
            Note.owner_id == user.id,
            Note.deleted_at.is_(None),
        )
    )
    # 404 rather than 403: a 403 would confirm that someone else's note exists.
    if note is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "note not found")
    return note


@router.get("/me", response_model=Me)
def me(user: User = Depends(current_user)) -> Me:
    return Me(id=user.id, email=user.email, name=user.name, roles=user.roles)


@router.get("/notes", response_model=list[NoteOut])
def list_notes(
    q: str | None = None,
    tag: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[Note]:
    # Ownership is a WHERE clause, never a post-filter, and never taken from
    # anything the client sent.
    stmt = select(Note).where(Note.owner_id == user.id, Note.deleted_at.is_(None))

    if q:
        stmt = stmt.where(_FTS_MATCH.bindparams(q=q))
    if tag:
        stmt = stmt.where(Note.tags.contains([tag]))

    # ponytail: limit/offset. Switch to keyset on updated_at if a user ever has
    # enough notes for deep pages to hurt.
    stmt = stmt.order_by(Note.updated_at.desc()).limit(limit).offset(offset)
    return list(db.scalars(stmt))


@router.post("/notes", response_model=NoteOut, status_code=status.HTTP_201_CREATED)
def create_note(
    payload: NoteIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> Note:
    note = Note(owner_id=user.id, **payload.model_dump())
    db.add(note)
    db.commit()
    db.refresh(note)
    return note


@router.get("/notes/{note_id}", response_model=NoteOut)
def get_note(
    note_id: UUID,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> Note:
    return _owned(db, user, note_id)


@router.patch("/notes/{note_id}", response_model=NoteOut)
def update_note(
    note_id: UUID,
    payload: NotePatch,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> Note:
    note = _owned(db, user, note_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(note, field, value)
    db.commit()
    db.refresh(note)
    return note


@router.delete("/notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_note(
    note_id: UUID,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> Response:
    note = _owned(db, user, note_id)
    note.deleted_at = datetime.now(timezone.utc)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/tags", response_model=list[str])
def list_tags(
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[str]:
    # unnest has to be joined against note, which the ORM expression builder
    # renders as a cartesian product instead. Plain SQL is clearer here.
    rows = db.execute(
        text(
            "SELECT DISTINCT t FROM note, unnest(note.tags) AS t"
            " WHERE note.owner_id = :owner AND note.deleted_at IS NULL"
            " ORDER BY t"
        ),
        {"owner": user.id},
    )
    return [row[0] for row in rows]
