"""Turn off the sidebar chat folders on deployments that already stored the flag

`folders.enable` is a runtime config row, and Config.seed_defaults only inserts
keys that do not exist yet — existing values win, by design, so an admin's choice
survives a restart. That also means flipping the default in config.py alone does
nothing for a database that has already booted once: the row is there, set to
True, and stays True forever.

This flips it, once, and only where it is still the untouched default. Same shape
and same reasoning as e5f83a2d1c94, which flipped the tier groups' share target.

Upstream «Папки» group CHATS (tying them to a model, a prompt and a knowledge
base). This fork wants the word for the knowledge base's own directories, which
are knowledge_directory rows and have nothing to do with this flag. Nothing is
deleted — flipping the row back restores the sidebar section.

Revision ID: f7a4c81be225
Revises: f2b6c94ad331
Create Date: 2026-08-20 15:30:00.000000

"""

import json
import time
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f7a4c81be225'
down_revision: Union[str, None] = 'f2b6c94ad331'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CONFIG_KEY = 'folders.enable'


def _config_table() -> sa.Table:
    return sa.table(
        'config',
        sa.column('key', sa.Text),
        sa.column('value', sa.Text),
        sa.column('updated_at', sa.BigInteger),
    )


def _set(target: bool, expect: bool) -> None:
    conn = op.get_bind()
    config = _config_table()

    row = conn.execute(sa.select(config.c.value).where(config.c.key == CONFIG_KEY)).first()
    if row is None:
        # Never booted with this key: seed_defaults will insert the new default.
        return

    try:
        current = json.loads(row[0]) if row[0] is not None else None
    except (TypeError, ValueError):
        return

    # Only touch it while it still holds the value we are migrating away from —
    # an admin who has deliberately set it keeps their choice.
    if current is not expect:
        return

    conn.execute(
        config.update().where(config.c.key == CONFIG_KEY).values(value=json.dumps(target), updated_at=int(time.time()))
    )


def upgrade() -> None:
    _set(target=False, expect=True)


def downgrade() -> None:
    _set(target=True, expect=False)
