import itertools
import logging
import re
from typing import Union

from generalling import pos
from pymystem3 import Mystem

mystem = Mystem()

class Answer(object):
    """
    A class facilitating processing of an answer.
    """
    __russian_letter = re.compile(r"[а-яё]", flags=re.I)

    def __init__(self, string):
        """
        Create a new answer instance.

        :param string: a text of an answer 'as is'.
        """
        self._src = string.strip()
        lemmas = [(i.strip(), pos(i)) for i in mystem.lemmatize(self._src) if i.strip()]
        self._lemmas = list(itertools.dropwhile(lambda a: a[1] is None, lemmas))
        text = [i["text"] for i in mystem.analyze(self._src) if i["text"].strip()]
        self._text = text[len(text) - len(self._lemmas):]
        assert len(self._text) == len(self._lemmas), "A number of word forms is not equal to a number of lemmas."
        logging.info("New answer created, lemmas: {}".format(self._lemmas))

    def __len__(self):
        """
        Calculate length of an answer (in words).

        :return: a number of tokens (including punctuation).
        """
        return len(self._lemmas)

    def get_lemmas(self, skip_punct=True, as_string=False) -> Union[list, str]:
        """
        Get lemmas of an answer.

        :param skip_punct: If True, punctuation's omitted.
        :param as_string: If True, the result of a function's converted to a string (tokens are joined with a space).

        :return: a list or a string.
        """
        lemmas = [w for (w, p) in self._lemmas if not skip_punct or p]
        return " ".join(lemmas) if as_string else lemmas

    def shorten(self):
        """
        Cut off anything following the first lemma without POS.

        :return: A new instance of Answer with a shortemed lemma list.
        """
        for i, (l, p) in enumerate(self._lemmas):
            if p is None:
                shortened_answer = Answer(self._src)
                shortened_answer._text, shortened_answer._lemmas = self._text[:i], self._lemmas[:i]
                return shortened_answer
        return self

    @property
    def is_empty(self):
        return all(p is None or not self.__russian_letter.search(w) for w, p in self._lemmas)

    @property
    def source(self): return self._src

    @property
    def pos_tags(self):
        return [p for i, p in self._lemmas]