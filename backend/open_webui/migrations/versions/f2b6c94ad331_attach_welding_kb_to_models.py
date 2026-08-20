"""Attach the seeded welding knowledge base to every existing workspace model

The deployment has exactly one knowledge base and every model is meant to answer
from it, so rather than asking an admin to tick it on each model by hand this
backfills model.meta.knowledge once.

Scope is deliberately "rows that already exist in the model table". meta.knowledge
lives on that row, so a raw Ollama/OpenAI model that was never customised has
nowhere to carry it — giving those one would mean minting a model row per upstream
model, which would also make them all appear in Workspace → Models. Models created
*after* this migration do not inherit the attachment either; this is a one-time
backfill, not a policy.

The item shape mirrors what KnowledgeSelector emits (a spread of the knowledge
base plus type: 'collection'), trimmed to the keys anything actually reads:
`id` is what both retrieval paths resolve, `name` is what the chip in the model
editor renders, `description` keeps the editor's tooltip honest. Round-trips
through ModelEditor untouched — its normaliser only rewrites items carrying
`collection_name` or `collection_names`, which this has neither of.

Read-modify-write in Python rather than SQL JSON operators: model.meta is a
JSONField (internal/db.py:123), i.e. TEXT-backed on both SQLite and PostgreSQL,
so ->>/json_extract do not apply. Same reasoning as e5f83a2d1c94.

Idempotent — a model that already lists the base is left alone, so re-running
after a manual attach cannot produce a duplicate.

Revision ID: f2b6c94ad331
Revises: e5f83a2d1c94
Create Date: 2026-08-20 12:00:00.000000

"""

import json
import time
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f2b6c94ad331'
down_revision: Union[str, None] = 'e5f83a2d1c94'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Not imported from open_webui.config: a migration must keep describing the
# database as it was when written, and stay runnable if the constant is renamed.
WELDING_KB_ID = 'welding-kb'
WELDING_KB_NAME = 'База знаний по сварке'
WELDING_KB_DESCRIPTION = (
    'База знаний по сварке. Использовать каждый раз, когда нужна точная информация по сварке (т.е. всегда)'
)


def _model_table() -> sa.Table:
    return sa.table(
        'model',
        sa.column('id', sa.Text),
        sa.column('meta', sa.Text),
        sa.column('updated_at', sa.BigInteger),
    )


def upgrade() -> None:
    conn = op.get_bind()
    model = _model_table()

    # The knowledge base has to exist before anything is pointed at it. On a fresh
    # database this migration runs before the startup seeder, so there is simply
    # nothing to attach yet — and nothing to attach it to either.
    knowledge = sa.table('knowledge', sa.column('id', sa.Text))
    exists = conn.execute(sa.select(knowledge.c.id).where(knowledge.c.id == WELDING_KB_ID)).first()
    if not exists:
        return

    entry = {
        'id': WELDING_KB_ID,
        'name': WELDING_KB_NAME,
        'description': WELDING_KB_DESCRIPTION,
        'type': 'collection',
    }

    now = int(time.time())
    for model_id, raw_meta in conn.execute(sa.select(model.c.id, model.c.meta)).fetchall():
        try:
            meta = json.loads(raw_meta) if raw_meta else {}
        except (TypeError, ValueError):
            # A meta column that will not parse is not ours to repair; skipping it
            # loses an attachment, overwriting it would lose the model's settings.
            continue
        if not isinstance(meta, dict):
            continue

        attached = meta.get('knowledge')
        if not isinstance(attached, list):
            attached = []

        if any(isinstance(item, dict) and item.get('id') == WELDING_KB_ID for item in attached):
            continue

        meta['knowledge'] = [*attached, entry]
        conn.execute(model.update().where(model.c.id == model_id).values(meta=json.dumps(meta), updated_at=now))


def downgrade() -> None:
    conn = op.get_bind()
    model = _model_table()

    now = int(time.time())
    for model_id, raw_meta in conn.execute(sa.select(model.c.id, model.c.meta)).fetchall():
        try:
            meta = json.loads(raw_meta) if raw_meta else {}
        except (TypeError, ValueError):
            continue
        if not isinstance(meta, dict) or not isinstance(meta.get('knowledge'), list):
            continue

        remaining = [
            item for item in meta['knowledge'] if not (isinstance(item, dict) and item.get('id') == WELDING_KB_ID)
        ]
        if len(remaining) == len(meta['knowledge']):
            continue

        # Drop the key entirely when nothing is left, matching what ModelEditor
        # writes for a model with no knowledge (it deletes meta.knowledge).
        if remaining:
            meta['knowledge'] = remaining
        else:
            meta.pop('knowledge', None)

        conn.execute(model.update().where(model.c.id == model_id).values(meta=json.dumps(meta), updated_at=now))
