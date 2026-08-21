"""Put already-merged documents back into the folders they were uploaded into.

WHY THIS EXISTS
---------------
The first version of merge_knowledge_base.py cleared ``directory_id`` when it
moved a document between bases. That was right while the knowledge base screen
was a flat list and wrong the moment it became a file manager, and by then the
documents had already been moved on stage: they sit in the target base at the
root, and the row that said which folder they came from has been overwritten.

The mapping is recoverable anyway, and from the live database - no backup
needed. ``routers/files.py`` stores the whole upload metadata dict on the file
row (``file.meta['data']``), and the folder upload put ``directory_id`` in it.
The merge only ever rewrote ``knowledge_file``, so every one of those values is
still there, still pointing at the directory row in the *source* base.

So: read the original directory id off each file, mirror the source's folder
tree into the target, and repoint the documents. Nothing is re-embedded and no
file is touched - chunks live in a collection named after the knowledge base,
and the base is not changing.

WHAT IT NEEDS TO BE ABLE TO FINISH
----------------------------------
The source base's ``knowledge_directory`` rows, for the names and the nesting.
They survive if the merge ran WITHOUT ``--delete-source``. If the base was
deleted, its directory rows went with it (``ondelete='CASCADE'``) and only the
grouping is left - documents that shared a folder can still be identified, but
nothing knows what the folder was called. In that case restore the pre-merge
backup into any database the script can reach and pass ``--from-db``.

The report says which case you are in before anything is written.

Usage (inside the container):

    python -m scripts.restore_knowledge_dirs --source <old-id> --target welding-kb
    python -m scripts.restore_knowledge_dirs --source <old-id> --target welding-kb --apply

The first form only reports. Nothing is written without ``--apply``.
"""

import argparse
import asyncio
import logging
import sys
import time

import sqlalchemy as sa

from scripts.merge_knowledge_base import _mirror_directories

log = logging.getLogger('restore_knowledge_dirs')


def _original_directory_id(file) -> str | None:
    """The directory the file was uploaded into, off the untouched file row.

    ``meta['data']`` is the upload metadata dict verbatim, so this is the value
    the old folder-upload flow sent - not something derived after the fact.
    Absent for anything uploaded one file at a time, which is a normal answer
    and not an error.
    """
    if not file or not file.meta:
        return None
    data = file.meta.get('data') or {}
    directory_id = data.get('directory_id')
    return directory_id if isinstance(directory_id, str) and directory_id else None


async def _read_source_directories(db, source_id: str, from_db_url: str | None):
    """The source base's folder rows, from the live database or a backup.

    The backup is read with a plain synchronous engine: it is a foreign database
    that only has to be SELECTed from, and going through the app's async session
    machinery would mean pointing the whole application at it.
    """
    from open_webui.models.knowledge import KnowledgeDirectoryModel, Knowledges

    if not from_db_url:
        return await Knowledges.get_all_directories(source_id, db=db)

    engine = sa.create_engine(from_db_url)
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                sa.text(
                    'SELECT id, knowledge_id, parent_id, name, user_id, created_at, updated_at '
                    'FROM knowledge_directory WHERE knowledge_id = :k'
                ),
                {'k': source_id},
            ).mappings()
            return [KnowledgeDirectoryModel(**dict(row)) for row in rows]
    finally:
        engine.dispose()


async def _collect(db, target_id: str, source_directories):
    """Work out where each rootless document in the target belongs.

    Returns (recoverable, unfiled, foreign) - documents whose original folder is
    a known source folder, documents carrying no original folder at all, and
    documents naming a directory that is not in the source tree.
    """
    from open_webui.models.files import Files
    from open_webui.models.knowledge import KnowledgeFile, KnowledgeFileVersion

    source_ids = {directory.id for directory in source_directories}

    async def first_file_id(document) -> str | None:
        """The file whose upload metadata named the original folder: v1's.

        Not ``knowledge_file.file_id``, for two reasons. It is the *published*
        version, so it is NULL while a document still awaits its first approval -
        exactly the case for anything that was pending when the merge ran. And if
        the document has since gained a v2 through the new UI, that file was
        uploaded into this base and its metadata carries no old folder at all, so
        reading it would silently strand the document at the root.

        Falls back to the document's own file_id for a legacy row with no
        versions, though b7c1e9d2f430 + d4a71b3c9e52 mean there should be none.
        """
        result = await db.execute(
            sa.select(KnowledgeFileVersion.file_id)
            .filter(KnowledgeFileVersion.knowledge_file_id == document.id)
            .order_by(KnowledgeFileVersion.version_no.asc())
            .limit(1)
        )
        return result.scalars().first() or document.file_id

    # Only documents sitting at the root. One filed in a folder already is either
    # untouched by the bad merge or was put there deliberately afterwards through
    # the new UI, and moving it would undo somebody's filing.
    result = await db.execute(
        sa.select(KnowledgeFile).filter(
            KnowledgeFile.knowledge_id == target_id,
            KnowledgeFile.directory_id.is_(None),
        )
    )
    documents = list(result.scalars().all())

    recoverable, unfiled, foreign = [], [], []
    for document in documents:
        file_id = await first_file_id(document)
        file = await Files.get_file_by_id(file_id, db=db) if file_id else None
        original = _original_directory_id(file)
        if not original:
            unfiled.append(document)
        elif original in source_ids:
            recoverable.append((document, original))
        else:
            # Names a directory that is not in the source tree: the folder was
            # deleted before the merge, or the file came from somewhere else.
            foreign.append((document, original))
    return recoverable, unfiled, foreign


async def _refile(db, recoverable, directory_map):
    """Repoint each document at its mirrored folder, one UPDATE per folder."""
    from open_webui.models.knowledge import KnowledgeFile

    now = int(time.time())
    by_directory: dict[str, list[str]] = {}
    for document, original in recoverable:
        destination = directory_map.get(original)
        if destination:
            by_directory.setdefault(destination, []).append(document.id)

    for destination, document_ids in by_directory.items():
        await db.execute(
            sa.update(KnowledgeFile)
            .where(KnowledgeFile.id.in_(document_ids))
            .values(directory_id=destination, updated_at=now)
        )
    await db.commit()
    return sum(len(ids) for ids in by_directory.values())


async def main() -> int:
    parser = argparse.ArgumentParser(description='Restore folder placement lost by an earlier merge.')
    parser.add_argument('--source', required=True, help='the knowledge base the documents came FROM')
    parser.add_argument('--target', required=True, help='the knowledge base they are in NOW')
    parser.add_argument('--apply', action='store_true', help='write the changes (default: report only)')
    parser.add_argument(
        '--from-db',
        help='SQLAlchemy URL of a pre-merge backup to read the folder tree from, for when the source base was deleted',
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format='%(message)s')

    from open_webui.internal.db import get_async_db_context
    from open_webui.main import app
    from open_webui.models.knowledge import Knowledges
    from open_webui.models.users import Users

    async with app.router.lifespan_context(app):
        async with get_async_db_context() as db:
            target = await Knowledges.get_knowledge_by_id(args.target, db=db)
            if not target:
                print(f'ERROR: no knowledge base {args.target} in this database', file=sys.stderr)
                return 1

            source_directories = await _read_source_directories(db, args.source, args.from_db)
            print(f'source {args.source}: {len(source_directories)} folder(s)')
            if not source_directories:
                # The distinction that decides whether this can finish at all, so
                # it is spelled out rather than left as an empty list. Note the
                # third possibility below: an empty result also looks exactly like
                # this when --from-db points at a snapshot that does not actually
                # hold the rows, which is worth ruling out before concluding the
                # folders are gone for good.
                print('')
                print('Nothing to rebuild the tree from. Either the source id is wrong, or the merge')
                print('ran with --delete-source and took the folder rows with it. In the second case,')
                print('restore the pre-merge backup somewhere and re-run with --from-db <url>.')
                print('')
                print('Before concluding the folders are gone, confirm the snapshot really holds them:')
                print(f"  SELECT count(*) FROM knowledge_directory WHERE knowledge_id = '{args.source}';")
                print('A backup restored from the wrong dump - or copied out of a WAL-mode SQLite file')
                print('without its -wal sibling - answers 0 here and is indistinguishable from deletion.')
                return 1

            recoverable, unfiled, foreign = await _collect(db, args.target, source_directories)
            print(f'target {args.target}: {len(recoverable) + len(unfiled) + len(foreign)} document(s) at the root')
            print(f'  original folder recoverable: {len(recoverable)}')
            print(f'  never in a folder:           {len(unfiled)}')
            if foreign:
                print(f'  WARNING - folder not in the source tree, left at root: {len(foreign)}')
                for document, original in foreign:
                    print(f'    {document.id} -> {original}')

            actor = await Users.get_super_admin_user(db=db)
            if not actor:
                print('ERROR: no admin user found', file=sys.stderr)
                return 1

            _, created, reused, orphaned = await _mirror_directories(
                db, source_directories, args.target, actor.id, apply=False
            )
            print(f'folders: {created} to create, {reused} already in the target')
            if orphaned:
                print(f'  WARNING - unreachable folder(s), contents stay at root: {len(orphaned)}')

            if not args.apply:
                print('')
                print('Dry run. Re-run with --apply to restore the folders.')
                return 0

            print('')
            print('Mirroring the folder tree...')
            directory_map, created, _, _ = await _mirror_directories(
                db, source_directories, args.target, actor.id, apply=True
            )
            print(f'  {created} folder(s) created')

            moved = await _refile(db, recoverable, directory_map)
            print('')
            print(f'Done. {moved} document(s) put back in their folders.')
    return 0


if __name__ == '__main__':
    sys.exit(asyncio.run(main()))
