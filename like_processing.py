#!/usr/local/bin/python3

from generalling import NegationParser, pos
from pymystem3 import Mystem
from typing import Dict, Union, Callable, Tuple, List
from wordlistlib import read_wordlists, read_csv_dictionaries

import argparse
import csv
import itertools
import logging
import os
import re
import sys

logging.basicConfig(format='[%(asctime)s] %(levelname)s: %(message)s', level=logging.INFO, stream=sys.stderr)

mystem = Mystem()

DISLIKES = [6, 14, 15]
LIKES = [5, 12, 13]


class HardPaths(object):
    SYNONYM_DICT = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "dictionaries",
        "likes",
        "synonym_dict.csv"
    )
    LIKE_MATCHING = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "dictionaries",
        "likes",
        "manual",
        "likes.csv"
    )
    LIKE_DICS = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "dictionaries",
        "likes",
    )

    dictionaries = (
        "negations.txt",
        "ignorables.txt",
    )


class Answer(object):
    __russian_letter = re.compile(r"[а-яё]", flags=re.I)

    def __init__(self, string):
        self._src = string.strip()
        lemmas = [(i.strip(), pos(i)) for i in mystem.lemmatize(self._src) if i.strip()]
        self._lemmas = list(itertools.dropwhile(lambda a: a[1] is None, lemmas))
        text = [i["text"] for i in mystem.analyze(self._src) if i["text"].strip()]
        self._text = text[len(text) - len(self._lemmas):]
        assert len(self._text) == len(self._lemmas), "A number of word forms is not equal to a number of lemmas."
        logging.info("New answer created, lemmas: {}".format(self._lemmas))

    def __len__(self):
        return len(self._lemmas)

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


def convert_csv_dictionary(dic):
    return {i: dic[i].pop() for i in dic}


def lemma_list_converter_factory(negations, ignorables):
    """
    A factory function producing a func matching a list of lemmas to a pair (main answer part, is negative)
    according to dictionaries defined.

    :param negations: A list of words to consider negations.
    :param ignorables: A list of words to ignore in the start of a sentence.

    :return: a func to use as a matching one.
    """

    parse_negations = NegationParser(negations, ignorables)

    def default_func(lemmas):
        text, is_neg = parse_negations(lemmas)
        if len(text) > 1 and text[1] in ["пространство", "место"]:
            text = text[:2]
        return text, is_neg

    def np_func(lemmas):
        text, is_neg = parse_negations(lemmas)
        cut_text = list(itertools.dropwhile(lambda a: pos(a) == "A", text))
        return (cut_text, is_neg) if cut_text and pos(cut_text[0]) == "S" else (text, is_neg)

    return [(default_func, "default"), (np_func, "np_cut")]


class _MatchToPredefinedAnswer(object):
    def __init__(self):
        self.__dict_cache = None

    def __call__(self,
                 line: int,
                 answer: Answer,
                 synonim_dic: Dict[str, str],
                 postprocessings: List[Callable[[list], Tuple[str, bool]]]) -> Union[None, str]:
        """
        Match an answer to a dictionary entry, if possible.

        :param answer: An answer of a respondent.
        :param synonim_dic: A dictionary matching synonymic words to the same entry key.
        :param postprocessings: A list of funcs converting a list of lemmas to a pair (dict key, negation).

        :returns: None, if the answer doesn't match anything; a dict entry string key, otherwise.

        :raises AssertionError: If postprocessings list's empty.
        """
        assert postprocessings

        if synonim_dic is not self.__dict_cache:
            self.__dict_cache = synonim_dic
            self.startingwith_re = re.compile(r'\b(' + r"|".join(sorted(synonim_dic.keys())) + r")\b")

        to_string = lambda a: " ".join(a)
        to_text_answer = lambda t, n: ("" if n else "нет ") + synonim_dic[to_string(t)]

        archived_text = archived_neg = None

        if not answer.is_empty:
            for remove_punct in (False, True):
                for postprocess, name in postprocessings:
                    cut_text, neg = postprocess(answer.get_lemmas(remove_punct, False))
                    logging.info("Parsed (line {}): {} -> {}({})".format(line, answer._src, neg, cut_text))
                    if archived_text is None:
                        archived_text, archived_neg = cut_text, neg
                    if to_string(cut_text) in synonim_dic:
                        result = to_text_answer(cut_text, neg)
                        logging.info("Conversion hypothesis (line {}) [exact match, {} postproc, full answer]: {} -> {}".format(line, name, answer._src, result))
                        return result
                    m = self.startingwith_re.search(to_string(cut_text))
                    if m:
                        result = ("" if neg else "нет ") + synonim_dic[m.group(0)]
                        logging.info("Conversion hypothesis (line {}) [substring match, {} postproc, full answer]: {} -> {}".format(line, name, answer._src, result))
                        return result

            shortened_answer = answer.shorten()
            if not shortened_answer.is_empty:
                for postprocess, name in postprocessings:
                    cut_text, neg = postprocess(shortened_answer.get_lemmas(False, False))
                    if to_string(cut_text) in synonim_dic:
                        result = to_text_answer(cut_text, neg)
                        logging.info(
                            "Conversion hypothesis (line {}) [exact match, {} postproc, shortened answer]: {} -> {}".format(line, name, answer._src, result))
                        return result

            result = ("" if archived_neg else "нет ") + to_string(archived_text)
            logging.info("No conversion hypothesis (line {}): {} -> {}".format(line, answer._src, result))
            return result


match_to_predefined_answer = _MatchToPredefinedAnswer()


def parse_args():
    parser = argparse.ArgumentParser(description="A script producing statistics on respondents' likes and dislikes.")
    parser.add_argument("data_table", metavar="PATH", type=str, help="A path to a csv table containing the data.")
    parser.add_argument("-u", "--unprocessed", metavar="PATH", type=str,
                        help="A path to a file to write unprocessed answers to.")
    parsed = parser.parse_args()
    parsed.data_table = os.path.expanduser(os.path.abspath(parsed.data_table))
    assert os.path.isfile(parsed.data_table)
    if parsed.unprocessed:
        parsed.unprocessed = os.path.expanduser(os.path.abspath(parsed.unprocessed))
    else:
        parsed.unprocessed = os.devnull
    return parsed


if __name__ == '__main__':

    parsed = parse_args()

    ready_answers = convert_csv_dictionary(read_csv_dictionaries([
        HardPaths.LIKE_MATCHING,
    ], True))
    syn_dic = convert_csv_dictionary(read_csv_dictionaries([HardPaths.SYNONYM_DICT], False))
    negations, ignorables = map(lambda a: read_wordlists([os.path.join(HardPaths.LIKE_DICS, a)], False),
                                HardPaths.dictionaries)

    with open(parsed.unprocessed, "w") as unproc_file:
        for num, ans in read_columns(parsed.data_table, *LIKES):
            answer = Answer(ans)
            result = match_to_predefined_answer(num, answer, syn_dic, lemma_list_converter_factory(negations, ignorables))
            if result is None:
                logging.info("Skipped (line {}): {}".format(num, ans))
                continue
            if ready_answers.get(result) is not None:
                logging.info("Matched (line {}): {} -> {}".format(num, result, ready_answers[result]))
                print(ready_answers[result])
            else:
                logging.info("Unmatched (line {}): {}".format(num, result))
                print(ans.lower(), file=unproc_file)
