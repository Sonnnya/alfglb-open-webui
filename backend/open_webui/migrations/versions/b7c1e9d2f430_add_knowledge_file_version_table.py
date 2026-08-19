"""Add knowledge_file_version table

Records every uploaded revision of a document and its approval status.

``knowledge_file`` keeps its existing meaning of "one row per document, whose
file_id is the published version" — no columns change — so this migration is
purely additive: if the backfill below were skipped entirely, every existing
knowledge base would still behave exactly as before. Existing documents are
backfilled as a single approved v1, because whatever is already in a knowledge
base is, by definition, already published to the vector store.

Revision ID: b7c1e9d2f430
Revises: 42e2978c7933
Create Date: 2026-08-18 18:40:00.000000

"""

import time
import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b7c1e9d2f430'
down_revision: Union[str, None] = '42e2978c7933'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if 'knowledge_file_version' in set(inspector.get_table_names()):
        return  # Already created — skip everything

    op.create_table(
        'knowledge_file_version',
        sa.Column('id', sa.Text(), primary_key=True),
        sa.Column(
            'knowledge_file_id',
            sa.Text(),
            sa.ForeignKey('knowledge_file.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('version_no', sa.Integer(), nullable=False),
        # UNIQUE: a file belongs to exactly one version, so joining the published
        # version back to its document stays 1:1 and the listing query cannot fan out.
        sa.Column(
            'file_id',
            sa.Text(),
            sa.ForeignKey('file.id', ondelete='CASCADE'),
            nullable=False,
            unique=True,
        ),
        sa.Column('author_id', sa.Text(), nullable=False),
        sa.Column('status', sa.Text(), nullable=False, server_default='pending'),
        sa.Column('comment', sa.Text(), nullable=True),
        sa.Column('review_note', sa.Text(), nullable=True),
        sa.Column('reviewed_by', sa.Text(), nullable=True),
        sa.Column('reviewed_at', sa.BigInteger(), nullable=True),
        sa.Column('created_at', sa.BigInteger(), nullable=False),
        # indexes
        sa.Index('ix_knowledge_file_version_knowledge_file_id', 'knowledge_file_id'),
        sa.Index('ix_knowledge_file_version_file_id', 'file_id'),
        # unique constraints
        sa.UniqueConstraint('knowledge_file_id', 'version_no', name='uq_knowledge_file_version_no'),
    )

    # ── Backfill: one approved v1 per existing document ──────────────────
    knowledge_file = sa.Table(
        'knowledge_file',
        sa.MetaData(),
        sa.Column('id', sa.Text()),
        sa.Column('file_id', sa.Text()),
        sa.Column('user_id', sa.Text()),
        sa.Column('created_at', sa.BigInteger()),
    )

    version = sa.Table(
        'knowledge_file_version',
        sa.MetaData(),
        sa.Column('id', sa.Text()),
        sa.Column('knowledge_file_id', sa.Text()),
        sa.Column('version_no', sa.Integer()),
        sa.Column('file_id', sa.Text()),
        sa.Column('author_id', sa.Text()),
        sa.Column('status', sa.Text()),
        sa.Column('comment', sa.Text()),
        sa.Column('review_note', sa.Text()),
        sa.Column('reviewed_by', sa.Text()),
        sa.Column('reviewed_at', sa.BigInteger()),
        sa.Column('created_at', sa.BigInteger()),
    )

    rows = conn.execute(
        sa.select(
            knowledge_file.c.id,
            knowledge_file.c.file_id,
            knowledge_file.c.user_id,
            knowledge_file.c.created_at,
        )
    ).fetchall()

    now = int(time.time())
    payload = [
        {
            'id': str(uuid.uuid4()),
            'knowledge_file_id': kf_id,
            'version_no': 1,
            'file_id': file_id,
            'author_id': user_id or '',
            # Already in the knowledge base means already published to the vector
            # store, so the pre-existing state maps to 'approved', not 'pending'.
            'status': 'approved',
            'comment': None,
            'review_note': None,
            'reviewed_by': None,
            'reviewed_at': created_at or now,
            'created_at': created_at or now,
        }
        for kf_id, file_id, user_id, created_at in rows
        if kf_id and file_id
    ]

    if payload:
        conn.execute(version.insert(), payload)


def downgrade() -> None:
    # knowledge_file was never altered, so dropping this table restores the exact
    # previous behaviour. Version history is lost, which is inherent to reverting.
    op.drop_table('knowledge_file_version')
