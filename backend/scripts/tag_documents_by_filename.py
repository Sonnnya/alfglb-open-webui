"""Propose tags for existing documents from what their filenames already say.

The corpus arrived with its classification half-written into the filenames —
``ГОСТ_Р_71988-2025.pdf``, ``СНиП III-18-75.docx``, ``Мустафин Ф.М. - Сварка
трубопроводов.pdf``. Tagging ninety-odd of those by hand from a blank slate is
hours of clicking for information the strings already carry.

So this proposes; people correct. It is a starting point, not an authority:
every rule below is a keyword match on a filename, which is exactly as reliable
as filenames are.

WHAT IT WILL NOT DO
-------------------
- Invent tags. Every rule targets an id that must already exist in
  ``knowledge_tag``; a rule pointing at a missing tag is reported and skipped,
  so a trimmed taxonomy cannot silently mint vocabulary through the back door.
- Overwrite. A document that already carries tags is left alone unless
  ``--retag`` is passed, because a human's tagging outranks a keyword match.
- Guess quietly. The dry run prints every proposal, document by document.

Usage (inside the container):

    python -m scripts.tag_documents_by_filename --target welding-kb
    python -m scripts.tag_documents_by_filename --target welding-kb --apply

Nothing is written without ``--apply``.
"""

import argparse
import asyncio
import logging
import re
import sys

import sqlalchemy as sa

log = logging.getLogger('tag_documents_by_filename')


# tag id -> patterns that imply it. Matched case-insensitively against the
# filename. Deliberately conservative: a rule that fires on half the corpus is
# worse than no rule, because someone has to undo it by hand.
#
# Ordered by how strongly the string implies the tag, which is only documentation
# — every matching rule contributes.
FILENAME_RULES: dict[str, list[str]] = {
    # ── Технологии, оборудование, материалы ──
    # NOT a bare r'\bрд\b': the corpus is full of «РД 03-615-03» and similar
    # руководящие документы, and the registry has no document-type tag, so a
    # bare match would file every one of them as manual arc welding.
    'рд': [r'\bрдс\b', r'\bмма\b', r'\bmma\b', r'\bsmaw\b', r'ручн\w*\s+дугов', r'покрыт\w*\s+электрод'],
    'мп': [r'механизированн\w*\s+\w*\s*сварк', r'полуавтомат', r'\bmag\b', r'\bmig\b', r'\bgmaw\b'],
    'рад': [r'\bрад\b', r'аргонодугов', r'\btig\b', r'\bgtaw\b', r'неплавящ\w*\s+электрод'],
    'проволока_сварочная': [
        r'сварочн\w*\s+проволок',
        r'порошков\w*\s+проволок',
        r'сплошн\w*\s+проволок',
        r'присадочн\w*\s+(проволок|металл|пруток)',
    ],
    'оборудование_дуговой_сварки': [
        r'источник\w*\s+питания',
        r'сварочн\w*\s+(инвертор|выпрямител|аппарат|источник)',
        r'\bинвертор',
        r'выпрямител',
    ],
    # ── Контроль и диагностика ──
    'вик': [r'\bвик\b', r'визуальн\w*\s+и\s+измерительн', r'визуально[-\s]?оптическ', r'визуальн\w*\s+контрол'],
    'узк': [
        r'\bузк\b',
        r'\bузд\b',
        r'ультразвуков\w*\s+контрол',
        r'ультразвуков\w*\s+дефектоскоп',
        r'эхо[-\s]?метод',
    ],
    'рк': [r'\bрк\b', r'радиографич', r'рентген', r'просвечиван'],
    'пвк': [
        r'\bпвк\b',
        r'капиллярн\w*\s+контрол',
        r'проникающ\w*\s+веществ',
        r'цветн\w*\s+дефектоскоп',
        r'пенетрант',
    ],
    'мк_магнитопорошковый': [r'магнитопорошков', r'\bмпд\b', r'\bмпк\b', r'магнитн\w*\s+суспенз'],
    'испытания_статические': [
        r'испытани\w*\s+на\s+растяжен',
        r'испытани\w*\s+на\s+разрыв',
        r'статическ\w*\s+испытани',
    ],
    # ── Дефекты и материаловедение ──
    'трещины': [r'трещин'],
    'пористость': [r'пористост', r'газов\w*\s+пор', r'\bсвищ'],
    'дефекты_сплавления': [r'непровар', r'несплавлен', r'отсутстви\w*\s+провара'],
    'дефекты_формы': [r'подрез', r'наплыв', r'утяжин', r'дефект\w*\s+формы'],
    # ── Объекты применения и нормативы ──
    'нгдо': [
        r'\bнгдо\b',
        r'нефтегаз',
        r'нефтепровод',
        r'газопровод',
        r'магистральн\w*\s+трубопровод',
        r'резервуар',
    ],
    # NOT a bare r'\basme\b', for the same reason as рд above: «ASME B31.3» and
    # «ASME IX» are not the Boiler and Pressure Vessel Code, and the registry has
    # no generic #asme tag to catch them.
    'asme_bpvc': [r'\bbpvc\b'],
    'сварщик': [r'сварщик', r'\biso\s*9606\b'],
}

COMPILED = {tag_id: [re.compile(p, re.IGNORECASE) for p in patterns] for tag_id, patterns in FILENAME_RULES.items()}


def haystack(filename: str) -> str:
    """The filename in a form word-boundary patterns can actually match.

    Underscores are word characters to `re`, so \bгост\b does NOT match
    "ГОСТ_Р_71988-2025.pdf" — there is no boundary between "Т" and "_". Since
    exactly that naming style is all over this corpus, separators are flattened
    to spaces before any rule is tried.
    """
    return filename.replace('_', ' ')


def propose(filename: str, known_tags: set[str]) -> list[str]:
    """Tags implied by one filename, restricted to tags that actually exist."""
    text = haystack(filename)
    return sorted(
        tag_id
        for tag_id, patterns in COMPILED.items()
        if tag_id in known_tags and any(p.search(text) for p in patterns)
    )


async def _documents_with_filenames(db, knowledge_id: str):
    """(document, filename, current tag ids) for every document in a base.

    The filename comes from v1 where there is one — the original upload — which
    is also the name that carries the classification. A later revision is often
    named «...v2 итог.docx» and says nothing.
    """
    from open_webui.models.files import File
    from open_webui.models.knowledge import KnowledgeFile, KnowledgeFileVersion
    from open_webui.models.knowledge_tags import KnowledgeFileTag

    first_version = (
        sa.select(
            KnowledgeFileVersion.knowledge_file_id.label('kf_id'),
            sa.func.min(KnowledgeFileVersion.version_no).label('min_no'),
        )
        .group_by(KnowledgeFileVersion.knowledge_file_id)
        .subquery()
    )
    version = sa.orm.aliased(KnowledgeFileVersion)

    rows = (
        await db.execute(
            sa.select(KnowledgeFile, File.filename)
            .outerjoin(first_version, first_version.c.kf_id == KnowledgeFile.id)
            .outerjoin(
                version,
                sa.and_(
                    version.knowledge_file_id == KnowledgeFile.id,
                    version.version_no == first_version.c.min_no,
                ),
            )
            .outerjoin(File, File.id == sa.func.coalesce(version.file_id, KnowledgeFile.file_id))
            .filter(KnowledgeFile.knowledge_id == knowledge_id)
            .order_by(KnowledgeFile.created_at)
        )
    ).all()

    existing = {}
    for document_id, tag_id in (
        await db.execute(sa.select(KnowledgeFileTag.knowledge_file_id, KnowledgeFileTag.tag_id))
    ).all():
        existing.setdefault(document_id, set()).add(tag_id)

    return [(document, filename, existing.get(document.id, set())) for document, filename in rows]


async def main() -> int:
    parser = argparse.ArgumentParser(description='Propose document tags from filenames.')
    parser.add_argument('--target', required=True, help='knowledge base id to tag')
    parser.add_argument('--apply', action='store_true', help='write the tags (default: report only)')
    parser.add_argument(
        '--retag',
        action='store_true',
        help='also touch documents that already carry tags (default: leave them alone)',
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format='%(message)s')

    from open_webui.internal.db import get_async_db_context
    from open_webui.main import app
    from open_webui.models.knowledge import Knowledges
    from open_webui.models.knowledge_tags import KnowledgeTags
    from open_webui.models.users import Users

    async with app.router.lifespan_context(app):
        async with get_async_db_context() as db:
            target = await Knowledges.get_knowledge_by_id(args.target, db=db)
            if not target:
                print(f'ERROR: no knowledge base {args.target} in this database', file=sys.stderr)
                return 1

            known_tags = {tag.id for tag in await KnowledgeTags.get_tags(db=db)}
            missing = sorted(set(FILENAME_RULES) - known_tags)
            if missing:
                # Loud, because a trimmed taxonomy silently disabling a third of
                # the rules would look like the filenames simply matched nothing.
                print(f'{len(missing)} rule(s) target a tag that does not exist and are skipped:')
                for tag_id in missing:
                    print(f'  {tag_id}')
                print('')

            documents = await _documents_with_filenames(db, args.target)
            print(f'{args.target}: {len(documents)} document(s)')

            planned: list[tuple[str, str, list[str]]] = []
            skipped_tagged = 0
            unmatched = []
            for document, filename, current in documents:
                if current and not args.retag:
                    skipped_tagged += 1
                    continue
                if not filename:
                    continue
                proposed = propose(filename, known_tags)
                if not proposed:
                    unmatched.append(filename)
                    continue
                # --retag adds to what is there rather than replacing it: the
                # point is to enrich a partly-tagged corpus, not to overrule the
                # person who tagged it.
                merged = sorted(set(proposed) | current)
                if merged != sorted(current):
                    planned.append((document.id, filename, merged))

            print(f'  already tagged, left alone: {skipped_tagged}')
            print(f'  no rule matched:            {len(unmatched)}')
            print(f'  will be tagged:             {len(planned)}')
            print('')

            for _, filename, tags in planned:
                print(f'  {filename}')
                print(f'    -> {" ".join("#" + t for t in tags)}')

            if unmatched:
                print('')
                print('No rule matched these — they need a human:')
                for filename in unmatched:
                    print(f'  {filename}')

            if not args.apply:
                print('')
                print('Dry run. Re-run with --apply to write these tags.')
                return 0
            if not planned:
                print('')
                print('Nothing to do.')
                return 0

            actor = await Users.get_super_admin_user(db=db)
            if not actor:
                print('ERROR: no admin user found', file=sys.stderr)
                return 1

            print('')
            for document_id, _, tags in planned:
                await KnowledgeTags.set_document_tags(document_id, tags, actor.id, db=db)
            print(f'Done. {len(planned)} document(s) tagged.')
    return 0


if __name__ == '__main__':
    sys.exit(asyncio.run(main()))
