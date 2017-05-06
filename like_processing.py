#!/usr/local/bin/python3

import argparse
import csv
import itertools
import json
import logging
import nltk
import os
import re
import sys


from collections import namedtuple, OrderedDict
from typing import Dict, Union, List

from answer import SimpleAnswer, FullSpellcheckAnswer
from generalling import NegationParser
from readers import read_wordlists, read_csv_dictionaries, read_columns


logging.basicConfig(format='[%(asctime)s] %(levelname)s: %(message)s', level=logging.INFO, stream=sys.stderr)


Hypothesis = namedtuple("Hypothesis", ["text", "match", "source_path"])


class HardPaths(object):

    MATCHING = "matching.json"
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
                 answer: str,
                 answer_class: type,
                 synonim_dic: OrderedDict,
                 postprocess) -> List[Hypothesis]:
        """
        Match an answer to a dictionary entry, if possible.

        :param answer: An answer of a respondent.
        :param synonim_dic: A dictionary matching synonymic words to the same entry key.
        :param postprocess: A func converting a list of lemmas to a pair (dict key, negation).

        :returns: A list of hypotheses.

        :raises AssertionError: If the postprocessing list or the answer're empty.
        """

        self._update_searcher(synonim_dic)

        hypotheses = []

        sentence_parts = postprocess.to_chunks(answer, answer_class)
        for part, neg in sentence_parts:
            logging.info("Part extracted: {} -> {}({})".format(answer, neg, part))
            matches = self.searcher.search(part)
            if matches:
                results = [("" if neg else "нет ") + synonim_dic[i] for i in matches]
                results = [Hypothesis(r, "substring", (part, neg)) for r in results]
                logging.info("Hypotheses generated: {}".format(", ".join("'%s'" % s[0] for s in results)))
                hypotheses.append(results)
        return hypotheses


class TextAnswerProcessor(object):

    @staticmethod
    def to_sentences(text):
        standard_sent = nltk.sent_tokenize(text)
        return list(
            filter(lambda a: a, itertools.chain(*[map(lambda a: a.strip(), i.split(";")) for i in standard_sent])))

    @staticmethod
    def to_priority_answer(answer: str,
                           answer_type,
                           syn_matcher,
                           ready_answers: dict,
                           stop_after) -> bool:

        sentences = TextAnswerProcessor.to_sentences(answer)
        logging.info("Split into sentences: %s -> %s", answer, sentences)

        all_hypotheses = set()
        data_sources = []

        for sentence in sentences:
            hypotheses = syn_matcher(sentence, answer_type)

            for hypotheses_per_chunk in hypotheses:
                for result in hypotheses_per_chunk:
                    if ready_answers.get(result.text) is not None:
                        logging.info("Matched: {} -> {}".format(
                            result.text,
                            ready_answers[result.text])
                        )
                        all_hypotheses.add(ready_answers[result.text])
                        data_sources.append(result.source_path)
                        break
                    elif result.text in stop_after:
                        logging.warning("Answer search stopped: {} in stop list.".format(result.text))
                        break
        if all_hypotheses:
            for ans in all_hypotheses: print(ans)
            logging.info("Processing path (matched): {} -> {} -> {}".format(
                answer,
                ", ".join("{}({})".format(i[1], i[0]) for i in data_sources),
                ", ".join(all_hypotheses))
            )
            return True
        return False


def parse_args():
    parser = argparse.ArgumentParser(description="A script producing statistics on respondents' likes and dislikes.")
    parser.add_argument("like", metavar="STR", type=str, choices=["like", "dislike", "place"], help="'like' or 'dislike'")
    parser.add_argument("data_table", metavar="PATH", type=str, help="path to a csv table containing the data")
    parser.add_argument("dictionaries", metavar="PATH", type=str, help="path to specific dictionaries")

    parser.add_argument("-u", "--unprocessed", metavar="PATH", type=str,
                        help="path to a file to write unprocessed answers to")

    parsed = parser.parse_args()
    parsed.data_table = os.path.expanduser(os.path.abspath(parsed.data_table))
    parsed.dictionaries = os.path.expanduser(os.path.abspath(parsed.dictionaries))
    assert os.path.isfile(parsed.data_table)
    assert os.path.isdir(parsed.dictionaries)
    if parsed.unprocessed:
        parsed.unprocessed = os.path.expanduser(os.path.abspath(parsed.unprocessed))
    else:
        parsed.unprocessed = os.devnull
    return parsed


def get_dictionary_paths(directory, for_case):
    full_path = os.path.join(directory, HardPaths.MATCHING)
    if not os.path.exists(full_path):
        logging.critical("Matching file %s does not exist in %s", HardPaths.MATCHING, directory)
        return {}
    with open(full_path) as f:
        data = json.loads(f.read())
        if for_case not in data:
            logging.critical("Dictionaries for parameter %s are not specified", for_case)
            return {}
    absolute_paths = {k: os.path.join(directory, v) for k, v in data[for_case].items()}
    if any(not os.path.exists(i) for i in absolute_paths.values()):
        logging.critical("Some dictionaries specified do not exist")
    return absolute_paths


def read_negs(filename):
    with open(filename) as f:
        reader = csv.reader(f, delimiter=",")
        dictionary = [(word, geni) for word, *geni in filter(lambda a: a, reader)]
    return OrderedDict(dictionary)


if __name__ == '__main__':

    parsed = parse_args()
    # Initializing dictionaries.
    dictionary_paths = get_dictionary_paths(parsed.dictionaries, parsed.like)
    if not dictionary_paths:
        sys.exit(1)
    path_to_answers = dictionary_paths["categories"]
    path_to_synonyms = dictionary_paths["concepts"]
    path_to_stops = dictionary_paths["stop_markers"]
    path_to_colnums = os.path.join(parsed.dictionaries, HardPaths.COLNUMS)
    if not os.path.isfile(path_to_answers):
        logging.critical("The directory %s does not contain column listing file", parsed.dictionaries)
        sys.exit(1)
    with open(path_to_colnums) as f:
        jsondic = json.loads(f.read())
    colnums = jsondic[parsed.like]

    ready_answers = convert_csv_dictionary(read_csv_dictionaries([path_to_answers], True))
    syn_dic = convert_csv_dictionary(read_csv_dictionaries([path_to_synonyms], False))
    negations, ignorables = read_negs(os.path.join(HardPaths.LIKE_DICS, "negations.txt")), read_negs(os.path.join(HardPaths.LIKE_DICS, "ignorables.txt"))
    stops = read_wordlists([path_to_stops])

    # # Initializing functions with the use of func factories.
    negation_parser = NegationParser(negations, ignorables)
    match_to_predefined_answer = _MatchToPredefinedAnswer()
    synonym_matcher = lambda a, ac: match_to_predefined_answer(a, ac, syn_dic, negation_parser)

    ANSWER_TYPES = [
        ("no spellcheck", SimpleAnswer),
        ("full spellcheck", FullSpellcheckAnswer),
    ]

    with open(parsed.unprocessed, "w") as unproc_file:
        for num, ans in read_columns(parsed.data_table, *colnums):

            logging.info("Start processing answer: '{}' (line {})".format(ans, num))
            direct_match = ready_answers.get(ans.lower()) or ready_answers.get(ans)
            if direct_match:
                logging.info("Processing path (matched directly): {} -> {}".format(ans, direct_match))
                print(direct_match)
                continue

            for type_name, answer_type in ANSWER_TYPES:
                logging.info("Try processing with %s, chunk: %s", type_name, type_name)
                if TextAnswerProcessor.to_priority_answer(ans, answer_type, synonym_matcher, ready_answers, stops):
                    break
            else:
                print(ans, file=unproc_file)
                logging.info("Processing path (aborting): {}".format(ans))
