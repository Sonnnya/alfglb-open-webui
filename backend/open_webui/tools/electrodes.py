"""
Electrode catalogue lookup for the Alfa Global deployment.

Answers "which electrode is like X" from a static, curated cross-reference table:
Alfa Global product <-> AWS <-> EN <-> ESAB / Bohler / Castolin / RU equivalents.

IMPORTANT: DO NOT IMPORT THIS MODULE DIRECTLY IN OTHER PARTS OF THE CODEBASE.
"""

import json
import logging
import re
from pathlib import Path

log = logging.getLogger(__name__)

# Ships inside the package on purpose: backend/data is gitignored, excluded by
# .dockerignore, and shadowed by the named volume in docker-compose.yml, so a
# catalogue kept there would be absent from every deployment.
CATALOG_PATH = Path(__file__).parent / 'data' / 'alfa_electrodes.json'

AG_COLUMN = 'Наименование материала AG'
DESIGNATION_COLUMNS = (AG_COLUMN, 'Обозначение по AWS', 'Обозначение по EN')
EQUIVALENT_COLUMNS = (
    'Материал ESAB',
    'Материалы Bohler',
    'Материалы Castolin',
    'Наименование РФ',
)
# `url` is deliberately absent: it is rendered as a link on the AG name instead
# of a ninth column, which is already more than a chat pane comfortably holds.
TABLE_COLUMNS = DESIGNATION_COLUMNS + EQUIVALENT_COLUMNS + ('Примечания',)

# 'Примечания' is a notes column by name only: 39 of its 43 filled cells hold
# GOST type designations ('Э-10Х25Н13Г2, Э-10Х25Н13Г2Б'), which is the spelling
# a Russian welder reaches for first. It is indexed as another cross-reference;
# the four cells that really are notes ('57-60 HRC') cost nothing to carry.
CROSS_REFERENCE_COLUMNS = EQUIVALENT_COLUMNS + ('Примечания',)

# Cyrillic letters that are visually identical to Latin ones. A user typing a
# designation inside a Russian sentence produces 'Е 309L-17' with a Cyrillic Е,
# which has to match the Latin 'E 309L-17' in the catalogue.
_HOMOGLYPHS = str.maketrans('АВЕКМНОРСТУХ', 'ABEKMHOPCTYX')

# AWS covering types. The same alloy with a different covering is exactly what
# "or an analogue" means here, so these are what a family match strips.
_COVERING_SUFFIXES = ('15', '16', '17')

_MIN_KEY_LENGTH = 3
_MIN_CONTAINED_LENGTH = 5
_MIN_PARTIAL_LENGTH = 4

_EXACT = 100
_EQUIVALENT = 90
_CONTAINED = 85
_FAMILY = 80
_PARTIAL = 60


def _normalize(value) -> str:
    """Fold to a comparable key: homoglyphs to Latin, then alphanumerics only.

    Cyrillic that is not a homoglyph drops out entirely ('НИИ-48Г' -> 'H48'),
    which is lossy but self-consistent: both the query and the catalogue go
    through this, and the rows returned carry the original text verbatim.
    """
    if value is None:
        return ''
    return re.sub(r'[^0-9A-Z]', '', str(value).upper().translate(_HOMOGLYPHS))


def _family(key: str) -> str:
    """Alloy family of a designation key: 'E309L17' -> 'E309L'.

    Only covering suffixes are stripped, so 'E6013' keeps its trailing 13 --
    that is a carbon-steel designation, not a covering type.
    """
    for suffix in _COVERING_SUFFIXES:
        if key.endswith(suffix) and len(key) > len(suffix) + 1:
            return key[: -len(suffix)]
    return ''


def _split_values(cell) -> list[str]:
    """A cell holds several products: 'OK GoldRox, OK 46.00'."""
    if not cell:
        return []
    return [part.strip() for part in str(cell).split(',') if part.strip()]


def _index_row(row: dict) -> dict:
    # 'AG E 309L-17' is the catalogue name for the AWS designation 'E 309L-17'.
    # The prefix must go, or a user typing the catalogue name would miss the AWS
    # column. It also matters for rows where the two disagree: 'AG E 310L-17'
    # carries the AWS designation 'E 310-17', without the L.
    ag_designation = re.sub(r'^AG\s+', '', row.get(AG_COLUMN) or '', flags=re.IGNORECASE)
    aws = row.get('Обозначение по AWS')

    designations = {_normalize(value) for value in [ag_designation, aws] + _split_values(row.get('Обозначение по EN'))}
    designations.discard('')

    # Families come from the AWS-shaped designations only -- the covering suffix
    # is an AWS convention, and an EN code ending in 15/16/17 would mean nothing.
    families = {_family(_normalize(value)) for value in (ag_designation, aws)}
    families.discard('')

    equivalents = set()
    for column in CROSS_REFERENCE_COLUMNS:
        for value in _split_values(row.get(column)):
            key = _normalize(value)
            if key:
                equivalents.add(key)

    return {
        'row': row,
        'designations': designations,
        'families': families,
        'equivalents': equivalents,
    }


_CATALOG: list[dict] | None = None


def _catalog() -> list[dict]:
    """Load and index the catalogue once per process."""
    global _CATALOG
    if _CATALOG is None:
        with open(CATALOG_PATH, encoding='utf-8') as f:
            _CATALOG = [_index_row(row) for row in json.load(f)]
    return _CATALOG


def _query_keys(query: str) -> set[str]:
    """Designation-shaped keys to try against the catalogue.

    A designation is routinely written with a space ('E 309L-17'), so adjacent
    token pairs are joined too: without that, a phrase passed verbatim yields
    only 'E' and '309L17' and never the designation itself.
    """
    tokens = query.split()
    keys = {_normalize(query)}
    for index, token in enumerate(tokens):
        keys.add(_normalize(token))
        if index + 1 < len(tokens):
            keys.add(_normalize(token + tokens[index + 1]))
    return {key for key in keys if len(key) >= _MIN_KEY_LENGTH}


def _score(entry: dict, query_norm: str, keys: set[str]) -> int:
    designations = entry['designations']
    equivalents = entry['equivalents']

    if designations & keys:
        return _EXACT
    if equivalents & keys:
        return _EQUIVALENT

    # The model may still pass a whole phrase. A designation long enough not to
    # occur by chance stays recognisable inside it.
    if any(len(value) >= _MIN_CONTAINED_LENGTH and value in query_norm for value in designations | equivalents):
        return _CONTAINED

    query_families = {family for family in (_family(key) for key in keys) if family}
    if entry['families'] & query_families:
        return _FAMILY

    # A partial key ('309L17' out of 'E 309L-17') still identifies a row, but a
    # key carrying no digit ('BOHLER') would match half the catalogue.
    for key in keys:
        if len(key) >= _MIN_PARTIAL_LENGTH and any(character.isdigit() for character in key):
            if any(key in value for value in designations | equivalents):
                return _PARTIAL

    return 0


def _cell(value) -> str:
    if value is None or not str(value).strip():
        return '—'
    # A pipe would end the column and a newline would end the row.
    return re.sub(r'\s+', ' ', str(value)).strip().replace('|', r'\|')


def _render_table(rows: list[dict]) -> str:
    lines = [
        f'| {" | ".join(TABLE_COLUMNS)} |',
        f'| {" | ".join("---" for _ in TABLE_COLUMNS)} |',
    ]
    for row in rows:
        cells = []
        for column in TABLE_COLUMNS:
            text = _cell(row.get(column))
            if column == AG_COLUMN and row.get('url'):
                text = f'[{text}]({row["url"]})'
            cells.append(text)
        lines.append(f'| {" | ".join(cells)} |')
    return '\n'.join(lines)


async def recommend_electrodes(query: str, count: int = 8) -> str:
    """
    Look up covered welding electrodes in the Alfa Global catalogue and return a
    cross-reference table of the matching products: their AWS and EN designations
    together with the equivalent products from ESAB, Bohler, Castolin and Russian
    manufacturers.

    Use this whenever the user names an electrode grade, asks which electrode to
    take, or asks for an analogue or an equivalent of one.

    :param query: The electrode designation on its own, e.g. "E 309L-17", "AG E 316L-16", "OK 67.45" or "BOHLER FOX A 7". Pass the designation, not the user's whole sentence.
    :param count: Maximum number of catalogue rows to return (default: 8)
    :return: JSON carrying a ready markdown table of the matching catalogue rows
    """
    try:
        catalog = _catalog()
    except Exception as e:
        log.exception(f'recommend_electrodes: cannot load the catalogue: {e}')
        return json.dumps({'error': 'Каталог электродов недоступен.'}, ensure_ascii=False)

    try:
        count = max(1, min(int(count), 25))
    except (TypeError, ValueError):
        count = 8

    query = (query or '').strip()
    if not query:
        return json.dumps(
            {'error': 'Не указана марка электрода для поиска.'},
            ensure_ascii=False,
        )

    query_norm = _normalize(query)
    keys = _query_keys(query)

    scored = []
    for position, entry in enumerate(catalog):
        score = _score(entry, query_norm, keys)
        if score:
            # Position keeps the catalogue's own order as the tie-break.
            scored.append((-score, position, entry['row']))
    scored.sort(key=lambda item: (item[0], item[1]))

    rows = [row for _, _, row in scored[:count]]

    if not rows:
        return json.dumps(
            {
                'query': query,
                'matched': 0,
                'message': 'В каталоге Альфа Глобал нет электрода, соответствующего запросу.',
                'catalogue': [entry['row'].get(AG_COLUMN) for entry in catalog],
                'instruction': (
                    'Сообщить пользователю, что в каталоге «Альфа Глобал» совпадений нет, '
                    'и предложить уточнить марку. НЕ выдумывать марки электродов, '
                    'НЕ рекомендовать продукцию других производителей и НЕ предлагать '
                    'ничего, кроме позиций из списка catalogue.'
                ),
            },
            ensure_ascii=False,
        )

    return json.dumps(
        {
            'query': query,
            'matched': len(rows),
            # The Alfa Global product and its catalogue page, lifted out of the
            # table so the model can name and link it in prose without having to
            # pick a URL back out of markdown link syntax. Six of the catalogue's
            # rows have no page at all, so `url` is present only when there is one
            # -- the instruction below is what stops a plausible one being invented.
            'products': [
                {'name': row.get(AG_COLUMN), **({'url': row['url']} if row.get('url') else {})} for row in rows
            ],
            'table_markdown': _render_table(rows),
            'instruction': (
                'Это каталог компании «Альфа Глобал», ассистентом которой ты являешься. '
                'Сначала назвать продукт «Альфа Глобал» из products — он идёт первым, '
                'потому что ближе всего к запросу — и оформить его ссылкой на url из '
                'products. Если у позиции нет url, назвать её просто текстом: НЕ выдумывать '
                'адрес страницы. Продукцию ESAB, Bohler, Castolin и российских производителей '
                'упоминать только после этого, но не отделять в отдельный список, без ссылок. '
                'Затем показать таблицу из table_markdown целиком и без изменений. '
                'Рекомендовать ТОЛЬКО те электроды, которые есть в таблице.'
            ),
        },
        ensure_ascii=False,
    )
