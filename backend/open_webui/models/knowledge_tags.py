"""Tags for knowledge-base documents: a shared, hierarchical vocabulary.

WHY NOT THE EXISTING `tag` TABLE
--------------------------------
``models/tags.py`` is upstream's *chat* tag: its primary key is ``(id, user_id)``
and chats carry a denormalized list of names in ``chat.meta.tags``. That is a
per-user, per-chat shape. A document taxonomy is the opposite — one shared
vocabulary, normalized, joined to documents so it can be queried. Reusing that
table would also put fork code inside a file that collides on every upstream
sync. Hence ``knowledge_tag`` / ``knowledge_file_tag``.

THE ID IS THE PATH
------------------
Obsidian-style: ``сварка/лучевая/лазерная``. A whole subtree is then a prefix
match (``LIKE 'сварка/%'``) rather than a recursive walk, and every tag has
exactly one canonical spelling — which is what makes tag-driven retrieval work
at all. Parents are implied by the path, not stored as a foreign key.

TAGS BELONG TO THE DOCUMENT, NOT THE VERSION
--------------------------------------------
``knowledge_file_tag.knowledge_file_id`` points at the *document*. A tag says
what a document is about, and that survives a revision; keying it to a version
would mean re-tagging on every upload and would leave a pending v2 apparently
untagged while its approved v1 is not.
"""

import logging
import time
from typing import Optional

from open_webui.internal.db import Base, get_async_db_context
from pydantic import BaseModel, ConfigDict
from sqlalchemy import (
    JSON,
    BigInteger,
    Column,
    ForeignKey,
    Index,
    PrimaryKeyConstraint,
    Text,
    delete,
    func,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession

log = logging.getLogger(__name__)

TAG_ID_SEPARATOR = '/'


####################
# DB MODEL
####################


class KnowledgeTag(Base):
    __tablename__ = 'knowledge_tag'

    # The full path, e.g. 'сварка/лучевая/лазерная'. Lower-case, underscores for
    # spaces, '/' for nesting — normalize_tag_id is the only thing that mints one.
    id = Column(Text, primary_key=True)

    # What a picker shows. Usually the leaf spelled for humans («Лазерная»), so
    # the chip can stay terse while the list stays readable.
    label = Column(Text, nullable=False)
    description = Column(Text, nullable=True)

    # NULL for a seeded tag; the creator's id for one added later.
    user_id = Column(Text, nullable=True)

    # {'system': True, 'group': 'Процессы соединения'} for seeded rows. `system`
    # is what protects them from deletion, exactly as on knowledge and group.
    meta = Column(JSON, nullable=True)

    created_at = Column(BigInteger, nullable=False)
    updated_at = Column(BigInteger, nullable=False)


class KnowledgeFileTag(Base):
    """Which tags are on which document."""

    __tablename__ = 'knowledge_file_tag'

    knowledge_file_id = Column(Text, ForeignKey('knowledge_file.id', ondelete='CASCADE'), nullable=False)
    tag_id = Column(Text, ForeignKey('knowledge_tag.id', ondelete='CASCADE'), nullable=False)

    # Who attached it. Kept for provenance only — removal is gated on write
    # access to the base, not on who put the tag there.
    user_id = Column(Text, nullable=False)
    created_at = Column(BigInteger, nullable=False)

    __table_args__ = (
        PrimaryKeyConstraint('knowledge_file_id', 'tag_id', name='pk_knowledge_file_tag'),
        Index('ix_knowledge_file_tag_tag_id', 'tag_id'),
    )


####################
# SCHEMAS
####################


class KnowledgeTagModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    label: str
    description: Optional[str] = None
    user_id: Optional[str] = None
    meta: Optional[dict] = None
    created_at: int
    updated_at: int


class KnowledgeTagResponse(KnowledgeTagModel):
    """A tag plus how many documents carry it, for the picker and the filter bar."""

    count: int = 0


class KnowledgeTagForm(BaseModel):
    label: str
    # Optional explicit id. Omitted, it is derived from the label, which is what
    # the «создать тег» field in the picker does.
    id: Optional[str] = None
    description: Optional[str] = None


class DocumentTagsForm(BaseModel):
    """The complete tag set for a document — this is a PUT, not an append.

    Sending the whole set rather than add/remove deltas keeps the client honest:
    the chip editor already knows every tag it is showing, and two users editing
    the same document cannot half-apply each other's change.
    """

    tag_ids: list[str]


####################
# HELPERS
####################


def normalize_tag_id(value: str) -> str:
    """The single place a tag id is minted.

    Lower-cases, collapses whitespace to underscores, and cleans up the path
    separators. Without one canonical spelling «ГОСТ», «гост» and «ГОСТ » become
    three tags and the vocabulary stops being one.
    """
    segments = []
    for raw_segment in value.strip().split(TAG_ID_SEPARATOR):
        segment = '_'.join(raw_segment.split()).strip('_').lower()
        if segment:
            segments.append(segment)
    return TAG_ID_SEPARATOR.join(segments)


def is_system_tag(tag: Optional[KnowledgeTagModel]) -> bool:
    return bool(tag and (tag.meta or {}).get('system'))


def expand_tag_filter(tag_ids: list[str]) -> list[str]:
    """Normalize the ids a filter was asked for, dropping empties."""
    return [normalized for raw in tag_ids if (normalized := normalize_tag_id(raw))]


####################
# TABLE
####################


class KnowledgeTagTable:
    async def seed_defaults(self, rows: list[dict], db: Optional[AsyncSession] = None) -> None:
        """Insert the seeded vocabulary, keyed on id, never on label.

        Insert-if-absent, like Groups.seed_defaults and Knowledges.seed_defaults:
        an admin who reworded a label or description keeps their edit across every
        subsequent boot. Only genuinely new tags are added.
        """
        async with get_async_db_context(db) as db:
            result = await db.execute(select(KnowledgeTag.id))
            existing = set(result.scalars().all())

            now = int(time.time())
            added = 0
            for row in rows:
                if row['id'] in existing:
                    continue
                db.add(
                    KnowledgeTag(
                        id=row['id'],
                        label=row['label'],
                        description=row.get('description'),
                        user_id=None,
                        meta=row.get('meta'),
                        created_at=now,
                        updated_at=now,
                    )
                )
                added += 1
            if added:
                await db.commit()
                log.info('seeded %d knowledge tag(s)', added)

    async def get_tags(self, db: Optional[AsyncSession] = None) -> list[KnowledgeTagResponse]:
        """The whole vocabulary with usage counts, ordered by id.

        Ordering by id groups a branch together — every 'сварка/…' lands next to
        its siblings — which is what makes the flat list read as a tree.
        """
        async with get_async_db_context(db) as db:
            counts = dict(
                (
                    await db.execute(
                        select(KnowledgeFileTag.tag_id, func.count(KnowledgeFileTag.knowledge_file_id)).group_by(
                            KnowledgeFileTag.tag_id
                        )
                    )
                ).all()
            )
            result = await db.execute(select(KnowledgeTag).order_by(KnowledgeTag.id.asc()))
            return [
                KnowledgeTagResponse(**KnowledgeTagModel.model_validate(tag).model_dump(), count=counts.get(tag.id, 0))
                for tag in result.scalars().all()
            ]

    async def get_tag_by_id(self, tag_id: str, db: Optional[AsyncSession] = None) -> Optional[KnowledgeTagModel]:
        async with get_async_db_context(db) as db:
            result = await db.execute(select(KnowledgeTag).filter_by(id=tag_id))
            tag = result.scalars().first()
            return KnowledgeTagModel.model_validate(tag) if tag else None

    async def create_tag(
        self,
        form: KnowledgeTagForm,
        user_id: str,
        db: Optional[AsyncSession] = None,
    ) -> Optional[KnowledgeTagModel]:
        tag_id = normalize_tag_id(form.id or form.label)
        if not tag_id:
            return None

        async with get_async_db_context(db) as db:
            existing = await self.get_tag_by_id(tag_id, db=db)
            if existing:
                # Not an error: two experts reaching for the same new tag should
                # converge on one row, which is the whole point of normalizing.
                return existing
            now = int(time.time())
            tag = KnowledgeTag(
                id=tag_id,
                label=form.label.strip() or tag_id,
                description=form.description,
                user_id=user_id,
                meta=None,
                created_at=now,
                updated_at=now,
            )
            db.add(tag)
            await db.commit()
            await db.refresh(tag)
            return KnowledgeTagModel.model_validate(tag)

    async def delete_tag(self, tag_id: str, db: Optional[AsyncSession] = None) -> bool:
        """Remove a tag and detach it from every document.

        The join rows are deleted explicitly rather than through the CASCADE on
        knowledge_file_tag.tag_id: SQLite honours that only with PRAGMA
        foreign_keys ON, so relying on it would behave differently in dev and in
        the Postgres deployment.
        """
        async with get_async_db_context(db) as db:
            await db.execute(delete(KnowledgeFileTag).filter(KnowledgeFileTag.tag_id == tag_id))
            await db.execute(delete(KnowledgeTag).filter(KnowledgeTag.id == tag_id))
            await db.commit()
            return True

    async def get_tags_for_documents(
        self,
        document_ids: list[str],
        db: Optional[AsyncSession] = None,
    ) -> dict[str, list[KnowledgeTagModel]]:
        """document id -> its tags, in ONE query.

        The registry draws ten rows per page; asking per row would be ten extra
        round trips for a list that is already a join.
        """
        if not document_ids:
            return {}
        async with get_async_db_context(db) as db:
            result = await db.execute(
                select(KnowledgeFileTag.knowledge_file_id, KnowledgeTag)
                .join(KnowledgeTag, KnowledgeTag.id == KnowledgeFileTag.tag_id)
                .filter(KnowledgeFileTag.knowledge_file_id.in_(document_ids))
                .order_by(KnowledgeTag.id.asc())
            )
            out: dict[str, list[KnowledgeTagModel]] = {}
            for document_id, tag in result.all():
                out.setdefault(document_id, []).append(KnowledgeTagModel.model_validate(tag))
            return out

    async def set_document_tags(
        self,
        document_id: str,
        tag_ids: list[str],
        user_id: str,
        db: Optional[AsyncSession] = None,
    ) -> list[KnowledgeTagModel]:
        """Replace a document's tag set. Unknown ids are ignored, not created.

        Ignoring rather than creating is deliberate: the vocabulary is closed to
        ordinary write access (only admins and Мастер-эксперт mint tags), so a
        client sending an unknown id is out of date, not authorized.
        """
        async with get_async_db_context(db) as db:
            wanted = set(expand_tag_filter(tag_ids))
            if wanted:
                result = await db.execute(select(KnowledgeTag.id).filter(KnowledgeTag.id.in_(wanted)))
                wanted = set(result.scalars().all())

            result = await db.execute(
                select(KnowledgeFileTag.tag_id).filter(KnowledgeFileTag.knowledge_file_id == document_id)
            )
            current = set(result.scalars().all())

            now = int(time.time())
            for tag_id in wanted - current:
                db.add(
                    KnowledgeFileTag(
                        knowledge_file_id=document_id,
                        tag_id=tag_id,
                        user_id=user_id,
                        created_at=now,
                    )
                )
            removed = current - wanted
            if removed:
                await db.execute(
                    delete(KnowledgeFileTag).filter(
                        KnowledgeFileTag.knowledge_file_id == document_id,
                        KnowledgeFileTag.tag_id.in_(removed),
                    )
                )
            await db.commit()

            return (await self.get_tags_for_documents([document_id], db=db)).get(document_id, [])

    async def delete_tags_for_documents(self, document_ids: list[str], db: Optional[AsyncSession] = None) -> None:
        """Drop every tag link for these documents.

        Called explicitly from the document purge paths. knowledge_file_tag has
        ON DELETE CASCADE on knowledge_file_id, but SQLite ignores it without
        PRAGMA foreign_keys — the same divergence that once left version rows
        behind when a folder was deleted with its contents.
        """
        if not document_ids:
            return
        async with get_async_db_context(db) as db:
            await db.execute(delete(KnowledgeFileTag).filter(KnowledgeFileTag.knowledge_file_id.in_(document_ids)))
            await db.commit()

    async def document_ids_with_tags(
        self,
        tag_ids: list[str],
        db: Optional[AsyncSession] = None,
    ) -> Optional[list[str]]:
        """Documents carrying ALL of these tags, subtree-inclusive.

        AND rather than OR: filters compose downward, so adding a tag narrows the
        list, which is what a person expects from clicking a second chip.

        Subtree-inclusive because the id is the path — filtering on `сварка`
        must return `сварка/лучевая/лазерная` too, or a parent tag would look
        broken to anyone who thinks in Obsidian terms.

        Returns None when no filter was asked for, which the caller reads as "do
        not restrict" — distinct from [] meaning "nothing matched".
        """
        wanted = expand_tag_filter(tag_ids)
        if not wanted:
            return None

        async with get_async_db_context(db) as db:
            matched: Optional[set[str]] = None
            for tag_id in wanted:
                result = await db.execute(
                    select(KnowledgeFileTag.knowledge_file_id).filter(
                        (KnowledgeFileTag.tag_id == tag_id)
                        | (KnowledgeFileTag.tag_id.startswith(f'{tag_id}{TAG_ID_SEPARATOR}'))
                    )
                )
                ids = set(result.scalars().all())
                matched = ids if matched is None else (matched & ids)
                if not matched:
                    return []
            return sorted(matched or [])


KnowledgeTags = KnowledgeTagTable()
