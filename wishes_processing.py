#!/usr/local/bin/python3

import csv
import re
import os
from answer import Answer
from like_processing import read_columns


PARKING_TEMPLATES = [
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


class HardcodeDictionary(object):
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
    dic = HardcodeDictionary
    compiled_parking_templates = (lambda: [(re.compile(r), l, f) for r, l, f in PARKING_TEMPLATES])()
    nonverbal_phrase_tags = {"A", "S", None, "PR", 'CONJ', "ADV"}

    SENTENCE_START = r'(?:((?:{trade}) с |быть(?: бы)? )(?:\w+?[оыи]й )?)?(?:{food_names})'.format(
        trade="|".join(HardcodeDictionary.TRADE),
        food_names="|".join(HardcodeDictionary.FOOD_NAMES)
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
    def cafe_postproc(cls, answer, hls):
        if TagNames.CAFE_GENERAL in hls:
            cls._assign_headlines_restaurants(
                answer.get_lemmas(False, True),
                answer.pos_tags,
                hls
            )
            if TagNames.ALLOW_CAFE in hls:
                hls.discard(TagNames.CAFE_GENERAL)

    @classmethod
    def peak_postproc(cls, answer, hls):
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


def iter_column(fn, col_number):
    return (Answer(text) for _, text in read_columns(fn, col_number))


def parse_args():
    import argparse
    parser = argparse.ArgumentParser(description="A script classifying respondents' answers using a dictionary.")
    parser.add_argument("csv", type=str, metavar="PATH", help="A path to a file to process.")
    parser.add_argument("column", type=int, metavar="NUM", help="A number of column to process.")
    parser.add_argument("dic", type=str, metavar="PATH", help="A path to a dictionary to use.")
    parser.add_argument("-d", "--delimiter", type=str, default="\t", metavar="SYMBOL",
                        help="A symbol to use as a delimiter in the output.")
    parsed = parser.parse_args()
    parsed.csv = os.path.expanduser(os.path.abspath(parsed.csv))
    parsed.dic = os.path.expanduser(os.path.abspath(parsed.dic))
    assert parsed.column >= 0
    assert os.path.isfile(parsed.csv) and os.path.isfile(parsed.dic)
    assert len(parsed.delimiter) == 1
    return parsed


if __name__ == "__main__":
    args = parse_args()

    postproc_seq = [
        Postprocs.no_change_postproc,
        Postprocs.trade_postproc,
        Postprocs.parking_postproc,
        Postprocs.street_food_postproc,
        Postprocs.cafe_postproc,
        Postprocs.peak_postproc
    ]

    matches = {}
    regexes = {}
    with open(args.dic) as kwf:
        reader = csv.reader(kwf, delimiter=",")
        for line in reader:
            hl, *kws = line
            for kw in kws:
                if kw:
                    matches[kw] = hl
                    regexes[kw] = re.compile(r'\b{}\b'.format(kw))

    results = []
    all_tags = set()

    for answer_instance in iter_column(args.csv, args.column):
        lemmas_text = answer_instance.get_lemmas(skip_punct=False, as_string=True)
        hls = set()
        for m in matches:
            if regexes[m].search(lemmas_text):
                hls.add(matches[m])

        for postproc in postproc_seq:
            postproc(answer_instance, hls)

        results.append((answer_instance.source, hls))
        all_tags |= hls

    import sys

    for i in sorted(all_tags):
        print(i, file=sys.stderr)

    header_tagging = sorted(all_tags)
    header = ["ID", "Исходный текст"] + header_tagging

    with open("output_clear.csv", "w") as clear_file, open("output_questioned.csv", "w") as questioned_file, open(
            "output_trash.csv", "w") as trash_file:
        c_writer = csv.writer(clear_file, delimiter=args.delimiter, quoting=csv.QUOTE_MINIMAL)
        q_writer = csv.writer(questioned_file, delimiter=args.delimiter, quoting=csv.QUOTE_MINIMAL)
        t_writer = csv.writer(trash_file, delimiter=args.delimiter, quoting=csv.QUOTE_MINIMAL)

        # c_writer.writerow(header)
        # q_writer.writerow(header)
        # t_writer.writerow(header)

        for num, (answer, tags) in enumerate(results):
            if not tags or "?" in tags and len(tags) == 1:
                active_writer = t_writer
            elif tags & QUESTIONED:
                active_writer = q_writer
            else:
                active_writer = c_writer
            line = [str(num + 2), answer] + sorted(tags) + [""] * (
                len(header_tagging) - len(tags))  # ["" if i not in tags else i for i in header_tagging]
            active_writer.writerow(line)
