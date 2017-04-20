#!/usr/local/bin/python3

import argparse
import json
import logging
import os
import re
import sys
from collections import namedtuple, OrderedDict
from typing import Dict, Union, Callable, Tuple, List

from answer import BaseAnswer, SimpleAnswer, FullSpellcheckAnswer, PartialSpellckeckAnswer
from generalling import NegationParser
from readers import read_wordlists, read_csv_dictionaries, read_columns

logging.basicConfig(format='[%(asctime)s] %(levelname)s: %(message)s', level=logging.INFO, stream=sys.stderr)


Hypothesis = namedtuple("Hypothesis", ["text", "match"])


class HardPaths(object):

    SYNONYM_DICT = "tagging_dict.csv"
    LIKE_MATCHING = "likes.csv"
    DISLIKE_MATCHING = "dislikes.csv"
    STOP_DICT = "stops.txt"
    COLNUMS = "colnums.json"

    LIKE_DICS = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "dictionaries",
        "likes",
    )

    dictionaries = (
        "negations.txt",
        "ignorables.txt",
    )


def convert_csv_dictionary(dic: Union[Dict[str, set], OrderedDict]) -> Dict[str, str]:
    assert issubclass(dic.__class__, dict)
    new_dict = dic.__class__()
    for k, v in dic.items():
        new_dict[k] = sorted(dic[k])[0]
    return new_dict


class Searcher(object):
    """
    A class looking for word matches and generating a list of matches
    sorted by priorities specified by an input ordered dict.
    """
    def __init__(self, dictionary: OrderedDict):
        self._regexes = {
            word: re.compile(r"\b({})\b".format(word), flags=re.I) for word in dictionary.keys()
            }
        self._order = {word: number for number, word in enumerate(dictionary.keys())}

    def search(self, text: str) -> List[str]:
        indices = []
        for word, regex in self._regexes.items():
            for match in regex.finditer(text):
                indices.append((word, self._order[word], match.start(1)))
        indices.sort(key=lambda a: (a[1], a[2]))
        return [word for word, _, _ in indices]


class _MatchToPredefinedAnswer(object):
    """A class caching a dictionary not to compile regular expressions multiple times."""
    def __init__(self):
        self.__dict_cache = None

    def _update_searcher(self, dictionary: OrderedDict):
        if dictionary is not self.__dict_cache:
            self.__dict_cache = dictionary
            self.searcher = Searcher(dictionary)

    def __call__(self,
                 answer: BaseAnswer,
                 synonim_dic: OrderedDict,
                 postprocess: Callable[[list], Tuple[str, bool]]) -> List[Hypothesis]:
        """
        Match an answer to a dictionary entry, if possible.

        :param answer: An answer of a respondent.
        :param synonim_dic: A dictionary matching synonymic words to the same entry key.
        :param postprocess: A func converting a list of lemmas to a pair (dict key, negation).

        :returns: A list of hypotheses.

        :raises AssertionError: If the postprocessing list or the answer're empty.
        """

        self._update_searcher(synonim_dic)

        to_string = lambda a: " ".join(a)
        to_text_answer = lambda t, n: ("" if n else "нет ") + synonim_dic[to_string(t)]

        hypotheses = []

        cut_text, neg = answer.apply_negation_parser(postprocess)

        logging.info("Negation detection: {} -> {}({})".format(answer.src, neg, cut_text))
        # The first hypothesis is that a sequence of lemmas negated is an exact match,
        # without going through a dictionary.
        hypotheses.append(Hypothesis(("" if neg else "нет ") + to_string(cut_text), "initial"))
        # The next hypothesis: the text may match any dictionary key as a whole.
        if to_string(cut_text) in synonim_dic:
            result = to_text_answer(cut_text, neg)
            hypotheses.append(Hypothesis(result, "exact"))
        # Finally, the text may contain key words.
        matches = self.searcher.search(to_string(cut_text))
        if matches:
            results = [("" if neg else "нет ") + synonim_dic[i] for i in matches]
            results = [Hypothesis(r, "substring") for r in results]
            hypotheses.extend(results)
        logging.info("Hypotheses generated: {}".format(", ".join("'%s'" % s[0] for s in hypotheses)))
        return hypotheses


class TextAnswerProcessor(object):
    @staticmethod
    def to_priority_answer(answer: BaseAnswer,
                           syn_matcher: Callable[[BaseAnswer], List[Hypothesis]],
                           ready_answers: dict,
                           stop_after) -> bool:
        hypotheses = syn_matcher(answer)
        ready_answer = None
        for result in hypotheses:
            if ready_answers.get(result.text) is not None:
                logging.info("Matched: {} -> {}".format(
                    result.text,
                    ready_answers[result.text])
                )
                ready_answer = ready_answers[result.text]
                break
            elif result.text in stop_after:
                logging.warning("Answer search stopped: {} in stop list.".format(result.text))
                break
        if ready_answer:
            print(ready_answer)
            logging.info("Processing path (matched): {} -> {} -> {}".format(answer.src, result.text, ready_answer))
            return True
        return False

    @staticmethod
    def to_all_options(answer: BaseAnswer,
                            syn_matcher: Callable[[BaseAnswer], List[Hypothesis]],
                            ready_answers: dict,
                            stop_after) -> bool:
        hypotheses = syn_matcher(answer)
        answers = set()
        ready_answer = None
        for result in hypotheses:
            if ready_answers.get(result.text) is not None:
                logging.info("Matched: {} -> {}".format(
                    result.text,
                    ready_answers[result.text])
                )
                ready_answer = ready_answers[result.text]
                if ready_answer not in answers:
                    print(ready_answer)
                    answers.add(ready_answer)
                    logging.info("Processing path (matched): {} -> {} -> {}".format(answer.src, result.text, ready_answer))

            elif result.text in stop_after:
                logging.warning("Answer search stopped: {} in stop list.".format(result.text))
                break
        if ready_answer:
            return True
        return False


def parse_args():
    parser = argparse.ArgumentParser(description="A script producing statistics on respondents' likes and dislikes.")
    parser.add_argument("like", metavar="STR", type=str, choices=["like", "dislike"], help="'like' or 'dislike'")
    parser.add_argument("data_table", metavar="PATH", type=str, help="path to a csv table containing the data")
    parser.add_argument("dictionaries", metavar="PATH", type=str, help="path to specific dictionaries")

    parser.add_argument("-u", "--unprocessed", metavar="PATH", type=str,
                        help="path to a file to write unprocessed answers to")

    parsed = parser.parse_args()
    parsed.data_table = os.path.expanduser(os.path.abspath(parsed.data_table))
    parsed.dictionaries = os.path.expanduser(os.path.abspath(parsed.dictionaries))
    assert os.path.isfile(parsed.data_table)
    assert os.path.isdir(parsed.dictionaries)
    assert parsed.like in ("like", "dislike")
    if parsed.unprocessed:
        parsed.unprocessed = os.path.expanduser(os.path.abspath(parsed.unprocessed))
    else:
        parsed.unprocessed = os.devnull
    return parsed


if __name__ == '__main__':

    parsed = parse_args()
    # Initializing dictionaries.
    like_dislike = HardPaths.LIKE_MATCHING if parsed.like == "like" else HardPaths.DISLIKE_MATCHING
    path_to_answers = os.path.join(parsed.dictionaries, like_dislike)
    if not os.path.isfile(path_to_answers):
        logging.critical("The directory %s does not contain %s dictionary", parsed.dictionaries, parsed.like)
        sys.exit(1)

    path_to_synonyms = os.path.join(parsed.dictionaries, HardPaths.SYNONYM_DICT)
    if not os.path.isfile(path_to_answers):
        logging.critical("The directory %s does not contain synonym dictionary", parsed.dictionaries)
        sys.exit(1)

    path_to_stops = os.path.join(parsed.dictionaries, HardPaths.STOP_DICT)
    if not os.path.isfile(path_to_answers):
        logging.critical("The directory %s does not contain stop dictionary", parsed.dictionaries)
        sys.exit(1)

    path_to_colnums = os.path.join(parsed.dictionaries, HardPaths.COLNUMS)
    if not os.path.isfile(path_to_answers):
        logging.critical("The directory %s does not contain column listing file", parsed.dictionaries)
        sys.exit(1)
    with open(path_to_colnums) as f:
        jsondic = json.loads(f.read())
    colnums = jsondic[parsed.like]

    ready_answers = convert_csv_dictionary(read_csv_dictionaries([path_to_answers], True))
    syn_dic = convert_csv_dictionary(read_csv_dictionaries([path_to_synonyms], False))
    negations, ignorables = map(lambda a: read_wordlists([os.path.join(HardPaths.LIKE_DICS, a)], False),
                                HardPaths.dictionaries)
    stops = read_wordlists([path_to_stops])

    # Initializing functions with the use of func factories.
    negation_parser = NegationParser(negations, ignorables)
    match_to_predefined_answer = _MatchToPredefinedAnswer()
    synonym_matcher = lambda a: match_to_predefined_answer(a, syn_dic, negation_parser)

    ANSWER_TYPES = [
        ("no spellcheck", SimpleAnswer),
        ("partial spellcheck", PartialSpellckeckAnswer),
        ("full spellcheck", FullSpellcheckAnswer),
    ]

    with open(parsed.unprocessed, "w") as unproc_file:
        for num, ans in read_columns(parsed.data_table, *colnums):
            logging.info("Start processing answer: '{}' (line {})".format(ans, num))
            direct_match = ready_answers.get(ans.lower())
            if direct_match:
                logging.info("Processing path (matched directly): {} -> {}".format(ans, direct_match))
                print(direct_match)
                continue

            for type_name, answer_type in ANSWER_TYPES:
                answer = answer_type(ans, include_punctuation=True)
                logging.info("Try processing with %s, lemmas: %s", type_name, answer.to_lemmas())
                if TextAnswerProcessor.to_all_options(answer, synonym_matcher, ready_answers, stops):
                    break
            else:
                print(ans, file=unproc_file)
                logging.info("Processing path (aborting): {}".format(ans))
