import abc
import functools
import itertools
import logging
import re
from typing import Union, Iterable, Tuple, List

import editdistance
import enchant

from generalling import pos
from pymystem3 import Mystem

mystem = Mystem()

class Answer(object):
    """
    A class facilitating processing of an answer.
    """
    __russian_letter = re.compile(r"[а-яё]", flags=re.I)

    def __init__(self, string, line=-1):
        """
        Create a new answer instance.

        :param string: a text of an answer 'as is'.
        """
        self.line = line
        self._src = string.strip()
        lemmas = [(i.strip(), pos(i)) for i in mystem.lemmatize(self._src) if i.strip()]
        self._lemmas = list(itertools.dropwhile(lambda a: all(not i.isalpha() for i in a[0] or not a[0]), lemmas))
        text = [i["text"] for i in mystem.analyze(self._src) if i["text"].strip()]
        self._text = text[len(text) - len(self._lemmas):]
        assert len(self._text) == len(self._lemmas), "A number of word forms is not equal to a number of lemmas."

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

    @property
    def is_empty(self):
        return all(p is None or not self.__russian_letter.search(w) for w, p in self._lemmas)

    @property
    def source(self): return self._src

    @property
    def pos_tags(self):
        return [p for i, p in self._lemmas]


class SpellChecker(object):
    """
    A class acting as a factory of functions performing string's spell check.
    """

    def __init__(self, dict_name, *wordlists):
        if not enchant.dict_exists(dict_name):
            raise ValueError("A dictionary ")
        self.spellcheck_dict = enchant.Dict(dict_name)
        for word in itertools.chain(*wordlists):
            self.spellcheck_dict.add_to_session(word)

    def __call__(self, text: Iterable[Tuple[str, bool]]) -> List[str]:

        @functools.lru_cache(maxsize=300)
        def spellcheckme(word):
            if self.spellcheck_dict.is_added(word) or self.spellcheck_dict.check(word):
                return word
            suggestions = list(filter(lambda a: " " not in a, self.spellcheck_dict.suggest(word)))

            if not suggestions or word in suggestions:
                return word
            else:
                return min(suggestions, key=functools.cmp_to_key(editdistance.eval))

        return [spellcheckme(word) if is_questionable else word for word, is_questionable in text]


class BaseAnswer(object, metaclass=abc.ABCMeta):
    """
    A base class to represent an answer.
    """
    _mystem = Mystem()

    def __init__(self, text: str, include_punctuation: bool):
        """
        :param str text: A text of an answer.
        :param bool include_punctuation: A flag showing whether it's necessary to
            include punctuation in lemma representation of the text.
        """
        self.include_punctuation = include_punctuation

        self.src = text
        full_data = self._mystem.analyze(text)
        self._raw_words = [i["text"] for i in full_data]
        self._has_analysis = [bool(i.get("analysis", False)) for i in full_data]
        self._is_whitespace = [
            False if self._has_analysis[num]
            else not bool(self._raw_words[num].strip())
            for num in range(len(full_data))
            ]
        self._full_data = full_data

    @abc.abstractmethod
    def to_lemmas(self):
        """
        Get a list of lemmas of the text saved.

        :return: A list of lemmas.
        """

    def apply_negation_parser(self, parsing_func):
        return parsing_func(self.to_lemmas())


class SimpleAnswer(BaseAnswer):
    def to_lemmas(self):
        lemmas = [
            wd["analysis"][0]["lex"] if self._has_analysis[num]
            else wd["text"]
            for num, wd in enumerate(self._full_data)
            ]
        if self.include_punctuation:
            return [wd.strip().lower() for num, wd in enumerate(lemmas) if not self._is_whitespace[num]]
        else:
            return [wd.strip().lower() for num, wd in enumerate(lemmas) if self._has_analysis[num]]


class FullSpellcheckAnswer(BaseAnswer):

    spellchecker = SpellChecker("ru_RU")

    @property
    def _are_questionable(self):
        return [
            True if self._has_analysis[num] and self._full_data[num]["analysis"][0].get("qual") == "bastard"
            else False
            for num in range(len(self._full_data))
            ]

    def to_lemmas(self):
        spellchecked_words = self.spellchecker(zip(self._raw_words, self._are_questionable))
        analyses = [
            self._mystem.analyze(wd)[:-1]
            if self._has_analysis[num] and spellchecked_words[num] != self._raw_words[num]
            else [self._full_data[num]]
            for num, wd in enumerate(spellchecked_words)
            ]
        lemmas = [
            wd["analysis"][0]["lex"] if self._has_analysis[num]
            else
            wd["text"]
            for num, wd in enumerate(itertools.chain(*analyses))
            ]

        if self.include_punctuation:
            return [wd.strip().lower() for num, wd in enumerate(lemmas) if not self._is_whitespace[num]]
        else:
            return [wd.strip().lower() for num, wd in enumerate(lemmas) if self._has_analysis[num]]


class PartialSpellckeckAnswer(SimpleAnswer, FullSpellcheckAnswer):
    def to_lemmas(self):
        return SimpleAnswer.to_lemmas(self)

    def apply_negation_parser(self, parsing_func):
        normalized_lemmas = FullSpellcheckAnswer.to_lemmas(self)
        cut_words, neg = parsing_func(normalized_lemmas)
        real_lemmas = SimpleAnswer.to_lemmas(self)
        assert len(normalized_lemmas) == len(real_lemmas), "Incorrect processing of spellcheck."
        return real_lemmas[-len(cut_words):], neg