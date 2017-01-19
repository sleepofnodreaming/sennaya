import re
from typing import Union, Tuple

import pymystem3

GLOBAL_MYSTEM = pymystem3.Mystem()


def parse_negations(lemmas: list, dictionary: list, ignored: Union[None, list]=None) -> Tuple[list, bool]:
    """

    :param lemmas:
    :param dictionary:
    :param ignored:
    :return:
    """
    text = " ".join(lemmas)

    if ignored is not None:
        for i in ignored:
            if text.startswith(i):
                text = text[len(i):].strip()
                break

    for neg in dictionary:
        if text.startswith(neg + " "):
            text, positive = text[len(neg) + 1:].strip(), False
            break
    else:
        positive = True
    if ignored is not None:
        for i in ignored:
            if text.startswith(i):
                return text[len(i):].strip().split(), positive
    return text.split(), positive


def pos(wd, analyzer=GLOBAL_MYSTEM):
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