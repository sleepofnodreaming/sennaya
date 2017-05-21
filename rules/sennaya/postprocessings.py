#!/usr/local/bin/python3

import csv
import re
import os
import sys
import time

from answer import Answer
from collections import namedtuple
from readers import read_columns

_PARKING_TEMPLATES = [
    (r'\bподземный (стоянка|паркинг)\b', "устроить подземную парковку", lambda a, b: b),
    (r'\bпаркинг под площадь\b', "устроить подземную парковку", lambda a, b: b),
    (r'\wать парковка платный\b', "устроить платную парковку", lambda a, b: b),
    (r'\b(убирать|исчезать|запрещать) (бы )?парковка\b', "убрать парковку", lambda a, b: b),
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


class _HardcodeDictionary(object):
    """
    A collection of word lists.
    These lists are supposed to be extremely specific and it makes no sense to convert them to a dictionary.
    """
    APPROVAL_WORDS = [
        "организовывать",
        "вернуть",
        "сделать",
        "оставлять",
        "выпивать",
        "неплохо видеть",
        "поставить",
        "вкусный",
        "хороший",
        "качественный",
        "появляться",
        "устанавливать",
        "поставлять",
        "разрешать",
        "неплохо быть бы видеть",
        "открывать",
        "где можно",
        "отдать под",
        "приличный",
    ]

    FOOD_NAMES = [
        "автомат",
        "булочка",
        "выпечка",
        "еда",
        "кофе",
        "макдональдс",
        "мороженое",
        "общепит",
        "перекус",
        "стрит фуд",
        "стритфуд",
        "фаст - фуд",
        "фастфуд",
        "фудкорт",
        "шаверма",
        "шаурма",
    ]

    RESTAURANT_NAMES = [
        "бистро",
        "веранда",
        "зонтик",
        "кафе",
        "кафетерий",
        "кафешка",
        "кафешок",
        "ресторан",
        "терраса",
    ]

    GOOD_FOOD_MARKERS = [
        "to go",
        "кофе с себя",
        "выпечка",
        "мороженое",
        "здоровый еда",
        "ларек с кофе",
        "ларек с еда",
        "лавочка с кофе",
        "мобильный кофейня",

    ]

    TRADE = [
        "будочка",
        "киоск",
        "ларек",
        "ларёк",
        "магазин",
    ]


class TagNames(object):
    """
    All constants naming categories assigned to answers.
    """

    NO_CHANGE_REQUIRED = "Ничего не менять"

    TRADE_GENERAL = "Торговля"
    ALLOW_TRADE = "Разрешить организованную торговлю"
    FORBID_TRADE = "Запретить торговлю"

    PARKING_GENERAL = "Парковки"

    STREET_FOOD_GENERAL = "Уличная еда"
    ALLOW_STREET_FOOD = "Организовать продажу уличной еды"

    CAFE_GENERAL = "Кафе, рестораны"
    ALLOW_CAFE = "Открыть качественные кафе"

    PEAK_GENERAL = 'ТК Пик'


class Postprocs(object):
    """
    A class embracing methods trying to re-assign some answers to a more precise category.
    """

    dic = _HardcodeDictionary
    compiled_parking_templates = (lambda: [(re.compile(r), l, f) for r, l, f in _PARKING_TEMPLATES])()
    nonverbal_phrase_tags = {"A", "S", None, "PR", 'CONJ', "ADV"}

    SENTENCE_START = r'(?:((?:{trade}) с |быть(?: бы)? )(?:\w+?[оыи]й )?)?(?:{food_names})'.format(
        trade="|".join(_HardcodeDictionary.TRADE),
        food_names="|".join(_HardcodeDictionary.FOOD_NAMES)
    )
    FOOD_APPROVAL = "({})[^,().!]+?({})".format("|".join(dic.APPROVAL_WORDS), "|".join(dic.FOOD_NAMES))

    _sentence_start_re, _food_approval_re = re.compile(SENTENCE_START), re.compile(FOOD_APPROVAL)
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
    def _assign_headlines_food(cls, lemmas, pos_tags, additional_headlines):
        approval_label = "Организовать продажу уличной еды"
        for i in cls.dic.GOOD_FOOD_MARKERS:
            if i in lemmas:
                additional_headlines.add(approval_label)
                return
        if cls._food_approval_re.search(lemmas):
            additional_headlines.add(approval_label)
            return
        if cls._sentence_start_re.match(lemmas):
            additional_headlines.add(approval_label)
            return
        if cls.is_nonverbal(pos_tags) and not cls._simple_negation_re.search(lemmas):
            additional_headlines.add(approval_label)

    @classmethod
    def _assign_headlines_restaurants(cls, lemmas, pos_tags, additional_headlines):
        approval_label = TagNames.ALLOW_CAFE

        regex = r"({})[^,().!]+?({})".format("|".join(cls.dic.APPROVAL_WORDS), "|".join(cls.dic.RESTAURANT_NAMES))
        if re.search(regex, lemmas):
            additional_headlines.add(approval_label)
            return

        if cls.is_nonverbal(pos_tags) and not cls._simple_negation_re.search(lemmas):
            additional_headlines.add(approval_label)

    @classmethod
    def no_change_postproc(cls, answer, hls):
        if TagNames.NO_CHANGE_REQUIRED in hls:
            hls.clear()
            hls.add(TagNames.NO_CHANGE_REQUIRED)

    @classmethod
    def trade_postproc(cls, answer, hls):
        if TagNames.ALLOW_TRADE in hls or TagNames.FORBID_TRADE in hls:
            hls.discard(TagNames.TRADE_GENERAL)
        if TagNames.ALLOW_TRADE in hls and TagNames.FORBID_TRADE in hls:
            hls.add(TagNames.TRADE_GENERAL)
            hls.remove(TagNames.ALLOW_TRADE)
            hls.remove(TagNames.FORBID_TRADE)

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
    def street_food_postproc(cls, answer, hls):
        if TagNames.STREET_FOOD_GENERAL in hls:
            cls._assign_headlines_food(
                answer.get_lemmas(False, True),
                answer.pos_tags,
                hls
            )
            if TagNames.ALLOW_STREET_FOOD in hls:
                hls.remove(TagNames.STREET_FOOD_GENERAL)

    @classmethod
    def cafe_postproc(cls, answer: Answer, hls: set):
        if TagNames.CAFE_GENERAL in hls:
            cls._assign_headlines_restaurants(
                answer.get_lemmas(False, True),
                answer.pos_tags,
                hls
            )
            if TagNames.ALLOW_CAFE in hls:
                hls.discard(TagNames.CAFE_GENERAL)

    @classmethod
    def peak_postproc(cls, answer: Answer, hls: set):
        """
        Check whether a "ПИК" mall is mentioned in a text as a landmark or as a subject.

        :param answer: An Answer object.
        :param hls: A current set of headlines assigned to an answer.
        """
        words, pos_tags = answer.get_lemmas(False, False), answer.pos_tags
        if TagNames.PEAK_GENERAL in hls:
            try:
                start_index = peak_index = words.index("пик")
                while peak_index >= 0:
                    if pos_tags[peak_index] not in ["PR", "A", "ADV", "S"]:
                        if peak_index == start_index - 1 and pos_tags[peak_index] is None:
                            peak_index -= 1
                            continue  # ignoring quotes
                        return
                    if pos_tags[peak_index] == "PR":
                        hls.discard(TagNames.PEAK_GENERAL)
                        return
                    peak_index -= 1
            except ValueError:
                pass


POSTPROCESSING_SEQUENCE = [
    Postprocs.no_change_postproc,
    Postprocs.trade_postproc,
    Postprocs.parking_postproc,
    Postprocs.street_food_postproc,
    Postprocs.cafe_postproc,
    Postprocs.peak_postproc
]


QUESTIONED = {
    "Кафе, рестораны",
    "Уличная еда",
    "Парковки",
    "Торговля",
    "Транспорт",
    "Переходы",
    "Лавки",
    "?",
}