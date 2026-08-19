"""Backfill versions for documents that have none

The first version migration (b7c1e9d2f430) backfilled every knowledge_file row
that existed *at that moment*. Any document added afterwards through the old
add-file path — i.e. between that migration running and the versioned upload
code going live — got a knowledge_file row with no version rows at all, and the
registry query joins through versions, so those documents became invisible.

This repairs the gap. It is a data fix, not a schema change: it inserts one
version per document that has none, and touches nothing else.

A document that already has a published file is recorded as an approved v1 —
whatever is in a knowledge base is by definition already in the vector store,
and marking it pending would silently pull it away from the model.

Revision ID: d4a71b3c9e52
Revises: c8d2fa5b1067
Create Date: 2026-08-18 20:05:00.000000

"""

import time
import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd4a71b3c9e52'
down_revision: Union[str, None] = 'c8d2fa5b1067'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    knowledge_file = sa.table(
        'knowledge_file',
        sa.column('id', sa.Text),
        sa.column('file_id', sa.Text),
        sa.column('user_id', sa.Text),
        sa.column('created_at', sa.BigInteger),
    )
    version = sa.table(
        'knowledge_file_version',
        sa.column('id', sa.Text),
        sa.column('knowledge_file_id', sa.Text),
        sa.column('version_no', sa.Integer),
        sa.column('file_id', sa.Text),
        sa.column('author_id', sa.Text),
        sa.column('status', sa.Text),
        sa.column('reviewed_by', sa.Text),
        sa.column('reviewed_at', sa.BigInteger),
        sa.column('created_at', sa.BigInteger),
    )

    orphans = conn.execute(
        sa.select(
            knowledge_file.c.id,
            knowledge_file.c.file_id,
            knowledge_file.c.user_id,
            knowledge_file.c.created_at,
        ).where(~sa.exists(sa.select(version.c.id).where(version.c.knowledge_file_id == knowledge_file.c.id)))
    ).fetchall()

    now = int(time.time())
    payload = [
        {
            'id': str(uuid.uuid4()),
            'knowledge_file_id': kf_id,
            'version_no': 1,
            'file_id': file_id,
            'author_id': user_id or '',
            'status': 'approved',
            'reviewed_by': None,
            'reviewed_at': created_at or now,
            'created_at': created_at or now,
        }
        # A document with no published file and no version has nothing to point a
        # version row at; leave it for the outer join in search_documents_by_id.
        for kf_id, file_id, user_id, created_at in orphans
        if file_id
    ]

    if payload:
        conn.execute(version.insert(), payload)


def downgrade() -> None:
    # The rows this inserted are indistinguishable from those the first version
    # migration created, so there is nothing safe and specific to remove.
    pass
