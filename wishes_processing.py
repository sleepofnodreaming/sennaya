import csv
from nltk import collocations
from nltk import tokenize
from nltk import pos_tag

DST_COL = 6

from collections import Counter
import re

from pymystem3 import Mystem

matches = {}
regexes = {}
with open("wishes-dic-2016-12-12.csv") as kwf:
    reader = csv.reader(kwf, delimiter=",")
    for line in reader:
        hl, *kws = line
        for kw in kws:
            if kw:
                matches[kw] = hl
                regexes[kw] = re.compile(r'\b{}\b'.format(kw))

PARKING_TEMPLATES = {
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
}



def assign_headlines_parking(lemmas, hl_set):
    for parking_tmpl in PARKING_TEMPLATES:
        regex, label, func = parking_tmpl
        m = re.search(regex, lemmas)
        if m:
            hl_set.add(func(m, label))
            break
    else:
        if not ({pos(i) for i in lemmas.split()} - {"A", "S", None, "PR", 'CONJ', "ADV"}) and not re.search(r"\bнет?\b", lemmas):
            if not "вело" in lemmas:
                hl_set.add("устроить парковку")


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

FOOD_NAMES = "шаверма,стрит фуд,стритфуд,выпечка,шаурма,фастфуд,общепит,макдональдс,мороженое,булочка,автомат,кофе,фудкорт,еда,фаст - фуд,перекус".split(
    ",")
RESTAURANT_NAMES = "кафе,кафетерий,ресторан,кафешка,бистро,зонтик,терраса,веранда,кафешок"

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

SENTENCE_START = r'(?:((?:ларек|ларёк|киоск|будочка|магазин) с |быть(?: бы)? )(?:\w+?[оыи]й )?)?(?:{})'.format(
    "|".join(FOOD_NAMES))


# print(SENTENCE_START)

def assign_headlines_food(lemmas, additional_headlines):
    approval_label = "Организовать продажу уличной еды"
    for i in GOOD_FOOD_MARKERS:
        if i in lemmas:
            additional_headlines.add(approval_label)
            return

    regex = "({})[^,().!]+?({})".format("|".join(APPROVAL_WORDS), "|".join(FOOD_NAMES))
    if re.search(regex, lemmas):
        additional_headlines.add(approval_label)
        return
    if re.match(SENTENCE_START, lemmas):
        additional_headlines.add(approval_label)
        return
    if not ({pos(i) for i in lemmas.split()} - {"A", "S", None, "PR", 'CONJ', "ADV"}) and not re.search(r"\bнет?\b",
                                                                                                        lemmas):
        additional_headlines.add(approval_label)


from keyword_extractor import pos


def assign_headlines_restaurants(lemmas, additional_headlines):
    approval_label = "Открыть качественные кафе"

    regex = r"({})[^,().!]+?({})".format("|".join(APPROVAL_WORDS), "|".join(RESTAURANT_NAMES))
    if re.search(regex, lemmas):
        additional_headlines.add(approval_label)
        return

    if not ({pos(i) for i in lemmas.split()} - {"A", "S", None, "PR", 'CONJ', "ADV"}) and not re.search(r"\bнет?\b",
                                                                                                        lemmas):
        additional_headlines.add(approval_label)


QUESTIONED = {
    "Кафе, рестораны",
    "Уличная еда",
    "Парковки",
    "Торговля",
    "Транспорт",
    "Переходы",
    "Лавки",
}

all_tags = set()


class TagNames(object):

    NO_CHANGE_REQUIRED = "Ничего не менять"


c = 0
ms = Mystem()
with open("/Users/marina/Desktop/bstp/sennaya-2016-12-17.csv") as f:
    reader = csv.reader(f, delimiter=",")
    for line in reader:
        value = line[DST_COL]
        lemmas = " ".join([i for i in ms.lemmatize(value) if i.strip()])

        hls = set()
        for m in matches:
            if regexes[m].search(lemmas):
                hls.add(matches[m])

        if "Ничего не менять" in hls:
            hls = {"Ничего не менять"}

        if "Разрешить организованную торговлю" in hls or "Запретить торговлю" in hls:
            hls.discard("Торговля")
        if "Разрешить организованную торговлю" in hls and "Запретить торговлю" in hls:
            hls.add("Торговля")
            hls.remove("Разрешить организованную торговлю")
            hls.remove("Запретить торговлю")

        if "Парковки" in hls:
            additional_headlines = set()
            assign_headlines_parking(lemmas, additional_headlines)
            if additional_headlines:
                hls.remove("Парковки")
                hls |= {i.capitalize() for i in additional_headlines}

        if "Уличная еда" in hls:
            assign_headlines_food(lemmas, hls)
            if "Организовать продажу уличной еды" in hls:
                hls.remove("Уличная еда")

        if "Кафе, рестораны" in hls:
            assign_headlines_restaurants(lemmas, hls)
            if "Открыть качественные кафе" in hls:
                hls.discard("Кафе, рестораны")

        # if hls & QUESTIONED:
        if True:
            print(value.strip())
            # print(lemmas)
            print("Теги: ", "; ".join(hls))
            # print()
            c += 1

        all_tags |= hls


import sys
for i in sorted(all_tags):
    print(i, file=sys.stderr)
