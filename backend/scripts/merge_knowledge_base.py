"""Move every document from one knowledge base into another, keeping approvals.

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
from typing import Optional

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


async def _report(db, source_id: str, target_id: str):
    """Pre-flight. Returns (movable, collisions, empty_content)."""
    from open_webui.models.files import Files

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
    print(f'  in a folder (flattened to root): {len([d for d in movable if d.directory_id])}')
    print(f'target {target_id}: {len(target_docs)} document(s) already present')
    if collisions:
        print(f'  SKIPPED - file already in target: {len(collisions)}')
        for document in collisions:
            print(f'    {document.id} (file {document.file_id})')
    if empty:
        print(f'  WARNING - no extracted text, will embed nothing: {len(empty)}')
        for document in empty:
            print(f'    {document.id} (file {document.file_id})')
    return movable, collisions, empty


async def _move(db, documents, target_id: str, reviewer_id: Optional[str]):
    from open_webui.models.knowledge import KnowledgeFile, KnowledgeFileVersion

    now = int(time.time())
    ids = [d.id for d in documents]
    await db.execute(
        sa.update(KnowledgeFile)
        .where(KnowledgeFile.id.in_(ids))
        .values(
            knowledge_id=target_id,
            # Folders belong to a base through knowledge_directory.knowledge_id, so
            # a moved document pointing at one of the source's folders would leave
            # the breadcrumb walk resolving into the base it just left. The registry
            # defaults to a flat list across folders, so root is not a loss.
            directory_id=None,
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

            movable, _collisions, _empty = await _report(db, args.source, args.target)

            # process_file looks a file up by owner unless the caller is an admin,
            # and the files being moved belong to whoever originally uploaded them.
            actor = await Users.get_super_admin_user(db=db)
            if not actor:
                print('ERROR: no admin user found; embedding needs one', file=sys.stderr)
                return 1
            reviewer_id = args.reviewer if args.reviewer is not None else actor.id

            if not args.apply:
                print('')
                print('Dry run. Re-run with --apply to perform the move.')
                return 0
            if not movable:
                print('')
                print('Nothing to move.')
                return 0

            print('')
            print(f'Moving {len(movable)} document(s)...')
            await _move(db, movable, args.target, reviewer_id or None)

            print('Re-embedding into the target collection...')
            failed = await _reembed(request, movable, args.target, actor, db)

            if args.delete_source:
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
