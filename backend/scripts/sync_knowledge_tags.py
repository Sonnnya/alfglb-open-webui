"""Make the seeded tag vocabulary in the database match ``knowledge_taxonomy.py``.

``KnowledgeTags.seed_defaults`` is insert-if-absent, exactly like the group and
knowledge-base seeders: it adds what is missing and never touches what is there,
so an admin's relabelling survives every boot. That is the right default — a
seeder that rewrote rows on every start would undo people's edits silently, and
one that deleted them would take their tagging with it.

The cost is that a *revised* registry cannot land on its own. Two things go
stale, and neither is visible:

- **Changed rows.** An id present in both the old and the new registry keeps its
  old row. When the registry redefined ``#рд`` from «Руководящий документ» to
  «Ручная дуговая сварка», the database went on saying the former — the same id
  meaning two different things depending on where you read it.
- **Dropped rows.** A tag removed from the registry stays in the picker forever.

So reconciliation is this script: explicit, dry-run by default, and printing
every value it is about to overwrite. Running it IS the decision to prefer the
registry over whatever is in the database.

WHAT IT TOUCHES
---------------
Only rows carrying ``meta.system``, i.e. rows this repo seeded. A tag a
Мастер-эксперт minted through the UI has ``user_id`` set and no ``system`` flag;
it is theirs, it is not in the registry by definition, and it is never touched.

A retired tag still attached to documents is reported and **kept** unless
``--force``. Removing it would delete those attachments with no way to tell
afterwards which documents had carried it. Refreshing is always safe by
comparison — it changes wording, never attachments.

Join rows are deleted explicitly rather than through the ``ondelete='CASCADE'``
on ``knowledge_file_tag.tag_id``: SQLite honours that only with
``PRAGMA foreign_keys`` ON, so relying on it leaves orphan rows in dev and none
in the Postgres deployment — the divergence that once left version rows behind
when a folder was deleted with its contents.

Usage (inside the container):

    python -m scripts.sync_knowledge_tags
    python -m scripts.sync_knowledge_tags --apply

Nothing is written without ``--apply``.
"""

import argparse
import asyncio
import logging
import sys
import time

import sqlalchemy as sa

log = logging.getLogger('sync_knowledge_tags')


def _differences(tag, row: dict) -> list[tuple[str, object, object]]:
    """What the database says vs what the registry says, field by field."""
    out = []
    if tag.label != row['label']:
        out.append(('label', tag.label, row['label']))
    if tag.description != row.get('description'):
        out.append(('description', tag.description, row.get('description')))
    if (tag.meta or {}) != row.get('meta'):
        out.append(('meta', tag.meta, row.get('meta')))
    return out


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help='write the changes (default: dry run)')
    parser.add_argument(
        '--force',
        action='store_true',
        help='also retire tags that are still attached to documents, dropping those attachments',
    )
    args = parser.parse_args()

    from open_webui.internal.db import get_async_db_context
    from open_webui.knowledge_taxonomy import seed_tag_rows
    from open_webui.main import app
    from open_webui.models.knowledge_tags import KnowledgeFileTag, KnowledgeTag

    registry = {row['id']: row for row in seed_tag_rows()}

    async with app.router.lifespan_context(app):
        async with get_async_db_context() as db:
            result = await db.execute(sa.select(KnowledgeTag).order_by(KnowledgeTag.id.asc()))
            tags = result.scalars().all()

            counts = dict(
                (
                    await db.execute(
                        sa.select(
                            KnowledgeFileTag.tag_id,
                            sa.func.count(KnowledgeFileTag.knowledge_file_id),
                        ).group_by(KnowledgeFileTag.tag_id)
                    )
                ).all()
            )

            seeded = [t for t in tags if (t.meta or {}).get('system')]
            stale = [t for t in seeded if t.id not in registry]
            drifted = [(t, d) for t in seeded if t.id in registry and (d := _differences(t, registry[t.id]))]

            print(f'registry holds {len(registry)} tag(s); database holds {len(tags)} ({len(seeded)} seeded)')
            print('')

            print(f'to refresh: {len(drifted)}')
            for tag, diffs in drifted:
                print(f'  {tag.id}')
                for field, old, new in diffs:
                    print(f'    {field}:')
                    print(f'      was: {old}')
                    print(f'      now: {new}')

            unused = [t for t in stale if not counts.get(t.id)]
            in_use = [t for t in stale if counts.get(t.id)]

            print('')
            print(f'to retire: {len(unused)}')
            for tag in unused:
                print(f'  {tag.id}')

            if in_use:
                print('')
                verb = 'retired WITH their attachments' if args.force else 'still attached, KEPT'
                print(f'{verb}: {len(in_use)}')
                for tag in in_use:
                    print(f'  {tag.id}  ({counts[tag.id]} document(s))')
                if not args.force:
                    print('')
                    print('  Re-tag those documents first, or pass --force to drop the attachments.')

            doomed = unused + in_use if args.force else unused

            if not args.apply:
                print('')
                print('Dry run. Re-run with --apply to write these changes.')
                return 0
            if not doomed and not drifted:
                print('')
                print('Nothing to do.')
                return 0

            now = int(time.time())
            for tag, _ in drifted:
                row = registry[tag.id]
                await db.execute(
                    sa.update(KnowledgeTag)
                    .where(KnowledgeTag.id == tag.id)
                    .values(
                        label=row['label'],
                        description=row.get('description'),
                        meta=row.get('meta'),
                        updated_at=now,
                    )
                )

            if doomed:
                ids = [t.id for t in doomed]
                await db.execute(sa.delete(KnowledgeFileTag).where(KnowledgeFileTag.tag_id.in_(ids)))
                await db.execute(sa.delete(KnowledgeTag).where(KnowledgeTag.id.in_(ids)))

            await db.commit()

            print('')
            print(f'Done. {len(drifted)} tag(s) refreshed, {len(doomed)} retired.')
    return 0


if __name__ == '__main__':
    sys.exit(asyncio.run(main()))
