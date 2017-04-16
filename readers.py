"""
A collection of various readers for different types of files.
"""

import csv
import logging

from typing import List, Tuple
from collections import OrderedDict


def read_csv_dictionaries(fns, ignore_fst_col, delimiter=","):
    matches = OrderedDict()
    for fn in fns:
        with open(fn) as kwf:
            reader = csv.reader(kwf, delimiter=delimiter)
            for line in reader:
                if not line:
                    continue
                if ignore_fst_col:
                    hl, *kws = line
                else:
                    hl, kws = line[0], line

                for kw in filter(lambda a: a, kws):
                    if kw not in matches:
                        matches[kw] = set()
                    matches[kw].add(hl)
    return matches


def read_wordlists(fns, as_csv=True):
    """
    Read files and compile a word list from the data read.

    :param fns: A list of paths to files.
    :param as_csv: The files given are CSVs. It means that each table cell will be treated as a separate word.

    :return: A list of words.
    """

    def _iter_lines(file):
        for line in file:
            line = line.strip()
            if line:
                yield [line]

    s = set()
    words = []
    for fn in fns:
        with open(fn) as kwf:
            reader = _iter_lines(kwf) if not as_csv else csv.reader(kwf, delimiter=",")
            for line in reader:
                for w in line:
                    if w not in s:
                        words.append(w)
                        s.add(w)
    return words


def read_columns(fn: str, *columns: List[int]) -> List[Tuple[int, str]]:
    """
    Read text from all the columns specified.

    :param fn: A path to a table file.
    :param columns: A list of column numbers to read data from (WARNING: nums should start from 1).

    :return: A list of pairs (line number, answer text).
    """
    answers = []
    ignored_lines = set()
    with open(fn) as f:
        reader = csv.reader(f, delimiter=",")
        next(reader, None)
        for num, line in enumerate(reader):
            line_snapshot = tuple(i.strip() for i in line[1:])
            if line_snapshot in ignored_lines:
                logging.warning("Line's a duplicate: %s", line_snapshot)
                continue
            ignored_lines.add(line_snapshot)
            line = [i.strip() for n, i in enumerate(line) if i.strip() and n + 1 in columns]
            answers.extend(((num + 2, i) for i in set(line)))
    return answers