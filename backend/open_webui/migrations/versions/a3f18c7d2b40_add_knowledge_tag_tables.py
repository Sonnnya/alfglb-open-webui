"""add knowledge_tag and knowledge_file_tag tables

Two tables, no changes to existing ones. The vocabulary itself is seeded at
startup by KnowledgeTags.seed_defaults (config.seed_knowledge_tags), not here:
the tag list is content that admins and Мастер-эксперт can edit afterwards, and
baking it into the revision chain would mean every future edit fought a
migration that wants to reassert it.

Revision ID: a3f18c7d2b40
Revises: f7a4c81be225
Create Date: 2026-08-21 14:10:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'a3f18c7d2b40'
down_revision: Union[str, None] = 'f7a4c81be225'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    existing_tables = set(sa.inspect(conn).get_table_names())

    if 'knowledge_tag' not in existing_tables:
        op.create_table(
            'knowledge_tag',
            # The id IS the path ('сварка/лучевая/лазерная'), so a subtree is a
            # prefix query and a tag has exactly one canonical spelling.
            sa.Column('id', sa.Text(), nullable=False),
            sa.Column('label', sa.Text(), nullable=False),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('user_id', sa.Text(), nullable=True),
            sa.Column('meta', sa.JSON(), nullable=True),
            sa.Column('created_at', sa.BigInteger(), nullable=False),
            sa.Column('updated_at', sa.BigInteger(), nullable=False),
            sa.PrimaryKeyConstraint('id'),
        )

    if 'knowledge_file_tag' not in existing_tables:
        op.create_table(
            'knowledge_file_tag',
            sa.Column('knowledge_file_id', sa.Text(), nullable=False),
            sa.Column('tag_id', sa.Text(), nullable=False),
            sa.Column('user_id', sa.Text(), nullable=False),
            sa.Column('created_at', sa.BigInteger(), nullable=False),
            sa.ForeignKeyConstraint(['knowledge_file_id'], ['knowledge_file.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['tag_id'], ['knowledge_tag.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('knowledge_file_id', 'tag_id', name='pk_knowledge_file_tag'),
        )
        op.create_index('ix_knowledge_file_tag_tag_id', 'knowledge_file_tag', ['tag_id'])


def downgrade() -> None:
    conn = op.get_bind()
    existing_tables = set(sa.inspect(conn).get_table_names())

    if 'knowledge_file_tag' in existing_tables:
        op.drop_index('ix_knowledge_file_tag_tag_id', table_name='knowledge_file_tag')
        op.drop_table('knowledge_file_tag')
    if 'knowledge_tag' in existing_tables:
        op.drop_table('knowledge_tag')
