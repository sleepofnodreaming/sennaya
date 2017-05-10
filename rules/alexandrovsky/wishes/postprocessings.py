import re

from answer import Answer

PARKING_TEMPLATES = [
    (r'\bподземный (стоянка|паркинг)\b', "устроить подземную парковку", lambda a, b: b),
    (r'\bпаркинг под площадь\b', "устроить подземную парковку", lambda a, b: b),
    (r'\wать парковка платный\b', "устроить платную парковку", lambda a, b: b),
    (r'\b(убирать|исчезать|запрещать|ограничивать) (бы )?парковка\b', "убрать парковку", lambda a, b: b),
    (
        r'\b(?:организов(?:ыв)?ать|устр(?:ои|аива)ть|не убирать|сделать|нужный|создание) (?:бы )?(\w+ый )?парковка\b',
        "устроить {}парковку", lambda m, l: l.format((m.group(1)[:-3] + "ую ") if m.group(1) is not None else "")),
    (r'\b(?:расширять|оставлять|увеличивать) (?:бы )?(\w+ый )?парковка\b',
     "расширить {}парковку", lambda m, l: l.format((m.group(1)[:-3] + "ую ") if m.group(1) is not None else "")),
    (r'\bмного парковочный место\b', "расширить парковку", lambda a, b: b),
    (r'\bплатный парковка\b', "устроить платную парковку", lambda a, b: b),
    (r'\b(бесплатный|открытый) парковка\b', "устроить бесплатную парковку", lambda a, b: b),
    (r'^(хороший |удобный |перехватывать )?парковка$', "устроить парковку", lambda a, b: b),
    (r'^парковка\s*[,.]', "устроить парковку", lambda a, b: b),
    (r'[,.] *парковка$', "устроить парковку", lambda a, b: b),
    (r'[,.] *парковка *[,.]', "устроить парковку", lambda a, b: b),
    (r'(парковка расширять|много парковка|дополнительный парковка|увеличивать количество место парковка)',
     "расширить парковку", lambda a, b: b),
    (r'(убирать с земля парковка|подземный парковка|перенести парковка под земля)', "устроить подземную парковку",
     lambda a, b: b),
]

QUESTIONED = {
    "Парковки",
    "Переходы",
    "Зоопарк",
    "Набережная",
    "Мост",
    "Транспорт",
}


class HardcodeDictionary(object):
    """
    A collection of word lists.

    These lists are supposed to be extremely specific and it makes no sense to convert them to a dictionary.
    """


    REMOVAL_NAMES = [
        "вместо",
        "убирать",
        "удалять",
        "закрывать",
        "ликвидировать",
        "вывозить",
    ]

    STOP_TRAFFIC = [
        "заблокировать",
        "запрещать",
        "ограничивать",
        "убирать",
        "устранение",
        "закрывать въезд",
        "исключать",
        "перекрывать"
    ]

    GUNS = {
        "артиллерия",
        "протока",
        "проток",
        "арсенал",
        "артиллерийский",
        "кронверк",
    }


class TagNames(object):
    """
    All constants naming categories assigned to answers.
    """

    NO_CHANGE_REQUIRED = "Ничего не менять"
    PARKING_GENERAL = "Парковки"
    ZOO = 'Зоопарк'
    EMBANKMENT = "Набережная"
    EMBANKMENT_RENOVATION = "Благоустроить набережную"
    BRIDGE = "Мост"
    BRIDGE_TO_ARTILLERY = "Мостики к Артиллерийскому музею"
    TRAFFIC = "Транспорт"
    STOP_TRAFFIC = "Ограничить въезд автотранспорта"


class Postprocs(object):
    """
    A class embracing methods trying to re-assign some answers to a more precise category.
    """

    dic = HardcodeDictionary
    compiled_parking_templates = (lambda: [(re.compile(r), l, f) for r, l, f in PARKING_TEMPLATES])()
    nonverbal_phrase_tags = {"A", "S", None, "PR", 'CONJ', "ADV"}

    _simple_negation_re = re.compile(r"\bнет?\b")

    @classmethod
    def is_nonverbal(cls, pos_tags):
        return not (set(pos_tags) - cls.nonverbal_phrase_tags)

    @classmethod
    def _assign_headlines_parking(cls, lemmas, pos_tags, hl_set):
        for regex, label, func in cls.compiled_parking_templates:
            m = regex.search(lemmas)
            if m:
                hl_set.add(func(m, label))
                break
        else:
            if cls.is_nonverbal(pos_tags) and not cls._simple_negation_re.search(lemmas):
                if not "вело" in lemmas:
                    hl_set.add("устроить парковку")

    @classmethod
    def _assign_headlines_zoo(cls, lemmas, pos_tags, additional_headlines):
        approval_label = "Закрыть зоопарк"

        regex = r"({})[^,().!]+?({})".format("|".join(cls.dic.REMOVAL_NAMES), "(зоопарк|зоосад)")
        if re.search(regex, lemmas):
            additional_headlines.add(approval_label)
            return


    @classmethod
    def no_change_postproc(cls, answer, hls):
        if TagNames.NO_CHANGE_REQUIRED in hls:
            if len(hls) > 1:
                hls.discard(TagNames.NO_CHANGE_REQUIRED)

    @classmethod
    def parking_postproc(cls, answer, hls):
        if TagNames.PARKING_GENERAL in hls:
            additional_headlines = set()
            cls._assign_headlines_parking(
                answer.get_lemmas(False, True),
                answer.pos_tags,
                additional_headlines
            )
            if additional_headlines:
                hls.remove(TagNames.PARKING_GENERAL)
                hls.update({i.capitalize() for i in additional_headlines})

    @classmethod
    def zoo_postproc(cls, answer: Answer, hls: set):
        if TagNames.ZOO in hls:
            cls._assign_headlines_zoo(
                answer.get_lemmas(False, True).lower(),
                answer.pos_tags,
                hls
            )
            hls.discard(TagNames.ZOO)

    @classmethod
    def embankment_processing(cls, answer: Answer, hls: set):
        if TagNames.EMBANKMENT_RENOVATION in hls:
            hls.discard(TagNames.EMBANKMENT)


    @classmethod
    def bridge_processing(cls, answer: Answer, hls: set):
        if TagNames.BRIDGE in hls:
            if set(i.lower() for i in answer.get_lemmas(False, False)) & cls.dic.GUNS:
                hls.discard(TagNames.BRIDGE)
                hls.add(TagNames.BRIDGE_TO_ARTILLERY)

    @classmethod
    def traffic_processing(self, answer: Answer, hls: set):
        if TagNames.TRAFFIC in hls:
            if set(i.lower() for i in answer.get_lemmas(False, False)) & set(self.dic.STOP_TRAFFIC):
                hls.discard(TagNames.TRAFFIC)
                hls.add(TagNames.STOP_TRAFFIC)


POSTPROCESSING_SEQUENCE = [
        Postprocs.no_change_postproc,
        Postprocs.parking_postproc,
        Postprocs.zoo_postproc,
        Postprocs.bridge_processing,
        Postprocs.traffic_processing,

    ]
