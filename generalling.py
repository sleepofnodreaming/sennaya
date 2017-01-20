import re
from typing import Union, Tuple, List

import pymystem3

GLOBAL_MYSTEM = pymystem3.Mystem()


class NegationParser(object):

    def __init__(self, negation_dict: List[str], ignoring_dict: Union[List[str], None]):
        self._negation_dict = negation_dict
        self._ignoring_dict = ignoring_dict
        self._neg_cut = re.compile(r'\b(' + r'|'.join(self._negation_dict) + r')\b')
        self._ignor_cut = None if self._ignoring_dict else re.compile(r'\b(' + r'|'.join(self._ignoring_dict) + r')\b')

    @staticmethod
    def cut_with_re(string, regex):
        if regex is None:
            return string
        m = regex.match(string)
        return string if not m else string[len(m.group(1)):]

    def __call__(self, lemmas: list) -> list:
        text, update_text = " ".join(lemmas), None
        neg = True
        while update_text != text:
            if update_text is not None:
                text = update_text
            if neg:
                update_text = self.cut_with_re(text, self._neg_cut).lstrip()
                if update_text != text:
                    neg = False
            update_text = self.cut_with_re(update_text, self._ignor_cut).lstrip()
        return update_text.split(), neg


def parse_negations(lemmas: list, dictionary: list, ignored: Union[None, list]=None) -> Tuple[list, bool]:
    """
    A deprecated wrapper for NegationParser factory.

    :param lemmas: A list of lemmas representing a text.
    :param dictionary: A list of negations.
    :param ignored: A list of words to ignore.

    :return: A tuple of two: (a list of lemmas, flag whether a negation was detected and removed).
    """
    neg_parser = NegationParser(dictionary, ignored)
    return neg_parser(lemmas)


def pos(wd, analyzer=GLOBAL_MYSTEM):
    """
    Determine a word's part of speech.

    :param wd: A word to assign pos to.
    :param analyzer: An analyzer to use to detect it.

    :return: A text part-of-speech label or, if detection failed, None.
    """
    analyses = analyzer.analyze(wd)
    if not analyses:
        return None
    dic = analyses[0]
    if "analysis" in dic and dic["analysis"]:
        ana_dic = dic["analysis"][0]
        if "gr" in ana_dic:
            m = re.search(r"^\w+", ana_dic["gr"])
            if m:
                return m.group(0)
    return None