
from generalling import parse_negations, pos
from wordlistlib import read_wordlists, read_csv_dictionaries

import csv
import os
import re
import logging
import sys
from pymystem3 import Mystem

logging.basicConfig(format='[%(asctime)s] %(levelname)s: %(message)s', level=logging.INFO)

mystem = Mystem()




class Answer(object):

    __russian_letter = re.compile(r"[а-яё]", flags=re.I)

    def __init__(self, string):
        self._src = string.strip()
        self._text = [i["text"] for i in mystem.analyze(self._src) if i["text"].strip()]
        self._lemmas = [(i, pos(i)) for i in mystem.lemmatize(self._src) if i.strip()]
        assert len(self._text) == len(self._lemmas), "A number of word forms is not equal to a number of lemmas."

    def get_lemmas(self, skip_punct=True, as_string=False):
        lemmas = [w for (w, p) in self._lemmas if not skip_punct or p]
        return " ".join(lemmas) if as_string else lemmas

    def shorten(self):
        for i, (l, p) in enumerate(self._lemmas):
            if p is None:
                shortened_answer = Answer(self._src)
                shortened_answer._text, shortened_answer._lemmas = self._text[:i], self._lemmas[:i]
                return shortened_answer
        return self

    @property
    def is_empty(self):
        return all(p is None or not self.__russian_letter.search(w) for w, p in self._lemmas)




LIKE_DICS = "/Users/marina/Dropbox/bstp/dictionaries/likes/"
dictionaries = [
    "negations.txt",
    "ignorables.txt",
]
negations, ignorables = map(lambda a: read_wordlists([os.path.join(LIKE_DICS, a)], False), dictionaries)


def read_columns(fn, *columns):
    # logging.info("Reading columns from table {}. Columns chosen: {}".format(fn, ", ".join(chr(ord("A") + i - 1) for i in columns)))
    answers = []
    with open(fn) as f:
        reader = csv.reader(f, delimiter=",")
        next(reader, None)
        for num, line in enumerate(reader):
            line = [i.strip() for n, i in enumerate(line) if i.strip() and n + 1 in columns]
            answers.extend(((num + 2, i) for i in set(line)))
    return answers


dic = read_csv_dictionaries(["/Users/marina/Dropbox/bstp/dictionaries/likes/general_dict.csv"], False)
dic = {i: dic[i].pop() for i in dic}


postproc = {
    ("зелень", False): "мало зелени",
    ("скамейка", False): "мало скамеек",
    ("дерево", False): "мало зелени",
    ("парковка", False): "мало парковочных мест",
    ("маргинал", False): "нет маргиналов"

}


DISLIKES = [6, 14, 15]
LIKES = [5, 12, 13]


for num, ans in read_columns("/Users/marina/Dropbox/bstp/sennaya-2016-12-17.csv", *DISLIKES):

    a = Answer(ans)
    print(a.is_empty)
    print(a.get_lemmas(True, True))
    print(a.get_lemmas(False, True))
    print(a.shorten().is_empty)
    print(a.shorten().get_lemmas(True, True))
    print(a.shorten().get_lemmas(False, True))
    print()


    # t = ans
    # ans = mystem.lemmatize(ans)
    # text, neg = parse_negations(ans, negations, ignorables)
    # if len(text) > 1  and text[1] in ["пространство", "место"]:
    #     text = text[:2]
    # str_text = " ".join(text)
    # if any(i.isalpha() for i in str_text):
    #     if " ".join(text) in dic:
    #         print(("" if neg else "нет ") + dic[" ".join(text)])
    #         # print("{}\t{}".format(t, ("" if neg else "нет ") + dic[" ".join(text)]))
    #     elif len(text) == 1:
    #         print(("" if neg else "нет ") + text[0])
    #     else:
    #         print(t.lower(), file=sys.stderr)
