"""
A module containing all commonly used project's linguistic things.
"""

import enchant
import itertools
import pymystem3
import re

from typing import Union, Tuple, List

GLOBAL_MYSTEM = pymystem3.Mystem()


class NegationParser(object):
    """
    A class working as a factory of functions parsing negations.
    """
    def __init__(self, negation_dict: dict, ignoring_dict: Union[dict, None]):
        self._negation_dict = negation_dict
        self._ignoring_dict = ignoring_dict
        self._neg_cut = re.compile(r'\b(' + r'|'.join(self._negation_dict.keys()) + r')\b')
        self._ignor_cut = None if self._ignoring_dict else re.compile(r'\b(' + r'|'.join(self._ignoring_dict.keys()) + r')\b')
        self._nps = re.compile(r'(?<!\b\w)\s*(?:[,]+| -)(?! (?:котор|\w{1,3}\s+котор|где|что|а |как))', flags=re.I)

    @staticmethod
    def _cut_with_re(string, regex):
        if regex is None:
            return string, None
        m = regex.match(string)
        return (string.lstrip(), None) if not m else (string[len(m.group(1)):], m.group(1))

    def parse_negations(self, lemmas: list) -> list:
        text, update_text, last = " ".join(lemmas).lower(), None, None
        neg = True
        final_last = None
        while update_text != text:
            if update_text is not None:
                text = update_text
            update_text, last = self._cut_with_re(text, self._neg_cut)
            if last: final_last = last
            if update_text != text: neg = False
            if self._ignor_cut is not None:
                update_text, last = self._cut_with_re(update_text, self._ignor_cut)
                if last: final_last = last

        if final_last in self._negation_dict:
            previous_grammars = self._negation_dict[final_last]
        else:
            previous_grammars = self._ignoring_dict.get(final_last, [])

        return update_text, neg, previous_grammars

    def to_chunks(self, sentence, chunk_constructor):

        def grammar_is_analogous_to(previous_grammars, full_data):
            for word in full_data:
                analysis = word.get("analysis")
                if not analysis:
                    continue
                grammar = analysis[0].get("gr", "")
                if any(i in grammar for i in previous_grammars):
                    return True
            return False

        def reorganize_nom_chunks(chunk):
            if " и " not in chunk:
                return [chunk]
            subchunks = chunk.split(" и ")
            for subchunk in subchunks:
                chunk_part = chunk_constructor(subchunk, True)
                nouns = list(filter(lambda gr: "S" in gr, chunk_part.grammars()))
                if not nouns:
                    return [chunk]
                if not all("им" in i for i in nouns):
                    return [chunk]
            return subchunks

        supposed_parts = list(map(lambda a: a.strip(), self._nps.split(sentence)))
        supposed_parts = itertools.chain.from_iterable(reorganize_nom_chunks(part) for part in supposed_parts)

        resulting_chunks, current_chunk, chunk_is_positive, previous_grammars = [], [], True, None
        for chunk in supposed_parts:
            sentence_part = chunk_constructor(chunk, True)
            words, is_negative, last_part_grammars = sentence_part.apply_negation_parser(lambda a: self.parse_negations(a))

            if not is_negative:
                if current_chunk:
                    resulting_chunks.append((" , ".join(current_chunk), chunk_is_positive))
                current_chunk, chunk_is_positive, previous_grammars = [words], is_negative, last_part_grammars
            else:
                if not current_chunk:
                    current_chunk, chunk_is_positive, previous_grammars = [words], is_negative, last_part_grammars

                else:
                    if previous_grammars is None or last_part_grammars is not None:
                        if current_chunk:
                            resulting_chunks.append((" , ".join(current_chunk), chunk_is_positive))
                        current_chunk, chunk_is_positive, previous_grammars = [words], is_negative, last_part_grammars
                        continue

                    if grammar_is_analogous_to(previous_grammars, sentence_part.full_data):
                        if not chunk_is_positive:
                            resulting_chunks.append((" , ".join(current_chunk), chunk_is_positive))
                            current_chunk = [words]
                        else:
                            current_chunk.append(words)
                    else:
                        resulting_chunks.append((" , ".join(current_chunk), chunk_is_positive))
                        current_chunk, chunk_is_positive, previous_grammars = [words], is_negative, last_part_grammars
        if current_chunk:
            resulting_chunks.append((" , ".join(current_chunk), chunk_is_positive))
        return resulting_chunks


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


class SpellcheckNorm(object):
    """
    A class acting as a factory of functions performing string's spell check.
    """
    def __init__(self, dict_name, *wordlists):
        if not enchant.dict_exists(dict_name):
            raise ValueError("A dictionary ")
        self.spellcheck_dict = enchant.Dict(dict_name)
        for word in itertools.chain(*wordlists):
            self.spellcheck_dict.add_to_session(word)
        self._wds = re.compile(r'\b([\w-]+)\b', flags=re.U | re.I)

    def __call__(self, text):

        def spellckeck_required(wd):
            analyses = GLOBAL_MYSTEM.analyze(wd)
            if not analyses:
                return True
            dic = analyses[0]
            if "analysis" in dic and dic["analysis"]:
                ana_dic = dic["analysis"][0]
                if ana_dic.get("qual") == "bastard":
                    return True
            return False

        def spellcheckme(match):
            if self.spellcheck_dict.is_added(match.group(1)) or self.spellcheck_dict.check(match.group(1)):
                return match.group(1)
            if not spellckeck_required(match.group(1)):
                return match.group(1)
            suggestions = self.spellcheck_dict.suggest(match.group(1))
            return match.group(1) if not suggestions or match.group(1) in suggestions else suggestions[0]

        return self._wds.sub(spellcheckme, text)
