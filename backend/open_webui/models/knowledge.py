import json
import logging
import time
import uuid
from typing import Literal, Optional

from open_webui.config import RAG_FILE_CONTENT_SEARCH_MAX_CHARS
from open_webui.internal.db import Base, JSONField, get_async_db_context
from open_webui.models.access_grants import AccessGrantModel, AccessGrants
from open_webui.models.files import (
    File,
    FileMetadataResponse,
    FileModel,
    FileModelResponse,
)
from open_webui.models.groups import Groups
from open_webui.models.users import User, UserModel, UserResponse, Users
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import (
    JSON,
    BigInteger,
    Column,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    and_,
    case,
    delete,
    func,
    or_,
    select,
    update,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, defer

log = logging.getLogger(__name__)

####################
# Knowledge DB Schema
# Let what was gathered here outlast the one who gathered it,
# and still teach when the builder is gone.
####################


class Knowledge(Base):
    __tablename__ = 'knowledge'

    id = Column(Text, unique=True, primary_key=True)
    user_id = Column(Text)

    name = Column(Text)
    description = Column(Text)

    meta = Column(JSON, nullable=True)

    created_at = Column(BigInteger)
    updated_at = Column(BigInteger)


def is_system_knowledge(knowledge) -> bool:
    """True for knowledge bases seeded at startup, which must not be deleted.

    Knowledge has no is_system column, so the marker lives in the meta JSON.
    KnowledgeForm carries only name / description / access_grants, so the update
    path can never set or clear it — only the startup seeder writes it.
    """
    return bool(knowledge and (getattr(knowledge, 'meta', None) or {}).get('system'))


class KnowledgeDirectory(Base):
    __tablename__ = 'knowledge_directory'

    id = Column(Text, unique=True, primary_key=True)
    knowledge_id = Column(Text, ForeignKey('knowledge.id', ondelete='CASCADE'), nullable=False)
    parent_id = Column(Text, ForeignKey('knowledge_directory.id', ondelete='CASCADE'), nullable=True)
    name = Column(Text, nullable=False)
    user_id = Column(Text, nullable=False)

    created_at = Column(BigInteger, nullable=False)
    updated_at = Column(BigInteger, nullable=False)

    __table_args__ = (
        UniqueConstraint('knowledge_id', 'parent_id', 'name', name='uq_knowledge_directory_knowledge_parent_name'),
        Index('ix_knowledge_directory_knowledge_id', 'knowledge_id'),
        Index('ix_knowledge_directory_parent_id', 'parent_id'),
    )


class KnowledgeModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str

    name: str
    description: str

    meta: Optional[dict] = None

    access_grants: list[AccessGrantModel] = Field(default_factory=list)

    created_at: int  # timestamp in epoch
    updated_at: int  # timestamp in epoch


class KnowledgeFile(Base):
    __tablename__ = 'knowledge_file'

    id = Column(Text, unique=True, primary_key=True)

    knowledge_id = Column(Text, ForeignKey('knowledge.id', ondelete='CASCADE'), nullable=False)
    # The *published* version's file. NULL while a document's only version is still
    # awaiting approval — every consumer joins or filters on this column, and both
    # drop NULL rows, which is what keeps unapproved content away from the model.
    file_id = Column(Text, ForeignKey('file.id', ondelete='CASCADE'), nullable=True)
    directory_id = Column(Text, ForeignKey('knowledge_directory.id', ondelete='SET NULL'), nullable=True)
    user_id = Column(Text, nullable=False)

    created_at = Column(BigInteger, nullable=False)
    updated_at = Column(BigInteger, nullable=False)

    __table_args__ = (
        UniqueConstraint('knowledge_id', 'file_id', name='uq_knowledge_file_knowledge_file'),
        Index('ix_knowledge_file_directory_id', 'directory_id'),
    )


class KnowledgeFileModel(BaseModel):
    id: str
    knowledge_id: str
    file_id: Optional[str] = None  # None until a version is approved
    directory_id: Optional[str] = None
    user_id: str

    created_at: int  # timestamp in epoch
    updated_at: int  # timestamp in epoch

    model_config = ConfigDict(from_attributes=True)


VERSION_STATUS_PENDING = 'pending'
VERSION_STATUS_APPROVED = 'approved'
VERSION_STATUS_REJECTED = 'rejected'

VersionStatus = Literal['pending', 'approved', 'rejected']


class KnowledgeFileVersion(Base):
    """One uploaded revision of a document.

    ``knowledge_file`` is the *document*: exactly one row per document, whose
    ``file_id`` always points at the currently published version. Versions that
    are pending or superseded have a ``file`` row and a row here, but **no**
    ``knowledge_file`` row — which is what keeps them out of the vector store and
    out of the seven model-facing consumers of ``Knowledges.get_files_by_id``.
    Approval is therefore a property of the data's shape, not a filter that seven
    call sites have to remember.
    """

    __tablename__ = 'knowledge_file_version'

    id = Column(Text, unique=True, primary_key=True)

    knowledge_file_id = Column(Text, ForeignKey('knowledge_file.id', ondelete='CASCADE'), nullable=False)
    version_no = Column(Integer, nullable=False)
    # UNIQUE: a file belongs to exactly one version, which keeps the join back to
    # the published version 1:1 and stops the listing query fanning out.
    file_id = Column(Text, ForeignKey('file.id', ondelete='CASCADE'), nullable=False, unique=True)
    author_id = Column(Text, nullable=False)

    # Plain text rather than a DB enum, matching how user.role is stored — avoids
    # an enum migration on Postgres when the set of statuses changes.
    status = Column(Text, nullable=False, default=VERSION_STATUS_PENDING)
    comment = Column(Text, nullable=True)  # author's changelog for this revision
    review_note = Column(Text, nullable=True)  # reviewer's reason, e.g. why rejected
    reviewed_by = Column(Text, nullable=True)
    reviewed_at = Column(BigInteger, nullable=True)

    created_at = Column(BigInteger, nullable=False)

    __table_args__ = (
        UniqueConstraint('knowledge_file_id', 'version_no', name='uq_knowledge_file_version_no'),
        Index('ix_knowledge_file_version_knowledge_file_id', 'knowledge_file_id'),
        Index('ix_knowledge_file_version_file_id', 'file_id'),
    )


class KnowledgeFileVersionModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    knowledge_file_id: str
    version_no: int
    file_id: str
    author_id: str

    status: VersionStatus = VERSION_STATUS_PENDING
    comment: Optional[str] = None
    review_note: Optional[str] = None
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[int] = None

    created_at: int


class KnowledgeDirectoryModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    knowledge_id: str
    parent_id: Optional[str] = None
    name: str
    user_id: str

    created_at: int  # timestamp in epoch
    updated_at: int  # timestamp in epoch


class KnowledgeDirectoryForm(BaseModel):
    name: str
    parent_id: Optional[str] = None


####################
# Forms
####################
class KnowledgeUserModel(KnowledgeModel):
    user: Optional[UserResponse] = None


class KnowledgeResponse(KnowledgeModel):
    files: Optional[list[FileMetadataResponse | dict]] = None


class KnowledgeUserResponse(KnowledgeUserModel):
    pass


class KnowledgeForm(BaseModel):
    name: str
    description: str
    access_grants: Optional[list[dict]] = None


class FileUserResponse(FileModelResponse):
    user: Optional[UserResponse] = None


class KnowledgeListResponse(BaseModel):
    items: list[KnowledgeUserModel]
    total: int


class KnowledgeDocumentResponse(BaseModel):
    """One row of the document registry: the document plus its *latest* version.

    Deliberately not the same shape as FileUserResponse. That one answers "which
    files are published", which is the model's question; this one answers "what
    does a human see in the list", which includes revisions still awaiting review.
    """

    document_id: str
    knowledge_id: str
    directory_id: Optional[str] = None

    file_id: str
    filename: str
    meta: Optional[dict] = None

    # The latest version's row id — what approve/reject endpoints take. None for a
    # legacy document that predates versioning and has no version row.
    version_id: Optional[str] = None
    version_no: int
    status: VersionStatus
    comment: Optional[str] = None
    review_note: Optional[str] = None

    author: Optional[UserResponse] = None
    # True when this exact version is the one the model can retrieve.
    is_published: bool = False
    created_at: int
    updated_at: int


class KnowledgeDocumentListResponse(BaseModel):
    items: list[KnowledgeDocumentResponse]
    total: int


class KnowledgeFileListResponse(BaseModel):
    items: list[FileUserResponse]
    directories: list[KnowledgeDirectoryModel] = Field(default_factory=list)
    breadcrumbs: list[KnowledgeDirectoryModel] = Field(default_factory=list)
    total: int


class KnowledgeTable:
    async def _get_access_grants(self, knowledge_id: str, db: Optional[AsyncSession] = None) -> list[AccessGrantModel]:
        return await AccessGrants.get_grants_by_resource('knowledge', knowledge_id, db=db)

    async def _to_knowledge_model(
        self,
        knowledge: Knowledge,
        access_grants: Optional[list[AccessGrantModel]] = None,
        db: Optional[AsyncSession] = None,
    ) -> KnowledgeModel:
        knowledge_data = KnowledgeModel.model_validate(knowledge).model_dump(exclude={'access_grants'})
        knowledge_data['access_grants'] = (
            access_grants if access_grants is not None else await self._get_access_grants(knowledge_data['id'], db=db)
        )
        return KnowledgeModel.model_validate(knowledge_data)

    async def seed_defaults(self, defaults: dict[str, dict], db: Optional[AsyncSession] = None) -> None:
        """Insert knowledge bases whose id doesn't yet exist, with their access grants.

        Mirrors Groups.seed_defaults: keyed on the id so a rename cannot produce a
        duplicate, existing rows win so admin edits survive a restart, and rows are
        built directly rather than through insert_new_knowledge (which mints its own
        uuid and drops meta). Self-healing — a base deleted by mistake returns on the
        next boot, though the menu link is broken until then.

        Each default may carry a 'grants' list of (principal_type, principal_id,
        permission); grant_access is itself idempotent, so grants are reapplied on
        every boot and a revoked one comes back. Group principals must already be
        seeded, so this runs after the tier groups.

        NOTE: unlike the /create route this does not call embed_knowledge_base_metadata(),
        so a seeded base has no metadata embedding until POST /knowledge/metadata/reindex.
        That only affects semantic search *across* knowledge bases.
        """
        async with get_async_db_context(db) as db:
            result = await db.execute(select(Knowledge.id).filter(Knowledge.id.in_(defaults.keys())))
            existing_ids = {row[0] for row in result.all()}

            now = int(time.time())
            created = []
            for kb_id, kb in defaults.items():
                if kb_id in existing_ids:
                    continue
                db.add(
                    Knowledge(
                        id=kb_id,
                        # Seeded at startup, so there is no owner. KnowledgeUserModel.user
                        # is Optional and the list view resolves it with .get(), so an
                        # unmatched user_id renders as no owner rather than failing.
                        user_id='',
                        name=kb['name'],
                        description=kb.get('description', ''),
                        meta=kb.get('meta'),
                        created_at=now,
                        updated_at=now,
                    )
                )
                created.append(kb_id)

            if created:
                try:
                    await db.commit()
                    log.info('Seeded %d new knowledge base(s): %s', len(created), ', '.join(created))
                except Exception as e:
                    log.exception(e)
                    await db.rollback()
                    return

            for kb_id, kb in defaults.items():
                for principal_type, principal_id, permission in kb.get('grants', []):
                    await AccessGrants.grant_access(
                        resource_type='knowledge',
                        resource_id=kb_id,
                        principal_type=principal_type,
                        principal_id=principal_id,
                        permission=permission,
                        db=db,
                    )

    async def insert_new_knowledge(
        self, user_id: str, form_data: KnowledgeForm, db: Optional[AsyncSession] = None
    ) -> Optional[KnowledgeModel]:
        async with get_async_db_context(db) as db:
            knowledge = KnowledgeModel(
                **{
                    **form_data.model_dump(exclude={'access_grants'}),
                    'id': str(uuid.uuid4()),
                    'user_id': user_id,
                    'created_at': int(time.time()),
                    'updated_at': int(time.time()),
                    'access_grants': [],
                }
            )

            try:
                result = Knowledge(**knowledge.model_dump(exclude={'access_grants'}))
                db.add(result)
                await db.commit()
                await db.refresh(result)
                await AccessGrants.set_access_grants('knowledge', result.id, form_data.access_grants, db=db)
                if result:
                    return await self._to_knowledge_model(result, db=db)
                else:
                    return None
            except Exception:
                return None

    async def get_knowledge_bases(
        self, skip: int = 0, limit: int = 30, db: Optional[AsyncSession] = None
    ) -> list[KnowledgeUserModel]:
        async with get_async_db_context(db) as db:
            result = await db.execute(select(Knowledge).order_by(Knowledge.updated_at.desc()))
            all_knowledge = result.scalars().all()
            user_ids = list(set(knowledge.user_id for knowledge in all_knowledge))
            knowledge_ids = [knowledge.id for knowledge in all_knowledge]

            users = await Users.get_users_by_user_ids(user_ids, db=db) if user_ids else []
            users_dict = {user.id: user for user in users}
            grants_map = await AccessGrants.get_grants_by_resources('knowledge', knowledge_ids, db=db)

            knowledge_bases = []
            for knowledge in all_knowledge:
                user = users_dict.get(knowledge.user_id)
                knowledge_bases.append(
                    KnowledgeUserModel.model_validate(
                        {
                            **(
                                await self._to_knowledge_model(
                                    knowledge,
                                    access_grants=grants_map.get(knowledge.id, []),
                                    db=db,
                                )
                            ).model_dump(),
                            'user': user.model_dump() if user else None,
                        }
                    )
                )
            return knowledge_bases

    async def search_knowledge_bases(
        self,
        user_id: str,
        filter: dict,
        skip: int = 0,
        limit: int = 30,
        db: Optional[AsyncSession] = None,
    ) -> KnowledgeListResponse:
        try:
            async with get_async_db_context(db) as db:
                stmt = select(Knowledge, User).outerjoin(User, User.id == Knowledge.user_id)

                if filter:
                    query_key = filter.get('query')
                    if query_key:
                        stmt = stmt.filter(
                            or_(
                                Knowledge.name.ilike(f'%{query_key}%'),
                                Knowledge.description.ilike(f'%{query_key}%'),
                                User.name.ilike(f'%{query_key}%'),
                                User.email.ilike(f'%{query_key}%'),
                                User.username.ilike(f'%{query_key}%'),
                            )
                        )

                    view_option = filter.get('view_option')
                    if view_option == 'created':
                        stmt = stmt.filter(Knowledge.user_id == user_id)
                    elif view_option == 'shared':
                        stmt = stmt.filter(Knowledge.user_id != user_id)

                    source = filter.get('source')
                    if source == 'external':
                        stmt = stmt.filter(Knowledge.meta['source'].as_string() == 'external')
                    elif source == 'local':
                        stmt = stmt.filter(
                            or_(
                                Knowledge.meta.is_(None),
                                Knowledge.meta['source'].as_string() != 'external',
                            )
                        )

                    stmt = AccessGrants.has_permission_filter(
                        db=db,
                        query=stmt,
                        DocumentModel=Knowledge,
                        filter=filter,
                        resource_type='knowledge',
                        permission='read',
                    )

                stmt = stmt.order_by(Knowledge.updated_at.desc(), Knowledge.id.asc())

                count_result = await db.execute(select(func.count()).select_from(stmt.subquery()))
                total = count_result.scalar()
                if skip:
                    stmt = stmt.offset(skip)
                if limit:
                    stmt = stmt.limit(limit)

                result = await db.execute(stmt)
                items = result.all()

                knowledge_ids = [kb.id for kb, _ in items]
                grants_map = await AccessGrants.get_grants_by_resources('knowledge', knowledge_ids, db=db)

                knowledge_bases = []
                for knowledge_base, user in items:
                    knowledge_bases.append(
                        KnowledgeUserModel.model_validate(
                            {
                                **(
                                    await self._to_knowledge_model(
                                        knowledge_base,
                                        access_grants=grants_map.get(knowledge_base.id, []),
                                        db=db,
                                    )
                                ).model_dump(),
                                'user': (UserModel.model_validate(user).model_dump() if user else None),
                            }
                        )
                    )

                return KnowledgeListResponse(items=knowledge_bases, total=total)
        except Exception as e:
            print(e)
            return KnowledgeListResponse(items=[], total=0)

    async def search_knowledge_files(
        self, filter: dict, skip: int = 0, limit: int = 30, db: Optional[AsyncSession] = None
    ) -> KnowledgeFileListResponse:
        """
        Scalable version: search files across all knowledge bases the user has
        READ access to, without loading all KBs or using large IN() lists.
        """
        try:
            async with get_async_db_context(db) as db:
                # Base query: join Knowledge → KnowledgeFile → File
                stmt = (
                    select(File, User, Knowledge)
                    .join(KnowledgeFile, File.id == KnowledgeFile.file_id)
                    .join(Knowledge, KnowledgeFile.knowledge_id == Knowledge.id)
                    .outerjoin(User, User.id == KnowledgeFile.user_id)
                )

                # Apply access-control directly to the joined query
                stmt = AccessGrants.has_permission_filter(
                    db=db,
                    query=stmt,
                    DocumentModel=Knowledge,
                    filter=filter,
                    resource_type='knowledge',
                    permission='read',
                )

                # Apply filename / content search
                search_filter = None
                if filter:
                    q = filter.get('query')
                    if q:
                        if filter.get('include_content'):
                            # Use ->> (as_string) instead of CAST(-> AS TEXT)
                            # to avoid PostgreSQL "invalid memory alloc request
                            # size" on large extracted-content rows (#24670).
                            content_text = File.data['content'].as_string()
                            content_text = func.substr(content_text, 1, RAG_FILE_CONTENT_SEARCH_MAX_CHARS)
                            search_filter = or_(
                                File.filename.ilike(f'%{q}%'),
                                content_text.ilike(f'%{q}%'),
                            )
                        else:
                            search_filter = File.filename.ilike(f'%{q}%')
                        stmt = stmt.filter(search_filter)

                # Order by file changes
                stmt = stmt.order_by(File.updated_at.desc(), File.id.asc())

                # Lightweight count: avoid selecting File.data and ORDER BY
                count_stmt = (
                    select(func.count(File.id))
                    .select_from(File)
                    .join(KnowledgeFile, File.id == KnowledgeFile.file_id)
                    .join(Knowledge, KnowledgeFile.knowledge_id == Knowledge.id)
                )
                count_stmt = AccessGrants.has_permission_filter(
                    db=db,
                    query=count_stmt,
                    DocumentModel=Knowledge,
                    filter=filter,
                    resource_type='knowledge',
                    permission='read',
                )
                if search_filter is not None:
                    count_stmt = count_stmt.filter(search_filter)
                count_result = await db.execute(count_stmt)
                total = count_result.scalar()

                if skip:
                    stmt = stmt.offset(skip)
                if limit:
                    stmt = stmt.limit(limit)

                stmt = stmt.options(defer(File.data))
                result = await db.execute(stmt)
                rows = result.all()

                items = []
                for file, user, knowledge in rows:
                    items.append(
                        FileUserResponse(
                            id=file.id,
                            user_id=file.user_id,
                            hash=file.hash,
                            filename=file.filename,
                            meta=file.meta,
                            created_at=file.created_at,
                            updated_at=file.updated_at,
                            user=(UserResponse(**UserModel.model_validate(user).model_dump()) if user else None),
                            collection=(await self._to_knowledge_model(knowledge, db=db)).model_dump(),
                        )
                    )

                return KnowledgeFileListResponse(items=items, total=total)

        except Exception as e:
            print('search_knowledge_files error:', e)
            return KnowledgeFileListResponse(items=[], total=0)

    async def check_access_by_user_id(self, id, user_id, permission='write', db: Optional[AsyncSession] = None) -> bool:
        knowledge = await self.get_knowledge_by_id(id, db=db)
        if not knowledge:
            return False
        if knowledge.user_id == user_id:
            return True
        user_groups = await Groups.get_groups_by_member_id(user_id, db=db)
        user_group_ids = {group.id for group in user_groups}
        return await AccessGrants.has_access(
            user_id=user_id,
            resource_type='knowledge',
            resource_id=knowledge.id,
            permission=permission,
            user_group_ids=user_group_ids,
            db=db,
        )

    async def get_knowledge_bases_by_user_id(
        self, user_id: str, permission: str = 'write', db: Optional[AsyncSession] = None
    ) -> list[KnowledgeUserModel]:
        knowledge_bases = await self.get_knowledge_bases(db=db)
        user_groups = await Groups.get_groups_by_member_id(user_id, db=db)
        user_group_ids = {group.id for group in user_groups}

        result = []
        for knowledge_base in knowledge_bases:
            if knowledge_base.user_id == user_id:
                result.append(knowledge_base)
            elif await AccessGrants.has_access(
                user_id=user_id,
                resource_type='knowledge',
                resource_id=knowledge_base.id,
                permission=permission,
                user_group_ids=user_group_ids,
                db=db,
            ):
                result.append(knowledge_base)
        return result

    async def get_knowledge_by_id(self, id: str, db: Optional[AsyncSession] = None) -> Optional[KnowledgeModel]:
        try:
            async with get_async_db_context(db) as db:
                result = await db.execute(select(Knowledge).filter_by(id=id))
                knowledge = result.scalars().first()
                return await self._to_knowledge_model(knowledge, db=db) if knowledge else None
        except Exception:
            return None

    async def get_knowledge_by_id_and_user_id(
        self, id: str, user_id: str, db: Optional[AsyncSession] = None
    ) -> Optional[KnowledgeModel]:
        knowledge = await self.get_knowledge_by_id(id, db=db)
        if not knowledge:
            return None

        if knowledge.user_id == user_id:
            return knowledge

        user_groups = await Groups.get_groups_by_member_id(user_id, db=db)
        user_group_ids = {group.id for group in user_groups}
        if await AccessGrants.has_access(
            user_id=user_id,
            resource_type='knowledge',
            resource_id=knowledge.id,
            permission='write',
            user_group_ids=user_group_ids,
            db=db,
        ):
            return knowledge
        return None

    async def get_knowledges_by_file_id(self, file_id: str, db: Optional[AsyncSession] = None) -> list[KnowledgeModel]:
        try:
            async with get_async_db_context(db) as db:
                result = await db.execute(
                    select(Knowledge)
                    .join(KnowledgeFile, Knowledge.id == KnowledgeFile.knowledge_id)
                    .filter(KnowledgeFile.file_id == file_id)
                )
                knowledges = result.scalars().all()
                knowledge_ids = [k.id for k in knowledges]
                grants_map = await AccessGrants.get_grants_by_resources('knowledge', knowledge_ids, db=db)
                return [
                    await self._to_knowledge_model(
                        knowledge,
                        access_grants=grants_map.get(knowledge.id, []),
                        db=db,
                    )
                    for knowledge in knowledges
                ]
        except Exception:
            return []

    async def search_files_by_id(
        self,
        knowledge_id: str,
        user_id: str,
        filter: dict,
        skip: int = 0,
        limit: int = 30,
        db: Optional[AsyncSession] = None,
    ) -> KnowledgeFileListResponse:
        try:
            async with get_async_db_context(db) as db:
                stmt = (
                    select(File, User)
                    .join(KnowledgeFile, File.id == KnowledgeFile.file_id)
                    .outerjoin(User, User.id == KnowledgeFile.user_id)
                    .filter(KnowledgeFile.knowledge_id == knowledge_id)
                )

                # Filter by directory_id (None = root level)
                directory_id = filter.get('directory_id') if filter else None
                if directory_id:
                    stmt = stmt.filter(KnowledgeFile.directory_id == directory_id)
                elif filter and 'directory_id' in filter:
                    # Explicit None = root level only
                    stmt = stmt.filter(KnowledgeFile.directory_id.is_(None))

                # Default sort: updated_at descending
                primary_sort = File.updated_at.desc()

                if filter:
                    query_key = filter.get('query')
                    if query_key:
                        if filter.get('include_content'):
                            # Use ->> (as_string) instead of CAST(-> AS TEXT)
                            # to avoid PostgreSQL memory allocation failures on
                            # large content (#24670).
                            content_text = File.data['content'].as_string()
                            content_text = func.substr(content_text, 1, RAG_FILE_CONTENT_SEARCH_MAX_CHARS)
                            stmt = stmt.filter(
                                or_(
                                    File.filename.ilike(f'%{query_key}%'),
                                    content_text.ilike(f'%{query_key}%'),
                                )
                            )
                        else:
                            stmt = stmt.filter(File.filename.ilike(f'%{query_key}%'))

                    view_option = filter.get('view_option')
                    if view_option == 'created':
                        stmt = stmt.filter(KnowledgeFile.user_id == user_id)
                    elif view_option == 'shared':
                        stmt = stmt.filter(KnowledgeFile.user_id != user_id)

                    order_by = filter.get('order_by')
                    direction = filter.get('direction')
                    is_asc = direction == 'asc'

                    if order_by == 'name':
                        primary_sort = File.filename.asc() if is_asc else File.filename.desc()
                    elif order_by == 'created_at':
                        primary_sort = File.created_at.asc() if is_asc else File.created_at.desc()
                    elif order_by == 'updated_at':
                        primary_sort = File.updated_at.asc() if is_asc else File.updated_at.desc()

                # Apply sort with secondary key for deterministic pagination
                stmt = stmt.order_by(primary_sort, File.id.asc())

                # Count BEFORE pagination
                count_result = await db.execute(select(func.count()).select_from(stmt.subquery()))
                total = count_result.scalar()

                if skip:
                    stmt = stmt.offset(skip)
                if limit:
                    stmt = stmt.limit(limit)

                stmt = stmt.options(defer(File.data))
                result = await db.execute(stmt)
                items = result.all()

                files = [
                    FileUserResponse(
                        id=file.id,
                        user_id=file.user_id,
                        hash=file.hash,
                        filename=file.filename,
                        meta=file.meta,
                        created_at=file.created_at,
                        updated_at=file.updated_at,
                        user=(UserResponse(**UserModel.model_validate(user).model_dump()) if user else None),
                    )
                    for file, user in items
                ]

                return KnowledgeFileListResponse(
                    items=files,
                    directories=await self.get_directories(
                        knowledge_id,
                        parent_id=filter.get('directory_id') if filter else None,
                        db=db,
                    ),
                    breadcrumbs=await self.get_directory_breadcrumbs(
                        filter.get('directory_id') if filter else None,
                        db=db,
                    ),
                    total=total,
                )
        except Exception as e:
            print(e)
            return KnowledgeFileListResponse(items=[], total=0)

    async def get_files_by_id(self, knowledge_id: str, db: Optional[AsyncSession] = None) -> list[FileModel]:
        try:
            async with get_async_db_context(db) as db:
                result = await db.execute(
                    select(File)
                    .join(KnowledgeFile, File.id == KnowledgeFile.file_id)
                    .filter(KnowledgeFile.knowledge_id == knowledge_id)
                )
                files = result.scalars().all()
                return [FileModel.model_validate(file) for file in files]
        except Exception:
            return []

    async def get_file_metadatas_by_id(
        self, knowledge_id: str, db: Optional[AsyncSession] = None
    ) -> list[FileMetadataResponse]:
        try:
            files = await self.get_files_by_id(knowledge_id, db=db)
            return [FileMetadataResponse(**file.model_dump()) for file in files]
        except Exception:
            return []

    async def add_file_to_knowledge_by_id(
        self,
        knowledge_id: str,
        file_id: str,
        user_id: str,
        directory_id: Optional[str] = None,
        db: Optional[AsyncSession] = None,
    ) -> Optional[KnowledgeFileModel]:
        """Attach a file to a knowledge base as a document awaiting review.

        This is the **single chokepoint** for putting a file into a knowledge base
        and it deliberately does NOT publish: the document is created with a NULL
        file_id and a pending v1, so the content stays out of the vector store
        until a Мастер-эксперт approves it.

        It used to create a published row directly, and three separate routes call
        it — POST /knowledge/{id}/file/add, the auto-link inside POST /files/ when
        the upload carries metadata.knowledge_id, and the batch add. Gating only
        one of them left the other two publishing on upload. Enforcing the rule
        here means every caller, including any added later, is correct by default.
        """
        created = await self.create_document(
            knowledge_id=knowledge_id,
            file_id=file_id,
            author_id=user_id,
            directory_id=directory_id,
            db=db,
        )
        return created[0] if created else None

    # ── Document versions ────────────────────────────────────────────
    #
    # A "document" is a knowledge_file row. Its versions live in
    # knowledge_file_version; knowledge_file.file_id is whichever version is
    # currently published (NULL if none is). Publishing is the only thing that
    # makes content reachable by the model, so it is deliberately a single
    # assignment in publish_version() rather than something spread around.

    async def search_documents_by_id(
        self,
        knowledge_id: str,
        filter: Optional[dict] = None,
        skip: int = 0,
        limit: int = 30,
        db: Optional[AsyncSession] = None,
    ) -> KnowledgeDocumentListResponse:
        """The human-facing document registry: one row per document, latest version.

        Separate from ``search_files_by_id`` on purpose. That function is what the
        model's search_knowledge tool calls (tools/builtin.py), so it must keep
        returning published files only; this one deliberately includes revisions
        awaiting review, which must never reach the model. Keeping them as two
        functions means the model path cannot accidentally inherit a change made
        for the UI.

        Cardinality stays one row per document — the max(version_no) subquery is
        grouped by document and joined back on equality — so LIMIT/OFFSET and the
        total count remain correct.
        """
        filter = filter or {}
        async with get_async_db_context(db) as db:
            latest = (
                select(
                    KnowledgeFileVersion.knowledge_file_id.label('kf_id'),
                    func.max(KnowledgeFileVersion.version_no).label('max_no'),
                )
                .group_by(KnowledgeFileVersion.knowledge_file_id)
                .subquery()
            )

            version = aliased(KnowledgeFileVersion)
            # OUTER joins throughout, deliberately. An inner join here silently hides
            # any document whose version rows are missing — which is exactly what
            # happened to documents added between the version migration and the
            # versioned upload path going live. A document must never disappear from
            # the registry because of a gap in its history.
            stmt = (
                select(KnowledgeFile, version, File, User)
                .outerjoin(latest, latest.c.kf_id == KnowledgeFile.id)
                .outerjoin(
                    version,
                    and_(
                        version.knowledge_file_id == KnowledgeFile.id,
                        version.version_no == latest.c.max_no,
                    ),
                )
                # Fall back to the document's published file when no version row exists.
                .outerjoin(File, File.id == func.coalesce(version.file_id, KnowledgeFile.file_id))
                .outerjoin(User, User.id == func.coalesce(version.author_id, KnowledgeFile.user_id))
                .filter(KnowledgeFile.knowledge_id == knowledge_id)
            )

            query = filter.get('query')
            if query:
                stmt = stmt.filter(File.filename.ilike(f'%{query}%'))

            status_filter = filter.get('status')
            if status_filter:
                # A versionless document reads as approved when it has a published file.
                effective_status = func.coalesce(
                    version.status,
                    case((KnowledgeFile.file_id.isnot(None), VERSION_STATUS_APPROVED), else_=VERSION_STATUS_PENDING),
                )
                stmt = stmt.filter(effective_status == status_filter)

            directory_id = filter.get('directory_id') if 'directory_id' in filter else None
            if 'directory_id' in filter:
                if directory_id:
                    stmt = stmt.filter(KnowledgeFile.directory_id == directory_id)
                else:
                    stmt = stmt.filter(KnowledgeFile.directory_id.is_(None))

            count_result = await db.execute(select(func.count()).select_from(stmt.subquery()))
            total = count_result.scalar() or 0

            # File.id as a tiebreaker keeps paging deterministic when timestamps collide.
            stmt = stmt.order_by(KnowledgeFile.updated_at.desc(), File.id.asc()).offset(skip).limit(limit)
            stmt = stmt.options(defer(File.data))

            rows = (await db.execute(stmt)).all()

            return KnowledgeDocumentListResponse(
                items=[
                    KnowledgeDocumentResponse(
                        document_id=document.id,
                        knowledge_id=document.knowledge_id,
                        directory_id=document.directory_id,
                        file_id=file.id,
                        filename=file.filename,
                        meta=file.meta,
                        version_id=ver.id if ver else None,
                        version_no=ver.version_no if ver else 1,
                        status=(
                            ver.status
                            if ver
                            else (VERSION_STATUS_APPROVED if document.file_id else VERSION_STATUS_PENDING)
                        ),
                        comment=ver.comment if ver else None,
                        review_note=ver.review_note if ver else None,
                        author=(UserResponse(**UserModel.model_validate(author).model_dump()) if author else None),
                        is_published=bool(document.file_id) and document.file_id == (ver.file_id if ver else file.id),
                        created_at=ver.created_at if ver else document.created_at,
                        updated_at=document.updated_at,
                    )
                    for document, ver, file, author in rows
                    # A row with neither a version nor a published file has no file to
                    # show at all; skip rather than emit a half-empty entry.
                    if file is not None
                ],
                total=total,
            )

    async def create_document(
        self,
        knowledge_id: str,
        file_id: str,
        author_id: str,
        comment: Optional[str] = None,
        directory_id: Optional[str] = None,
        approved: bool = False,
        db: Optional[AsyncSession] = None,
    ) -> Optional[tuple[KnowledgeFileModel, KnowledgeFileVersionModel]]:
        """Create a document with its first version.

        ``approved=False`` leaves ``knowledge_file.file_id`` NULL, so the document
        exists and is listable but nothing about it reaches the model.
        """
        now = int(time.time())
        async with get_async_db_context(db) as db:
            try:
                document = KnowledgeFile(
                    id=str(uuid.uuid4()),
                    knowledge_id=knowledge_id,
                    file_id=file_id if approved else None,
                    directory_id=directory_id,
                    user_id=author_id,
                    created_at=now,
                    updated_at=now,
                )
                db.add(document)
                await db.flush()

                version = KnowledgeFileVersion(
                    id=str(uuid.uuid4()),
                    knowledge_file_id=document.id,
                    version_no=1,
                    file_id=file_id,
                    author_id=author_id,
                    status=VERSION_STATUS_APPROVED if approved else VERSION_STATUS_PENDING,
                    comment=comment,
                    reviewed_by=author_id if approved else None,
                    reviewed_at=now if approved else None,
                    created_at=now,
                )
                db.add(version)
                await db.commit()
                await db.refresh(document)
                await db.refresh(version)
                return (
                    KnowledgeFileModel.model_validate(document),
                    KnowledgeFileVersionModel.model_validate(version),
                )
            except Exception as e:
                log.exception(e)
                await db.rollback()
                return None

    async def add_version(
        self,
        knowledge_file_id: str,
        file_id: str,
        author_id: str,
        comment: Optional[str] = None,
        approved: bool = False,
        db: Optional[AsyncSession] = None,
    ) -> Optional[KnowledgeFileVersionModel]:
        """Append a new revision to an existing document."""
        now = int(time.time())
        async with get_async_db_context(db) as db:
            try:
                result = await db.execute(
                    select(func.max(KnowledgeFileVersion.version_no)).filter(
                        KnowledgeFileVersion.knowledge_file_id == knowledge_file_id
                    )
                )
                next_no = (result.scalar() or 0) + 1

                version = KnowledgeFileVersion(
                    id=str(uuid.uuid4()),
                    knowledge_file_id=knowledge_file_id,
                    version_no=next_no,
                    file_id=file_id,
                    author_id=author_id,
                    status=VERSION_STATUS_APPROVED if approved else VERSION_STATUS_PENDING,
                    comment=comment,
                    reviewed_by=author_id if approved else None,
                    reviewed_at=now if approved else None,
                    created_at=now,
                )
                db.add(version)
                await db.commit()
                await db.refresh(version)
                return KnowledgeFileVersionModel.model_validate(version)
            except Exception as e:
                log.exception(e)
                await db.rollback()
                return None

    async def get_versions(
        self, knowledge_file_id: str, db: Optional[AsyncSession] = None
    ) -> list[KnowledgeFileVersionModel]:
        """Full history, newest version first — what «История» renders."""
        async with get_async_db_context(db) as db:
            result = await db.execute(
                select(KnowledgeFileVersion)
                .filter(KnowledgeFileVersion.knowledge_file_id == knowledge_file_id)
                .order_by(KnowledgeFileVersion.version_no.desc())
            )
            return [KnowledgeFileVersionModel.model_validate(v) for v in result.scalars().all()]

    async def get_version_by_id(
        self, version_id: str, db: Optional[AsyncSession] = None
    ) -> Optional[KnowledgeFileVersionModel]:
        async with get_async_db_context(db) as db:
            result = await db.execute(select(KnowledgeFileVersion).filter_by(id=version_id))
            version = result.scalars().first()
            return KnowledgeFileVersionModel.model_validate(version) if version else None

    async def get_latest_version(
        self, knowledge_file_id: str, db: Optional[AsyncSession] = None
    ) -> Optional[KnowledgeFileVersionModel]:
        async with get_async_db_context(db) as db:
            result = await db.execute(
                select(KnowledgeFileVersion)
                .filter(KnowledgeFileVersion.knowledge_file_id == knowledge_file_id)
                .order_by(KnowledgeFileVersion.version_no.desc())
                .limit(1)
            )
            version = result.scalars().first()
            return KnowledgeFileVersionModel.model_validate(version) if version else None

    async def get_pending_versions(
        self, knowledge_id: str, db: Optional[AsyncSession] = None
    ) -> list[tuple[KnowledgeFileVersionModel, KnowledgeFileModel]]:
        """Every version awaiting review in a knowledge base — the reviewer queue."""
        async with get_async_db_context(db) as db:
            result = await db.execute(
                select(KnowledgeFileVersion, KnowledgeFile)
                .join(KnowledgeFile, KnowledgeFile.id == KnowledgeFileVersion.knowledge_file_id)
                .filter(
                    KnowledgeFile.knowledge_id == knowledge_id,
                    KnowledgeFileVersion.status == VERSION_STATUS_PENDING,
                )
                .order_by(KnowledgeFileVersion.created_at.asc())
            )
            return [
                (
                    KnowledgeFileVersionModel.model_validate(v),
                    KnowledgeFileModel.model_validate(d),
                )
                for v, d in result.all()
            ]

    async def set_version_status(
        self,
        version_id: str,
        status: VersionStatus,
        reviewer_id: str,
        review_note: Optional[str] = None,
        db: Optional[AsyncSession] = None,
    ) -> Optional[KnowledgeFileVersionModel]:
        async with get_async_db_context(db) as db:
            try:
                await db.execute(
                    update(KnowledgeFileVersion)
                    .filter_by(id=version_id)
                    .values(
                        status=status,
                        review_note=review_note,
                        reviewed_by=reviewer_id,
                        reviewed_at=int(time.time()),
                    )
                )
                await db.commit()
                return await self.get_version_by_id(version_id, db=db)
            except Exception as e:
                log.exception(e)
                await db.rollback()
                return None

    async def publish_version(
        self, knowledge_file_id: str, file_id: Optional[str], db: Optional[AsyncSession] = None
    ) -> Optional[KnowledgeFileModel]:
        """Point a document at a version's file — the single act that exposes
        content to the model. ``file_id=None`` unpublishes the document."""
        async with get_async_db_context(db) as db:
            try:
                await db.execute(
                    update(KnowledgeFile)
                    .filter_by(id=knowledge_file_id)
                    .values(file_id=file_id, updated_at=int(time.time()))
                )
                await db.commit()
                result = await db.execute(select(KnowledgeFile).filter_by(id=knowledge_file_id))
                document = result.scalars().first()
                return KnowledgeFileModel.model_validate(document) if document else None
            except Exception as e:
                log.exception(e)
                await db.rollback()
                return None

    async def get_document_by_id(
        self, knowledge_file_id: str, db: Optional[AsyncSession] = None
    ) -> Optional[KnowledgeFileModel]:
        async with get_async_db_context(db) as db:
            result = await db.execute(select(KnowledgeFile).filter_by(id=knowledge_file_id))
            document = result.scalars().first()
            return KnowledgeFileModel.model_validate(document) if document else None

    async def get_document_by_file_id(
        self, knowledge_id: str, file_id: str, db: Optional[AsyncSession] = None
    ) -> Optional[KnowledgeFileModel]:
        """Find the document that owns a file, through any of its versions."""
        async with get_async_db_context(db) as db:
            result = await db.execute(
                select(KnowledgeFile)
                .join(KnowledgeFileVersion, KnowledgeFileVersion.knowledge_file_id == KnowledgeFile.id)
                .filter(
                    KnowledgeFile.knowledge_id == knowledge_id,
                    KnowledgeFileVersion.file_id == file_id,
                )
                .limit(1)
            )
            document = result.scalars().first()
            return KnowledgeFileModel.model_validate(document) if document else None

    async def has_file(self, knowledge_id: str, file_id: str, db: Optional[AsyncSession] = None) -> bool:
        """Check whether a file belongs to a knowledge base."""
        try:
            async with get_async_db_context(db) as db:
                result = await db.execute(
                    select(KnowledgeFile).filter_by(knowledge_id=knowledge_id, file_id=file_id).limit(1)
                )
                return result.scalars().first() is not None
        except Exception:
            return False

    async def remove_file_from_knowledge_by_id(
        self, knowledge_id: str, file_id: str, db: Optional[AsyncSession] = None
    ) -> bool:
        try:
            async with get_async_db_context(db) as db:
                await db.execute(delete(KnowledgeFile).filter_by(knowledge_id=knowledge_id, file_id=file_id))
                await db.commit()
                return True
        except Exception:
            return False

    async def reset_knowledge_by_id(
        self, id: str, include_directories: bool = True, db: Optional[AsyncSession] = None
    ) -> Optional[KnowledgeModel]:
        try:
            async with get_async_db_context(db) as db:
                # Delete all knowledge_file entries for this knowledge_id
                await db.execute(delete(KnowledgeFile).filter_by(knowledge_id=id))

                # Delete all directories if requested
                if include_directories:
                    await db.execute(delete(KnowledgeDirectory).filter_by(knowledge_id=id))

                await db.commit()

                # Update the knowledge entry's updated_at timestamp
                await db.execute(update(Knowledge).filter_by(id=id).values(updated_at=int(time.time())))
                await db.commit()

                return await self.get_knowledge_by_id(id=id, db=db)
        except Exception as e:
            log.exception(e)
            return None

    async def update_knowledge_by_id(
        self,
        id: str,
        form_data: KnowledgeForm,
        overwrite: bool = False,
        db: Optional[AsyncSession] = None,
    ) -> Optional[KnowledgeModel]:
        try:
            async with get_async_db_context(db) as db:
                await db.execute(
                    update(Knowledge)
                    .filter_by(id=id)
                    .values(
                        **form_data.model_dump(exclude={'access_grants'}),
                        updated_at=int(time.time()),
                    )
                )
                await db.commit()
                if form_data.access_grants is not None:
                    await AccessGrants.set_access_grants('knowledge', id, form_data.access_grants, db=db)
                return await self.get_knowledge_by_id(id=id, db=db)
        except Exception as e:
            log.exception(e)
            return None

    async def update_knowledge_data_by_id(
        self, id: str, data: dict, db: Optional[AsyncSession] = None
    ) -> Optional[KnowledgeModel]:
        try:
            async with get_async_db_context(db) as db:
                await db.execute(
                    update(Knowledge)
                    .filter_by(id=id)
                    .values(
                        data=data,
                        updated_at=int(time.time()),
                    )
                )
                await db.commit()
                return await self.get_knowledge_by_id(id=id, db=db)
        except Exception as e:
            log.exception(e)
            return None

    async def update_knowledge_meta_by_id(
        self, id: str, meta: dict, db: Optional[AsyncSession] = None
    ) -> Optional[KnowledgeModel]:
        try:
            async with get_async_db_context(db) as db:
                await db.execute(
                    update(Knowledge)
                    .filter_by(id=id)
                    .values(
                        meta=meta,
                        updated_at=int(time.time()),
                    )
                )
                await db.commit()
                return await self.get_knowledge_by_id(id=id, db=db)
        except Exception as e:
            log.exception(e)
            return None

    async def delete_knowledge_by_id(self, id: str, db: Optional[AsyncSession] = None) -> bool:
        try:
            async with get_async_db_context(db) as db:
                await AccessGrants.revoke_all_access('knowledge', id, db=db)
                await db.execute(delete(Knowledge).filter_by(id=id))
                await db.commit()
                return True
        except Exception:
            return False

    async def delete_all_knowledge(self, db: Optional[AsyncSession] = None) -> bool:
        async with get_async_db_context(db) as db:
            try:
                result = await db.execute(select(Knowledge.id))
                knowledge_ids = [row[0] for row in result.all()]
                for knowledge_id in knowledge_ids:
                    await AccessGrants.revoke_all_access('knowledge', knowledge_id, db=db)
                await db.execute(delete(Knowledge))
                await db.commit()

                return True
            except Exception:
                return False

    # ── Directory CRUD ────────────────────────────────────────────────

    async def create_directory(
        self,
        knowledge_id: str,
        name: str,
        user_id: str,
        parent_id: Optional[str] = None,
        db: Optional[AsyncSession] = None,
    ) -> Optional[KnowledgeDirectoryModel]:
        async with get_async_db_context(db) as db:
            try:
                now = int(time.time())
                directory = KnowledgeDirectory(
                    id=str(uuid.uuid4()),
                    knowledge_id=knowledge_id,
                    parent_id=parent_id,
                    name=name,
                    user_id=user_id,
                    created_at=now,
                    updated_at=now,
                )
                db.add(directory)
                await db.commit()
                await db.refresh(directory)
                return KnowledgeDirectoryModel.model_validate(directory)
            except Exception as e:
                log.exception(e)
                return None

    async def get_directories(
        self,
        knowledge_id: str,
        parent_id: Optional[str] = None,
        db: Optional[AsyncSession] = None,
    ) -> list[KnowledgeDirectoryModel]:
        """List directories at a given level (parent_id=None for root)."""
        async with get_async_db_context(db) as db:
            stmt = select(KnowledgeDirectory).filter(KnowledgeDirectory.knowledge_id == knowledge_id)
            if parent_id:
                stmt = stmt.filter(KnowledgeDirectory.parent_id == parent_id)
            else:
                stmt = stmt.filter(KnowledgeDirectory.parent_id.is_(None))

            stmt = stmt.order_by(KnowledgeDirectory.name.asc())
            result = await db.execute(stmt)
            return [KnowledgeDirectoryModel.model_validate(d) for d in result.scalars().all()]

    async def get_all_directories(
        self,
        knowledge_id: str,
        db: Optional[AsyncSession] = None,
    ) -> list[KnowledgeDirectoryModel]:
        """Get ALL directories for a KB (no parent filter). Used for tree building."""
        async with get_async_db_context(db) as db:
            stmt = (
                select(KnowledgeDirectory)
                .filter(KnowledgeDirectory.knowledge_id == knowledge_id)
                .order_by(KnowledgeDirectory.name.asc())
            )
            result = await db.execute(stmt)
            return [KnowledgeDirectoryModel.model_validate(d) for d in result.scalars().all()]

    async def get_files_with_directory_ids(
        self,
        knowledge_id: str,
        db: Optional[AsyncSession] = None,
    ) -> list[tuple[FileModel, Optional[str]]]:
        """Get all files in a KB with their directory_id from KnowledgeFile."""
        try:
            async with get_async_db_context(db) as db:
                result = await db.execute(
                    select(File, KnowledgeFile.directory_id)
                    .join(KnowledgeFile, File.id == KnowledgeFile.file_id)
                    .filter(KnowledgeFile.knowledge_id == knowledge_id)
                )
                return [(FileModel.model_validate(file), dir_id) for file, dir_id in result.all()]
        except Exception:
            return []

    async def get_directory_by_id(
        self, directory_id: str, db: Optional[AsyncSession] = None
    ) -> Optional[KnowledgeDirectoryModel]:
        async with get_async_db_context(db) as db:
            result = await db.execute(select(KnowledgeDirectory).filter_by(id=directory_id))
            directory = result.scalars().first()
            return KnowledgeDirectoryModel.model_validate(directory) if directory else None

    async def get_directory_breadcrumbs(
        self,
        directory_id: Optional[str],
        db: Optional[AsyncSession] = None,
    ) -> list[KnowledgeDirectoryModel]:
        """Walk up the parent chain to build breadcrumbs (root first)."""
        if not directory_id:
            return []

        async with get_async_db_context(db) as db:
            breadcrumbs = []
            current_id = directory_id
            seen = set()

            while current_id and current_id not in seen:
                seen.add(current_id)
                result = await db.execute(select(KnowledgeDirectory).filter_by(id=current_id))
                directory = result.scalars().first()
                if not directory:
                    break
                breadcrumbs.append(KnowledgeDirectoryModel.model_validate(directory))
                current_id = directory.parent_id

            breadcrumbs.reverse()  # root first
            return breadcrumbs

    async def rename_directory(
        self,
        directory_id: str,
        name: str,
        db: Optional[AsyncSession] = None,
    ) -> Optional[KnowledgeDirectoryModel]:
        async with get_async_db_context(db) as db:
            try:
                await db.execute(
                    update(KnowledgeDirectory).filter_by(id=directory_id).values(name=name, updated_at=int(time.time()))
                )
                await db.commit()
                return await self.get_directory_by_id(directory_id, db=db)
            except Exception as e:
                log.exception(e)
                return None

    async def move_directory(
        self,
        directory_id: str,
        new_parent_id: Optional[str],
        db: Optional[AsyncSession] = None,
    ) -> Optional[KnowledgeDirectoryModel]:
        """Move a directory to a new parent, with cycle detection."""
        async with get_async_db_context(db) as db:
            try:
                # Cycle detection: walk up from new_parent_id to ensure
                # we don't encounter directory_id
                if new_parent_id:
                    current = new_parent_id
                    seen = set()
                    while current and current not in seen:
                        if current == directory_id:
                            return None  # Would create a cycle
                        seen.add(current)
                        result = await db.execute(select(KnowledgeDirectory.parent_id).filter_by(id=current))
                        row = result.first()
                        current = row[0] if row else None

                await db.execute(
                    update(KnowledgeDirectory)
                    .filter_by(id=directory_id)
                    .values(parent_id=new_parent_id, updated_at=int(time.time()))
                )
                await db.commit()
                return await self.get_directory_by_id(directory_id, db=db)
            except Exception as e:
                log.exception(e)
                return None

    async def update_directory(
        self,
        directory_id: str,
        name: Optional[str] = None,
        parent_id: Optional[str] = '__unset__',
        db: Optional[AsyncSession] = None,
    ) -> Optional[KnowledgeDirectoryModel]:
        """Update directory name and/or parent. Pass parent_id=None to move to root."""
        # Handle move if parent_id is being changed
        if parent_id != '__unset__':
            result = await self.move_directory(directory_id, parent_id, db=db)
            if result is None:
                return None  # Cycle detected or error

        if name is not None:
            return await self.rename_directory(directory_id, name, db=db)

        return await self.get_directory_by_id(directory_id, db=db)

    async def delete_directory(
        self,
        directory_id: str,
        move_files_to_parent: bool = True,
        db: Optional[AsyncSession] = None,
    ) -> bool:
        """
        Delete a directory.
        - If move_files_to_parent=True: files move to parent dir (or root)
        - If move_files_to_parent=False: files are also deleted
        """
        async with get_async_db_context(db) as db:
            try:
                # Get the directory to find its parent
                result = await db.execute(select(KnowledgeDirectory).filter_by(id=directory_id))
                directory = result.scalars().first()
                if not directory:
                    return False

                parent_id = directory.parent_id

                if move_files_to_parent:
                    # Move files in this directory to its parent (or root)
                    await db.execute(
                        update(KnowledgeFile).filter_by(directory_id=directory_id).values(directory_id=parent_id)
                    )
                    # Recursively move files from all subdirectories too
                    await self._move_files_from_subtree(directory_id, parent_id, db=db)
                else:
                    # Delete files in this directory and all subdirectories
                    await self._delete_files_in_subtree(directory_id, db=db)

                # CASCADE on parent_id will handle deleting subdirectories
                await db.execute(delete(KnowledgeDirectory).filter_by(id=directory_id))
                await db.commit()
                return True
            except Exception as e:
                log.exception(e)
                return False

    async def _move_files_from_subtree(
        self,
        directory_id: str,
        target_directory_id: Optional[str],
        db: AsyncSession,
    ) -> None:
        """Recursively move all files from a directory subtree to the target."""
        result = await db.execute(select(KnowledgeDirectory.id).filter_by(parent_id=directory_id))
        child_ids = [row[0] for row in result.all()]

        for child_id in child_ids:
            await db.execute(
                update(KnowledgeFile).filter_by(directory_id=child_id).values(directory_id=target_directory_id)
            )
            await self._move_files_from_subtree(child_id, target_directory_id, db=db)

    async def _delete_files_in_subtree(
        self,
        directory_id: str,
        db: AsyncSession,
    ) -> None:
        """Recursively delete all files from a directory subtree."""
        await db.execute(delete(KnowledgeFile).filter_by(directory_id=directory_id))
        result = await db.execute(select(KnowledgeDirectory.id).filter_by(parent_id=directory_id))
        child_ids = [row[0] for row in result.all()]
        for child_id in child_ids:
            await self._delete_files_in_subtree(child_id, db=db)

    async def move_file_to_directory(
        self,
        knowledge_id: str,
        file_id: str,
        directory_id: Optional[str] = None,
        db: Optional[AsyncSession] = None,
    ) -> bool:
        """Move a file to a different directory within the same KB."""
        async with get_async_db_context(db) as db:
            try:
                await db.execute(
                    update(KnowledgeFile)
                    .filter_by(knowledge_id=knowledge_id, file_id=file_id)
                    .values(directory_id=directory_id, updated_at=int(time.time()))
                )
                await db.commit()
                return True
            except Exception as e:
                log.exception(e)
                return False


Knowledges = KnowledgeTable()
