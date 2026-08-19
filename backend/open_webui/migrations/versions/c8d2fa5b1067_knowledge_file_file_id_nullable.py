"""Allow knowledge_file.file_id to be NULL

``knowledge_file`` is the document; its ``file_id`` is the *published* version.
A document whose only version is still awaiting approval therefore has no
published version, and NULL is how that is expressed.

This is what keeps unapproved content away from the model for free: every
consumer of ``knowledge_file.file_id`` is an inner join or an equality filter,
and both drop NULL rows without any code change. See
``Knowledges.get_files_by_id`` and the six other join sites.

Revision ID: c8d2fa5b1067
Revises: b7c1e9d2f430
Create Date: 2026-08-18 19:10:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c8d2fa5b1067'
down_revision: Union[str, None] = 'b7c1e9d2f430'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    columns = {c['name']: c for c in inspector.get_columns('knowledge_file')}
    if columns.get('file_id', {}).get('nullable'):
        return  # Already nullable — nothing to do

    # batch_alter_table so SQLite gets a table rebuild rather than an unsupported
    # ALTER COLUMN; on PostgreSQL this is a plain ALTER.
    with op.batch_alter_table('knowledge_file') as batch:
        batch.alter_column('file_id', existing_type=sa.Text(), nullable=True)


def downgrade() -> None:
    # Documents with no published version cannot be represented by the old schema.
    # Drop them rather than fail: their version rows cascade away with them, and
    # they were never visible to the model in the first place.
    conn = op.get_bind()

    knowledge_file = sa.Table(
        'knowledge_file',
        sa.MetaData(),
        sa.Column('id', sa.Text()),
        sa.Column('file_id', sa.Text()),
    )
    conn.execute(knowledge_file.delete().where(knowledge_file.c.file_id.is_(None)))

    with op.batch_alter_table('knowledge_file') as batch:
        batch.alter_column('file_id', existing_type=sa.Text(), nullable=False)
