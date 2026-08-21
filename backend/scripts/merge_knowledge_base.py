"""Move every document from one knowledge base into another, keeping approvals.

NOTE: !!!!CAUTION!!!! this thing deleted knowledge dir since it's cascade delete in ORM-model
fix goes with this commit but i won't test this exact version.

Written for the stage migration of the pre-fork «Сварка» base into the seeded
«База знаний по сварке», but takes both ids as arguments so it is not tied to
that one pair.

WHY A SCRIPT AND NOT AN ALEMBIC MIGRATION
-----------------------------------------
Two reasons. The source id is specific to one deployment, and baking it into the
permanent revision chain would make every future fresh database carry a step that
means nothing to it. And the move is not purely relational: the vector chunks live
in a collection named after the knowledge base id, so the content has to be
re-embedded into the target's collection, which needs the running app's embedding
function (``request.app.state.ef``). Hence the lifespan below.

WHAT ALREADY HOLDS BEFORE THIS RUNS
-----------------------------------
Documents added under the old code are plain ``knowledge_file`` rows with no
version history. Migrations b7c1e9d2f430 and d4a71b3c9e52 already gave each of
them an **approved v1** ``knowledge_file_version``, so they arrive in exactly the
shape the registry expects and no status has to be invented here.

FOLDERS COME ACROSS TOO
-----------------------
The source's ``knowledge_directory`` tree is mirrored into the target and each
document is repointed at its mirrored folder, so a base that was uploaded as a
directory tree still reads as one afterwards. Folders already present in the
target are reused rather than duplicated.

ORDER IS LOAD-BEARING
---------------------
The documents are repointed *before* anything is deleted. ``knowledge_file`` has
``ondelete='CASCADE'`` on ``knowledge_id``, enforced on PostgreSQL, so removing
the source base first would take all of its documents with it.

Usage (inside the container, where the app's dependencies live):

    python -m scripts.merge_knowledge_base --source <old-id> --target welding-kb
    python -m scripts.merge_knowledge_base --source <old-id> --target welding-kb --apply

The first form only reports. Nothing is written without ``--apply``.
"""

import argparse
import asyncio
import logging
import sys
import time
from types import SimpleNamespace

import sqlalchemy as sa

log = logging.getLogger('merge_knowledge_base')


async def _fetch_documents(db, knowledge_id: str):
    """Every document row in a base, published or not.

    Deliberately not get_files_by_id, which joins through file_id and so drops
    any document whose only version is still awaiting review.
    """
    from open_webui.models.knowledge import KnowledgeFile

    result = await db.execute(
        sa.select(KnowledgeFile).filter(KnowledgeFile.knowledge_id == knowledge_id).order_by(KnowledgeFile.created_at)
    )
    return list(result.scalars().all())


async def _report(db, source_id: str, target_id: str, actor_id: str):
    """Pre-flight. Returns (movable, collisions, empty_content)."""
    from open_webui.models.files import Files
    from open_webui.models.knowledge import Knowledges

    source_docs = await _fetch_documents(db, source_id)
    target_docs = await _fetch_documents(db, target_id)
    target_file_ids = {d.file_id for d in target_docs if d.file_id}

    # uq_knowledge_file_knowledge_file is (knowledge_id, file_id): a file already
    # published in the target would make the UPDATE fail for the whole batch.
    collision_ids = {d.id for d in source_docs if d.file_id and d.file_id in target_file_ids}
    collisions = [d for d in source_docs if d.id in collision_ids]
    movable = [d for d in source_docs if d.id not in collision_ids]

    # A file whose extracted text is empty embeds nothing. It would still render
    # as a perfectly normal approved document in the registry and return zero
    # chunks to the model, so it is worth seeing before the move, not after.
    empty = []
    for document in movable:
        if not document.file_id:
            continue
        file = await Files.get_file_by_id(document.file_id, db=db)
        if not file or not ((file.data or {}).get('content') or '').strip():
            empty.append(document)

    published = [d for d in movable if d.file_id]
    print(f'source {source_id}: {len(source_docs)} document(s)')
    print(f'  published (will be re-embedded): {len(published)}')
    print(f'  awaiting review (move only):     {len(movable) - len(published)}')
    print(f'target {target_id}: {len(target_docs)} document(s) already present')

    # The folder half of the plan, computed without writing anything. This is the
    # line that says whether the source has a tree at all, and it is the whole
    # point of running without --apply first.
    _, created, reused, orphaned = await _mirror_directories(
        db, await Knowledges.get_all_directories(source_id, db=db), target_id, actor_id, apply=False
    )
    in_folders = len([d for d in movable if d.directory_id])
    print(f'folders: {created} to create, {reused} already in the target')
    print(f'  document(s) that will keep their folder: {in_folders}')
    if orphaned:
        # A directory whose parent chain does not reach a root - a dangling
        # parent_id or a cycle. Its documents land at the target's root.
        print(f'  WARNING - unreachable folder(s), contents go to root: {len(orphaned)}')
        for directory in orphaned:
            print(f'    {directory.id} ({directory.name})')
    if collisions:
        print(f'  SKIPPED - file already in target: {len(collisions)}')
        for document in collisions:
            print(f'    {document.id} (file {document.file_id})')
    if empty:
        print(f'  WARNING - no extracted text, will embed nothing: {len(empty)}')
        for document in empty:
            print(f'    {document.id} (file {document.file_id})')
    return movable, collisions, empty


async def _mirror_directories(db, source_directories, target_id: str, actor_id: str, apply: bool):
    """Recreate the source base's folder tree inside the target.

    Takes the source rows rather than a knowledge id: restore_knowledge_dirs.py
    reads the same tree from a base whose documents have already been moved away,
    and a caller reading it out of a backup database has no live id to pass.

    Returns (mapping, created, reused, orphaned) where mapping is
    ``source directory id -> target directory id``, which _move uses to keep each
    document in the folder it was uploaded into.

    Folders belong to a base through ``knowledge_directory.knowledge_id``, so a
    moved document that kept its source ``directory_id`` would leave the
    breadcrumb walk resolving into the base it just left. The first version of
    this script therefore cleared it. That was right when the registry was a flat
    list; now that it is a file manager, flattening throws away the structure the
    documents were uploaded with - so the tree is mirrored instead.

    Existing folders in the target are REUSED, keyed on (parent, name), the same
    insert-if-absent discipline as the seeders. That is also what makes a re-run
    safe: create_directory commits per row, so a run that dies half way through
    would otherwise leave orphan folders behind and no clean way to retry.
    """
    from open_webui.models.knowledge import Knowledges

    target_directories = await Knowledges.get_all_directories(target_id, db=db)

    # (parent id or '', name) -> target directory id. uq_knowledge_directory_
    # knowledge_parent_name is exactly this key, so a hit here is a folder that
    # already exists and a miss is one that can be created.
    existing = {((d.parent_id or ''), d.name): d.id for d in target_directories}

    children_of: dict[str, list] = {}
    for directory in source_directories:
        children_of.setdefault(directory.parent_id or '', []).append(directory)

    mapping: dict[str, str] = {}
    created = 0
    reused = 0

    # Breadth-first from the roots. get_all_directories orders by name, which says
    # nothing about depth, so walking it directly would reach a child before its
    # parent had been mapped and silently drop that subtree to the root.
    queue = list(children_of.get('', []))
    seen: set[str] = set()
    while queue:
        directory = queue.pop(0)
        if directory.id in seen:
            continue
        seen.add(directory.id)

        parent = mapping.get(directory.parent_id) if directory.parent_id else None
        key = ((parent or ''), directory.name)

        if key in existing:
            mapping[directory.id] = existing[key]
            reused += 1
        elif apply:
            # user_id carries over: nothing gates a folder's rename or delete on
            # its owner (DirectoryRow gates on write access to the base), so this
            # is provenance rather than permission - but losing it for no reason
            # would be worse than keeping it.
            new_directory = await Knowledges.create_directory(
                knowledge_id=target_id,
                name=directory.name,
                user_id=directory.user_id or actor_id,
                parent_id=parent,
                db=db,
            )
            if not new_directory:
                # create_directory logs and returns None instead of raising, so an
                # unchecked failure here loses this folder AND every document under
                # it to the target's root - the "it ran fine, half the structure is
                # missing" outcome. Stop instead; the reuse above makes a retry safe.
                raise RuntimeError(f'could not create folder {directory.name!r} under {target_id}')
            existing[key] = new_directory.id
            mapping[directory.id] = new_directory.id
            created += 1
        else:
            # Dry run: nothing is written, but children still need a distinct
            # parent key or the counts below would be wrong. A fake id can never
            # collide with a real one in `existing`, so no false reuse.
            mapping[directory.id] = f'(new) {directory.id}'
            created += 1

        queue.extend(children_of.get(directory.id, []))

    orphaned = [d for d in source_directories if d.id not in mapping]
    return mapping, created, reused, orphaned


async def _move(db, documents, target_id: str, reviewer_id: str | None, directory_map: dict):
    from open_webui.models.knowledge import KnowledgeFile, KnowledgeFileVersion

    now = int(time.time())
    ids = [d.id for d in documents]

    # Grouped by destination folder rather than updated one document at a time: a
    # base has a handful of folders and can have thousands of documents. A source
    # folder missing from the map (unreachable parent) falls back to the root,
    # which is the old behaviour and is reported by _report.
    by_directory: dict[str | None, list[str]] = {}
    for document in documents:
        destination = directory_map.get(document.directory_id) if document.directory_id else None
        by_directory.setdefault(destination, []).append(document.id)

    for destination, document_ids in by_directory.items():
        await db.execute(
            sa.update(KnowledgeFile)
            .where(KnowledgeFile.id.in_(document_ids))
            .values(
                knowledge_id=target_id,
                directory_id=destination,
                updated_at=now,
            )
        )

    if reviewer_id:
        # Cosmetic only: the backfilled v1 rows are approved with reviewed_by NULL,
        # so «История» shows them approved with no «Проверил:». Naming the admin who
        # ran the migration makes them read like every other approved revision.
        await db.execute(
            sa.update(KnowledgeFileVersion)
            .where(
                KnowledgeFileVersion.knowledge_file_id.in_(ids),
                KnowledgeFileVersion.status == 'approved',
                KnowledgeFileVersion.reviewed_by.is_(None),
            )
            .values(reviewed_by=reviewer_id)
        )

    await db.commit()


async def _reembed(request, documents, target_id: str, actor, db):
    """Re-embed each published document into the target's collection.

    process_file with collection_name set never re-reads the file from storage -
    it reuses the ``file-{id}`` collection or the stored extracted text - so this
    does not depend on the original uploads still being on disk.
    """
    from open_webui.routers.retrieval import ProcessFileForm, process_file

    published = [d for d in documents if d.file_id]
    failed = []
    for index, document in enumerate(published, start=1):
        print(f'  embedding {index}/{len(published)}: {document.file_id}')
        try:
            await process_file(
                request,
                ProcessFileForm(file_id=document.file_id, collection_name=target_id),
                user=actor,
                db=db,
            )
        except Exception as e:
            log.error('failed to embed %s: %s', document.file_id, e)
            failed.append((document.file_id, str(e)))
    return failed


async def _drop_source(db, source_id: str):
    """Remove the emptied base: its collection, its metadata embedding, its row,
    and every reference to it left in a model's meta.knowledge.

    Mirrors DELETE /api/v1/knowledge/{id} rather than calling it, because that
    route refuses a meta.system base and needs an HTTP client. The model-meta
    sweep is the part that matters - a model still listing a base that no longer
    exists silently contributes nothing to retrieval.
    """
    from open_webui.models.knowledge import Knowledges, is_system_knowledge
    from open_webui.models.models import ModelForm, Models
    from open_webui.retrieval.vector.async_client import ASYNC_VECTOR_DB_CLIENT
    from open_webui.routers.knowledge import remove_knowledge_base_metadata_embedding

    # Say what the DATABASE will do, not just what this function does. Deleting
    # the knowledge row takes its whole subtree with it through ON DELETE CASCADE
    # (models/knowledge.py:78 and :115) - which is how the folder names were lost
    # the first time this ran. Nothing in Python is involved, so nothing in Python
    # can report it after the fact; it has to be counted before.
    directories = await Knowledges.get_all_directories(source_id, db=db)
    remaining = await _fetch_documents(db, source_id)
    print(f'  cascade will also delete {len(directories)} folder row(s) and {len(remaining)} document row(s)')

    # The same refusal DELETE /knowledge/{id} makes, and for the same reason: a
    # seeded base is not the operator's to remove. Reachable by getting --source
    # and --target the wrong way round, which would otherwise delete welding-kb
    # after emptying it into the old base.
    source = await Knowledges.get_knowledge_by_id(source_id, db=db)
    if is_system_knowledge(source):
        print(f'REFUSING to delete {source_id}: it is a seeded (meta.system) base.', file=sys.stderr)
        return

    for model in await Models.get_all_models(db=db):
        attached = (getattr(model.meta, 'knowledge', None) or []) if model.meta else []
        remaining = [item for item in attached if item.get('id') != source_id]
        if len(remaining) != len(attached):
            print(f'  detaching from model {model.id}')
            model.meta.knowledge = remaining
            await Models.update_model_by_id(model.id, ModelForm(**model.model_dump()), db=db)

    try:
        await ASYNC_VECTOR_DB_CLIENT.delete_collection(collection_name=source_id)
    except Exception as e:
        log.debug('no collection to drop for %s: %s', source_id, e)

    await remove_knowledge_base_metadata_embedding(source_id)
    await Knowledges.delete_knowledge_by_id(id=source_id, db=db)


async def main() -> int:
    parser = argparse.ArgumentParser(description='Merge one knowledge base into another.')
    parser.add_argument('--source', required=True, help='knowledge base id to move documents out of')
    parser.add_argument('--target', required=True, help='knowledge base id to move them into')
    parser.add_argument('--apply', action='store_true', help='write the changes (default: report only)')
    parser.add_argument(
        '--delete-source',
        action='store_true',
        help='after moving, delete the emptied base and detach it from every model',
    )
    parser.add_argument(
        '--reviewer',
        help='user id to record as reviewer on migrated approvals (default: the first admin)',
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format='%(message)s')

    from open_webui.internal.db import get_async_db_context
    from open_webui.main import app
    from open_webui.models.knowledge import Knowledges
    from open_webui.models.users import Users

    async with app.router.lifespan_context(app):
        request = SimpleNamespace(app=app)

        async with get_async_db_context() as db:
            source = await Knowledges.get_knowledge_by_id(args.source, db=db)
            target = await Knowledges.get_knowledge_by_id(args.target, db=db)
            if not source:
                print(f'ERROR: no knowledge base {args.source} in this database', file=sys.stderr)
                return 1
            if not target:
                print(f'ERROR: no knowledge base {args.target} in this database', file=sys.stderr)
                return 1
            print(f'«{source.name}» -> «{target.name}»')
            print('')

            # process_file looks a file up by owner unless the caller is an admin,
            # and the files being moved belong to whoever originally uploaded them.
            # Resolved before the report because mirroring the folder tree needs a
            # fallback owner for any directory row missing one.
            actor = await Users.get_super_admin_user(db=db)
            if not actor:
                print('ERROR: no admin user found; embedding needs one', file=sys.stderr)
                return 1
            reviewer_id = args.reviewer if args.reviewer is not None else actor.id

            movable = (await _report(db, args.source, args.target, actor.id))[0]

            if not args.apply:
                print('')
                print('Dry run. Re-run with --apply to perform the move.')
                return 0
            print('')
            # Folders first, and BEFORE the "nothing to move" exit below. A document
            # cannot be repointed at a folder that does not exist yet; and on a re-run
            # every document has already moved, so returning early here would mean a
            # run that died part way through could never finish its tree. This is also
            # the last moment the source tree can be read: --delete-source drops the
            # source's directory rows with it (knowledge_directory.knowledge_id is
            # ondelete=CASCADE).
            print('Mirroring the folder tree...')
            directory_map, created, _, _ = await _mirror_directories(
                db,
                await Knowledges.get_all_directories(args.source, db=db),
                args.target,
                actor.id,
                apply=True,
            )
            print(f'  {created} folder(s) created')

            failed = []
            if movable:
                print(f'Moving {len(movable)} document(s)...')
                await _move(db, movable, args.target, reviewer_id or None, directory_map)

                print('Re-embedding into the target collection...')
                failed = await _reembed(request, movable, args.target, actor, db)
            else:
                print('No documents to move.')

            if args.delete_source:
                if movable:
                    # THE GUARD. Moving is reversible; deleting the source is not,
                    # and it takes the source's folder rows with it through
                    # ON DELETE CASCADE - which is exactly how the folder names
                    # were lost the first time this script ran on stage, in a
                    # single --apply --delete-source invocation.
                    #
                    # So the two halves cannot share a run any more. Move, look at
                    # the result in the UI, then re-run the same command: with
                    # nothing left to move, the delete goes ahead.
                    print('')
                    print(f'NOT deleting {args.source}: this run just moved {len(movable)} document(s).')
                    print("That delete is irreversible and cascades to the source's folder rows,")
                    print('so nothing can put them back. Check the documents in the UI first, then')
                    print('re-run this exact command - with nothing left to move it will delete.')
                else:
                    print(f'Removing the emptied base {args.source}...')
                    await _drop_source(db, args.source)

            print('')
            print(f'Done. {len(movable) - len(failed)} document(s) moved and embedded.')
            if failed:
                print(f'{len(failed)} failed to embed (rows were still moved):')
                for file_id, error in failed:
                    print(f'  {file_id}: {error}')
                return 1
    return 0


if __name__ == '__main__':
    sys.exit(asyncio.run(main()))
