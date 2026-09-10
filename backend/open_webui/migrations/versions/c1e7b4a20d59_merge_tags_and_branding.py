"""Merge the `tags` and `branding` migration branches

Both branches were cut from f7a4c81be225 and each added exactly one revision, so
merging the git branches produced two Alembic heads:

    f7a4c81be225
      ├── a3f18c7d2b40  (tags)     create knowledge_tag / knowledge_file_tag
      └── ea91f7c2d4b8  (branding) flip ui.enable_community_sharing to False

`config.py:208` calls `command.upgrade(alembic_cfg, 'head')` — singular — which
raises MultipleHeads and aborts run_migrations on every boot. That blocks *all*
future migrations, not just these two.

This revision is an empty merge point: it joins the two heads so 'head' resolves
again. It has no upgrade/downgrade body because the branches are disjoint and
commutative — one creates two new tables, the other updates a single config row
behind a guard that only fires when the row still holds the old default. Neither
reads what the other writes, so no ordering or reconciliation is required.

Revision ID: c1e7b4a20d59
Revises: a3f18c7d2b40, ea91f7c2d4b8
Create Date: 2026-09-10 10:00:00.000000

"""

from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = 'c1e7b4a20d59'
down_revision: Union[str, Sequence[str], None] = ('a3f18c7d2b40', 'ea91f7c2d4b8')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
