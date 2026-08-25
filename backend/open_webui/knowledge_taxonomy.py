"""The seeded tag vocabulary for the welding knowledge base.

Transcribed verbatim from the company's «Единый реестр канонических тегов»
(`Tag_Dictionary_v4_1.md`) — 18 canonical tags in the four headings that file
groups them under. That document is the authority: it is the only source that
states, per tag, the standardized term, the ISO/AWS/ASTM code, the synonyms an
AI should accept, and the wordings that are «недопустимо».

WHY NOT THE FULL «СИСТЕМАТИКА ЗНАНИЙ» v12
------------------------------------------
v12 (`index (4).md`, and the Obsidian vault skeleton) lists 171 tags but carries
no synonyms, no codes and no glosses — it is an outline, not a registry. It also
spells `#рд` twice, once as «Ручная дуговая сварка» (Ур. 3) and once as
«Руководящий документ» (Ур. 7), which cannot both be a primary key. The registry
resolves that: `#рд` is the welding process, and there is no document-type tag.

Seeding the registry rather than the outline means the vocabulary an expert sees
is exactly the vocabulary that has been curated. Growing it is a deliberate act:
a Мастер-эксперт mints a tag, or this file gains a row when the registry does.

IDS ARE VERBATIM, AND FLAT
--------------------------
`#узк` stays `узк`, not `контроль/узк`. The expert maintains an Obsidian vault
whose folders carry these exact names, and documents are written referring to
them; inventing a path prefix here would mean the two stop matching for no gain.

The schema still supports paths (the id IS the path — see models/knowledge_tags)
and a prefix filter still works, so a future `сварка/дуговая/рд` costs nothing.
Nothing in this file uses that yet.

The four headings live in ``meta.group``. They are a picker heading only — not
part of the tag, not addressable, and safe to reword.

WHAT `meta` CARRIES
-------------------
- ``system``     — protects a seeded row from deletion, as on knowledge and group.
- ``group``      — the heading above, for the picker.
- ``code``       — «Код / Шифр»: ISO / AWS / ASTM / ГОСТ, verbatim.
- ``aliases``    — «Синонимы и алиасы (для ИИ)». Stored for tag-aware retrieval:
                   a query saying «УЗД» or «эхо-метод» has to reach `#узк`.
                   **Nothing reads this yet** — that is the next step.
- ``deprecated`` — «Недопустимо (Ндп)»: wordings the expert rejects. Kept apart
                   from `aliases` on purpose. A retrieval layer may want to match
                   them and warn; a picker must never suggest them.

`label` is what a picker row shows; the chip on a document shows the id with a
leading `#`. `description` is the «Стандартизованный термин» verbatim.

Ids, labels and descriptions are Russian and stay that way: this is user-facing
vocabulary typed by Russian-speaking experts, and it is database content, which
i18n cannot reach (same reasoning as the Russian tier-group names in
config.TIER_GROUPS).
"""

# group -> ordered {id: (label, standardized term, code, aliases, deprecated)}
# The group is only a heading for the picker; it is not part of the tag.
SEED_KNOWLEDGE_TAGS: dict[str, dict[str, tuple[str, str, str, tuple[str, ...], tuple[str, ...]]]] = {
    'Технологии, оборудование, материалы': {
        'рд': (
            'Ручная дуговая сварка',
            'Ручная дуговая сварка покрытыми электродами',
            'ISO: 111 / AWS: SMAW',
            ('ММА', 'ручник'),
            ('штучник', 'stick welding'),
        ),
        'мп': (
            'Механизированная сварка',
            'Механизированная дуговая сварка сплошной проволокой',
            'ISO: 135 / AWS: GMAW',
            ('полуавтомат', 'MAG', 'MIG'),
            ('полуавтоматика', 'wire welding'),
        ),
        'рад': (
            'Аргонодуговая сварка',
            'Дуговая сварка неплавящимся электродом в инертном газе',
            'ISO: 141 / AWS: GTAW',
            ('аргонодуговая', 'аргон'),
            ('TIG welding', 'Heliarc'),
        ),
        'проволока_сварочная': (
            'Сварочная проволока',
            'Проволока для плавящегося электрода или присадочного металла',
            'ГОСТ Р 58765 / AWS: Electrode',
            ('сварочная проволока', 'присадка'),
            (),
        ),
        'оборудование_дуговой_сварки': (
            'Оборудование дуговой сварки',
            'Источники питания для дуговой сварки',
            'ТН ВЭД: 8515',
            ('инвертор', 'выпрямитель', 'аппарат'),
            ('сварочник',),
        ),
    },
    'Контроль и диагностика': {
        'вик': (
            'ВИК',
            'Визуально-оптический метод контроля',
            'ГОСТ Р 56542 / AWS: VT',
            ('визуальный контроль', 'обмер'),
            ('внешний осмотр',),
        ),
        'узк': (
            'УЗК',
            'Акустический (ультразвуковой) метод контроля',
            'ГОСТ Р 56542 / ASTM E164 / AWS: UT',
            ('УЗК', 'УЗД', 'эхо-метод'),
            ('ультразвук',),
        ),
        'рк': (
            'РК',
            'Радиографический метод контроля',
            'ГОСТ Р 56542 / ASTM E94 / AWS: RT',
            ('рентген', 'просвечивание'),
            ('рентгенодефектоскопия',),
        ),
        'пвк': (
            'ПВК',
            'Капиллярный контроль (проникающими веществами)',
            'ГОСТ Р 56542 / ASTM E165 / AWS: PT',
            ('цветная дефектоскопия', 'ЦД', 'пенетрант'),
            ('мел-керосин', 'dye penetrant'),
        ),
        'мк_магнитопорошковый': (
            'МК магнитопорошковый',
            'Магнитопорошковый метод контроля',
            'ГОСТ Р 56542 / ASTM E709 / AWS: MT',
            ('МПД', 'МПК', 'магнитная суспензия'),
            ('магнитная дефектоскопия', 'magnaflux'),
        ),
        'испытания_статические': (
            'Испытания статические',
            'Механические статические испытания на растяжение',
            'ASTM E8',
            ('испытания на разрыв',),
            (),
        ),
    },
    'Дефекты и материаловедение': {
        'трещины': (
            'Трещины',
            'Трещина (Crack)',
            'ISO: 100',
            ('микротрещина', 'горячая трещина'),
            (),
        ),
        'пористость': (
            'Пористость',
            'Газовая пора (Porosity)',
            'ISO: 2011',
            ('пора', 'свищ', 'цепочка пор'),
            ('дутик', 'раковина'),
        ),
        'дефекты_сплавления': (
            'Дефекты сплавления',
            'Непровар / Несплавление (Incomplete fusion)',
            'ISO: 401, 402',
            ('отсутствие провара', 'непровар корня'),
            ('недовар',),
        ),
        'дефекты_формы': (
            'Дефекты формы',
            'Подрез (Undercut) / Наплыв (Overlap)',
            'ISO: 501, 506',
            ('краевой подрез', 'утяжина'),
            (),
        ),
    },
    'Объекты применения и нормативы': {
        'нгдо': (
            'НГДО',
            'Нефтегазодобывающее оборудование',
            'НАКС: НГДО',
            ('нефтепровод', 'газопровод', 'резервуар'),
            (),
        ),
        'asme_bpvc': (
            'ASME BPVC',
            'Boiler and Pressure Vessel Code',
            'ASME BPVC',
            ('код ASME', 'зарубежные котлы'),
            (),
        ),
        'сварщик': (
            'Сварщик',
            'Сварщик ручной сварки / Сварщик-оператор',
            'НАКС / ISO 9606',
            ('сварной',),
            (),
        ),
    },
}


def seed_tag_rows() -> list[dict]:
    """Flatten the taxonomy into rows for KnowledgeTags.seed_defaults().

    Empty `aliases` / `deprecated` are omitted rather than stored as `[]`, so a
    row's meta says only what the registry actually states about it.
    """
    rows = []
    for group_index, (group, tags) in enumerate(SEED_KNOWLEDGE_TAGS.items()):
        for tag_id, (label, term, code, aliases, deprecated) in tags.items():
            # `group_order` exists because the API returns tags sorted by id, which
            # says nothing about which heading comes first. Without it the picker
            # orders its sections by whichever group happened to own the
            # alphabetically-first tag — «Объекты» above «Технологии». This keeps
            # the picker reading in the order the registry is written in.
            meta = {'system': True, 'group': group, 'group_order': group_index}
            if code:
                meta['code'] = code
            if aliases:
                meta['aliases'] = list(aliases)
            if deprecated:
                meta['deprecated'] = list(deprecated)
            rows.append({'id': tag_id, 'label': label, 'description': term, 'meta': meta})
    return rows


def seeded_tag_ids() -> set[str]:
    """Every id this file seeds — used to retire tags dropped from the registry."""
    return {tag_id for tags in SEED_KNOWLEDGE_TAGS.values() for tag_id in tags}
