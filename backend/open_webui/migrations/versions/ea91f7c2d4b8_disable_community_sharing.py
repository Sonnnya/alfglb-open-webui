"""Turn off the Open WebUI Community surfaces on deployments that already stored the flag

`ui.enable_community_sharing` is a runtime config row, and Config.seed_defaults only
inserts keys that do not exist yet — existing values win, by design, so an admin's
choice survives a restart. That also means flipping the default in config.py alone
does nothing for a database that has already booted once: the row is there, set to
True, and stays True forever.

This flips it, once, and only where it is still the untouched default. Same shape and
same reasoning as f7a4c81be225, which turned off the sidebar chat folders.

The flag is a single gate over thirteen frontend surfaces: ShareChatModal's «Share to
Open WebUI Community», RateComment, the share entries in ModelItemMenu / ModelMenu /
PromptMenu / ToolMenu, the «Made by Open WebUI Community» / «Discover a ...» sections
on Functions / Models / Prompts / Tools, and the usage-stats sync modal that
routes/+layout.svelte:1273 renders. All of them send an internal tool's users out to a
public service, which is not wanted for this deployment.

Nothing is deleted — flipping the row back, or ENABLE_COMMUNITY_SHARING=true on a
fresh database, restores every one of them.

Revision ID: ea91f7c2d4b8
Revises: f7a4c81be225
Create Date: 2026-09-07 12:00:00.000000

"""

import json
import time
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'ea91f7c2d4b8'
down_revision: Union[str, None] = 'f7a4c81be225'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CONFIG_KEY = 'ui.enable_community_sharing'


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
