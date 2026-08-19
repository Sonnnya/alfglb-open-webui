"""Set the tier groups' share target to «Никто»

TIER_GROUPS now seeds `data.config.share = False`, but seeding is
insert-if-absent — a deployment where the Эксперт / Мастер-эксперт rows already
exist keeps whatever `_ensure_default_share_config` gave them at first boot,
which is the global default 'members'. This brings those rows in line.

Only rows still carrying that untouched default are changed: an admin who has
deliberately picked a value in the group form keeps it. Unlike the keys under
`permissions`, `share` is not re-asserted on every boot, so this runs once.

Revision ID: e5f83a2d1c94
Revises: d4a71b3c9e52
Create Date: 2026-08-19 12:00:00.000000

"""

import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e5f83a2d1c94'
down_revision: Union[str, None] = 'd4a71b3c9e52'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TIER_GROUP_IDS = ('expert', 'master-expert')

# The value _ensure_default_share_config writes when DEFAULT_GROUP_SHARE_PERMISSION
# is unset. Only this is overwritten; anything else is a deliberate choice.
UNTOUCHED_DEFAULT = 'members'


def _rows(conn, group):
    """Read `data` per row. Done in Python rather than a JSON UPDATE so the same
    migration runs on SQLite and Postgres, whose JSON operators disagree."""
    return conn.execute(sa.select(group.c.id, group.c.data).where(group.c.id.in_(TIER_GROUP_IDS))).fetchall()


def _apply(conn, group, target, only_when):
    for group_id, data in _rows(conn, group):
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except (TypeError, ValueError):
                continue
        if not isinstance(data, dict):
            data = {}

        config = data.get('config')
        if not isinstance(config, dict):
            config = {}

        if config.get('share') != only_when:
            continue

        config['share'] = target
        data['config'] = config
        conn.execute(sa.update(group).where(group.c.id == group_id).values(data=data))


def upgrade() -> None:
    group = sa.table('group', sa.column('id', sa.Text), sa.column('data', sa.JSON))
    _apply(op.get_bind(), group, target=False, only_when=UNTOUCHED_DEFAULT)


def downgrade() -> None:
    group = sa.table('group', sa.column('id', sa.Text), sa.column('data', sa.JSON))
    _apply(op.get_bind(), group, target=UNTOUCHED_DEFAULT, only_when=False)
