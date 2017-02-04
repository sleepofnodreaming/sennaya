#!/usr/local/bin/python3

import argparse
import itertools
import logging
import os
import re
import sys
from collections import namedtuple, OrderedDict
from typing import Dict, Union, Callable, Tuple, List

from answer import Answer
from generalling import NegationParser, pos, SpellcheckNorm
from readers import read_wordlists, read_csv_dictionaries, read_columns

logging.basicConfig(format='[%(asctime)s] %(levelname)s: %(message)s', level=logging.INFO, stream=sys.stderr)


DISLIKES = [6, 14, 15]
LIKES = [5, 12, 13]


class HardPaths(object):
    SYNONYM_DICT = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "dictionaries",
        "likes",
        "tagging_dict.csv"
    )
    LIKE_MATCHING = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "dictionaries",
        "likes",
        "manual",
        "likes.csv"
    )
    DISLIKE_MATCHING = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "dictionaries",
        "likes",
        "manual",
        "dislikes.csv"
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


def convert_csv_dictionary(dic):
    assert issubclass(dic.__class__, dict)
    new_dict = dic.__class__()
    for k, v in dic.items():
        new_dict[k] = sorted(dic[k])[0]
    return new_dict

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


class Searcher(object):
    def __init__(self, dictionary: OrderedDict):
        self._regexes = {
            word: re.compile(r"\b({})\b".format(word), flags=re.I) for word in dictionary.keys()
        }
        self._order = {word: number for number, word in enumerate(dictionary.keys())}

    def search(self, text):
        indices = []
        for word, regex in self._regexes.items():
            for match in regex.finditer(text):
                indices.append((word, self._order[word], match.start(1)))
        indices.sort(key=lambda a: (a[1], a[2]))
        return [word for word, _, _ in indices]



class _MatchToPredefinedAnswer(object):
    def __init__(self):
        self.__dict_cache = None

    def _update_searcher(self, dictionary):
        if dictionary is not self.__dict_cache:
            self.__dict_cache = dictionary
            self.searcher = Searcher(dictionary)

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

        :raises AssertionError: If the postprocessing list or the answer're empty.
        """
        assert postprocessings
        assert not answer.is_empty

        self._update_searcher(synonim_dic)

        to_string = lambda a: " ".join(a)
        to_text_answer = lambda t, n: ("" if n else "нет ") + synonim_dic[to_string(t)]

        first_iter_result = None

        hypotheses = []

        Hypothesis = namedtuple("Hypothesis", ["text", "match", "postproc", "answer", "punct"])


        for remove_punct in (False, True):
            for postprocess, name in postprocessings:
                cut_text, neg = postprocess(answer.get_lemmas(remove_punct, False))
                logging.info("Parsed (line {}): {} -> {}({})".format(line, answer._src, neg, cut_text))

                # Фксршмштп еру
                if first_iter_result is not None:
                    first_iter_result = ("" if neg else "нет ") + to_string(cut_text)
                #
                if to_string(cut_text) in synonim_dic:
                    result = to_text_answer(cut_text, neg)
                    hypotheses.append(Hypothesis(result, "exact", name, "full", not remove_punct))
                m = self.searcher.search(to_string(cut_text))
                if m:
                    logging.info("Prioritized tags: %s", ", ".join(m))
                    # result = ("" if neg else "нет ") + synonim_dic[m[0]]
                    results = [("" if neg else "нет ") + synonim_dic[i] for i in m]
                    results = [Hypothesis(r, "substring", name, "full", not remove_punct) for r in results]
                    hypotheses.extend(results)

        if first_iter_result:
            hypotheses.append(Hypothesis(first_iter_result, "initial", None, None, None))

        return hypotheses


match_to_predefined_answer = _MatchToPredefinedAnswer()


def _match_answer_to_category(ans, hypotheses, ready_answers, num):
    for result in hypotheses:
        if ready_answers.get(result.text) is not None:
            if result[-1] is not None:
                logging.info(
                    "Converted (line {0}) [{1.match} match, {1.postproc} postproc, {1.answer} answer]: {2} -> {1.text}".format(
                        num, result, ans))
            else:
                logging.info("Not converted (line {}): {} -> {}".format(num, ans, result.text))

            logging.info("Matched (line {}): {} -> {}".format(num, result.text, ready_answers[result.text]))
            return ready_answers[result.text]


def process_text_answer(answer, syn_matcher, num):
    hypotheses = syn_matcher(answer)
    ready_answer = _match_answer_to_category(answer._src, hypotheses, ready_answers, num)
    if ready_answer:
        print(ready_answer)
        return True
    return False


def parse_args():
    parser = argparse.ArgumentParser(description="A script producing statistics on respondents' likes and dislikes.")
    parser.add_argument("like", metavar="STR", type=str, choices=["like", "dislike"])
    parser.add_argument("data_table", metavar="PATH", type=str, help="A path to a csv table containing the data.")

    parser.add_argument("-u", "--unprocessed", metavar="PATH", type=str,
                        help="A path to a file to write unprocessed answers to.")

    parsed = parser.parse_args()
    parsed.data_table = os.path.expanduser(os.path.abspath(parsed.data_table))
    assert os.path.isfile(parsed.data_table)
    assert parsed.like in ("like", "dislike")
    if parsed.unprocessed:
        parsed.unprocessed = os.path.expanduser(os.path.abspath(parsed.unprocessed))
    else:
        parsed.unprocessed = os.devnull
    return parsed


if __name__ == '__main__':

    parsed = parse_args()

    ready_answers = convert_csv_dictionary(read_csv_dictionaries([
        HardPaths.LIKE_MATCHING if parsed.like == "like" else HardPaths.DISLIKE_MATCHING,
    ], True))
    syn_dic = convert_csv_dictionary(read_csv_dictionaries([HardPaths.SYNONYM_DICT], False))
    negations, ignorables = map(lambda a: read_wordlists([os.path.join(HardPaths.LIKE_DICS, a)], False),
                                HardPaths.dictionaries)

    spellcheck = SpellcheckNorm("ru_RU", *[negations, ignorables])

    with open(parsed.unprocessed, "w") as unproc_file:
        for num, ans in read_columns(parsed.data_table, *(LIKES if parsed.like == "like" else DISLIKES)):
            direct_match = ready_answers.get(ans.lower())
            if direct_match:
                logging.info("Matched directly (line {}): {} -> {}".format(num, ans, direct_match))
                print(direct_match)
                continue

            synonym_matcher = lambda a: match_to_predefined_answer(
                num,
                a,
                syn_dic,
                lemma_list_converter_factory(negations, ignorables)
            )

            answer = Answer(ans)

            if answer.is_empty:
                logging.info("Skipped (line {}): {}".format(num, ans))
                continue

            if not process_text_answer(answer, synonym_matcher, num):
                logging.info("Trying spellcheck...")
                ans_norm = spellcheck(ans)
                if ans != ans_norm:
                    logging.info("Spellckeck (line {}): {} -> {}".format(num, ans, ans_norm))
                    answer = Answer(ans_norm)
                    if not answer.is_empty:
                        if not process_text_answer(answer, synonym_matcher, num):
                            print(ans.lower(), file=unproc_file)
                else:
                    logging.info("Spellcheck dropped.")
                    print(ans.lower(), file=unproc_file)
