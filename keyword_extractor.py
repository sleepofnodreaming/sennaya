#!/usr/local/bin/python3

import argparse
import csv
import os
import re
import sys
from collections import Counter

import nltk
from nltk.collocations import *
from nltk.text import TextCollection
from pymystem3 import Mystem

from generalling import pos

GLOBAL_MYSTEM = Mystem()

START_PHRASE = [
    "мало",
    "много",
    "отсутствие",
    "становиться",
    "не хватать",
    "недостаток",
    "недостаточный количество",
    "недостаточный",
    "нет",
    "больше",
    "появляться",
    "больше",
    "не",
    "увеличиваться",
    "отсутствовать",
    "наличие",
    "убирать",
]


def convert_to_working_text(token_list):
    text = " ".join(token_list)
    m = re.search(r"\b(?:" + "|".join(START_PHRASE) + ") ([^,.;]+)(?:[.,;]|$)", text, flags=re.I)
    if m:
        return m.group(1).strip().split()
    return token_list


def generate_idf_keywords(texts, stopword_src=None, freq_threshold=0, avail_pos=None):
    def appropriate_pos(tag):
        if avail_pos is None:
            return True
        return tag in avail_pos

    # reading stop words from a stop word file (one word per line, everything's lowercase).
    if stopword_src is None:
        stop_words = set()
    else:
        with open(stopword_src) as f:
            stop_words = {i.strip() for i in f}
    text_collection = TextCollection(texts)

    # Frequency distribution should include tokens including any letters only.
    fd = Counter((i for i in text_collection.tokens if not re.search(r'^[\W]+$', i) and i not in stop_words))

    ms = GLOBAL_MYSTEM

    for i in sorted(fd.keys(), key=lambda a: text_collection.idf(a)):
        if fd[i] > freq_threshold and appropriate_pos(pos(i, ms)) and len(i) > 1:
            yield i, fd[i]


def csv_to_lemmas(fn, column_number, skip_nonalpha=False, pattern=lambda a: a):
    texts = []
    ms = GLOBAL_MYSTEM
    with open(fn) as f:
        reader = csv.reader(f, delimiter=",")
        for line in reader:
            if column_number >= len(line):
                continue
            value = line[column_number]
            lemmas = pattern([i.strip() for i in ms.lemmatize(value) if i.strip()])
            if skip_nonalpha:
                lemmas = list(filter(lambda i: not re.search(r'^[\W]+$', i), lemmas))
            texts.append(lemmas)
    if not texts:
        print("No lines containing column No.{} found.".format(column_number), file=sys.stderr)
    return texts


def several_columns_to_lemmas(fn, column_numbers, skip_nonalpha=False, pattern=lambda a: a):
    texts = []
    for i in column_numbers:
        texts.extend(csv_to_lemmas(fn, i, skip_nonalpha, pattern))
    return texts


def get_keywords(csv_path, stopword_path, col_num, threshold, line_preparation):
    texts = several_columns_to_lemmas(csv_path, col_num, False, line_preparation)
    return (i for i, j in generate_idf_keywords(texts, stopword_path, threshold, {"S"}))


def bigram_filter_factory(stop_word_src, one_word_dic):
    if stop_word_src:
        with open(stop_word_src) as f:
            stop_words = {i.strip() for i in f}
    else:
        stop_words = set()

    def bigram_filter(bigram):
        stop_pos = {"PR", "CONJ", "ADV"}
        oblig_pos = {"A", "V", "S"}

        word1, word2 = bigram
        pos_1, pos_2 = pos(word1, GLOBAL_MYSTEM), pos(word2, GLOBAL_MYSTEM)
        if (not (pos_1 in stop_pos or pos_2 in stop_pos)) and (pos_1 in oblig_pos or pos_2 in oblig_pos):
            if word1 not in stop_words and word1 not in stop_words:
                if word1 not in one_word_dic or word2 not in one_word_dic:
                    if len(word1) > 1 and len(word2) > 1:
                        return True
        return False

    return bigram_filter


def get_bigrams(csv_path, col_num, filtering_condition, line_preparation):
    lemmatized_texts = several_columns_to_lemmas(csv_path, col_num, True, line_preparation)
    bigram_measures = nltk.collocations.BigramAssocMeasures()
    finder = BigramCollocationFinder.from_documents(lemmatized_texts)
    for ngram in finder.nbest(bigram_measures.poisson_stirling, 300):
        if filtering_condition(ngram):
            yield ngram


def filter_trigrams(trigram):
    cond = lambda sp: False if sp is None or sp == "PR" else True
    return cond(pos(trigram[0], GLOBAL_MYSTEM)) and cond(pos(trigram[2], GLOBAL_MYSTEM))


def get_trigrams(csv_path, col_num, filtering_condition, line_preparation):
    trigram_measures = nltk.collocations.TrigramAssocMeasures()
    finder = TrigramCollocationFinder.from_documents(several_columns_to_lemmas(csv_path, col_num, True, line_preparation))
    for ngr in finder.nbest(trigram_measures.poisson_stirling, 300):
        if filtering_condition(ngr):
            yield ngr


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("csv", type=str, metavar="PATH", help="A path to a csv table to process.")
    parser.add_argument("column", type=int, metavar="NUM", nargs="+", help="A number of column to process.")
    parser.add_argument("-n", "--ngram", type=int, metavar="WORD_NUM", default=1,
                        help="A number of words in an ngram (0 < n < 4).")
    parser.add_argument("-s", "--stop_words", type=str, metavar="PATH",
                        help="A path to a file containing stop words (one per line).")
    parser.add_argument("-c", "--cut_lines_by_template", action="store_true",
                        help="Choose whether a content of a table should be cut.")

    data = parser.parse_args()
    data.csv = os.path.expanduser(os.path.abspath(data.csv))
    data.column = [i - 1 for i in data.column]
    if data.stop_words is not None:
        data.stop_words = os.path.expanduser(os.path.abspath(data.stop_words))
    if data.ngram > 3 or data.ngram < 1:
        print("Incorrect ngram length: {}.".format(data.ngram), file=sys.stderr)
        raise ValueError()
    if not os.path.isfile(data.csv):
        print("File does not exist: {}".format(data.csv), file=sys.stderr)
        raise ValueError()
    if data.stop_words is not None:
        if not os.path.isfile(data.stop_words):
            print("File does not exist: {}".format(data.stop_words), file=sys.stderr)
            raise ValueError()
    if data.ngram == 3 and data.stop_words is not None:
        print("File will be ignored: {}.".format(data.stop_words), file=sys.stderr)
    return data


if __name__ == "__main__":

    THRESHOLD_ONE = 5
    THRESHOLD_TWO = 4

    try:
        args = parse_args()
    except ValueError:
        sys.exit(1)

    func = convert_to_working_text if args.cut_lines_by_template else (lambda a: a)

    if args.ngram == 1:
        for i in get_keywords(args.csv, args.stop_words, args.column, THRESHOLD_ONE, func):
            print(i)
    elif args.ngram == 2:
        one_word_dic = set(get_keywords(args.csv, args.stop_words, args.column, THRESHOLD_TWO, func))
        if not one_word_dic:
            print("No dic compiled. Exiting...", file=sys.stderr)
            sys.exit()
        bigram_filter = bigram_filter_factory(args.stop_words, one_word_dic)
        for i in get_bigrams(args.csv, args.column, bigram_filter, func):
            print(*i)
    else:
        for i in get_trigrams(args.csv, args.column, filter_trigrams, func):
            print(*i)
