#!/usr/local/bin/python3

import csv
import logging
import os
import re
import sys
import time
from collections import namedtuple, Counter

from answer import Answer
from readers import read_columns
from rules.alexandrovsky import QUESTIONED, Postprocs

logging.basicConfig(format='[%(asctime)s] %(levelname)s: %(message)s', level=logging.INFO, stream=sys.stderr)


def iter_column(fn, col_number):
    return (Answer(text) for _, text in read_columns(fn, col_number))


OutputFiles = namedtuple("OutputFiles", ["clear", "questioned", "trash"])


def generate_output_paths(directory=None):
    time_string = time.strftime("%Y_%m_%d_%H_%M")
    patterns = [
        "output_clear_{}.csv",
        "output_questioned_{}.csv",
        "output_trash_{}.csv",
    ]
    names = map(lambda a: a.format(time_string), patterns)
    if directory:
        names = map(lambda a: os.path.join(directory, a), names)
    return OutputFiles(*names)


def parse_args():
    import argparse
    parser = argparse.ArgumentParser(description="A script classifying respondents' answers using a dictionary.")
    parser.add_argument("csv", type=str, metavar="PATH", help="a path to a file to process")
    parser.add_argument("column", type=int, metavar="NUM", help="a number of a column to get answers from")
    parser.add_argument("dic", type=str, metavar="PATH", help="a path to a dictionary to use")
    parser.add_argument("-d", "--delimiter", type=str, default="\t", metavar="SYMBOL",
                        help="a symbol to use as a delimiter in the output")
    parser.add_argument(
        "-o", "--output", type=str, metavar="PATH",
        help="a path to a directory to put the results to (by default they're saved to a dir where the script's located)"
    )
    parsed = parser.parse_args()
    parsed.csv = os.path.expanduser(os.path.abspath(parsed.csv))
    parsed.dic = os.path.expanduser(os.path.abspath(parsed.dic))
    if parsed.output is not None:
        parsed.output = os.path.expanduser(os.path.abspath(parsed.output))

    assert parsed.column >= 0
    assert os.path.isfile(parsed.csv)
    assert os.path.isfile(parsed.dic)
    assert parsed.output is None or os.path.isdir(parsed.output)
    assert len(parsed.delimiter) == 1
    return parsed


if __name__ == "__main__":
    args = parse_args()

    postproc_seq = [
        Postprocs.no_change_postproc,
        Postprocs.parking_postproc,
        Postprocs.zoo_postproc,
        Postprocs.bridge_processing,
        Postprocs.traffic_processing,

    ]

    matches = {}
    regexes = {}
    with open(args.dic) as kwf:
        reader = csv.reader(kwf, delimiter=",")
        for line in reader:
            hl, *kws = line
            for kw in kws:
                if kw:
                    matches[kw] = hl
                    regexes[kw] = re.compile(r'\b{}\b'.format(kw), flags=re.I)

    results = []
    all_tags = []

    for answer_instance in iter_column(args.csv, args.column):
        lemmas_text = answer_instance.get_lemmas(skip_punct=False, as_string=True).lower()
        hls = set()
        for m in matches:
            if regexes[m].search(lemmas_text):
                logging.info("Found: '%s' in <<%s>>", m, lemmas_text)
                hls.add(matches[m])
        if not hls:
            logging.info("Unprocessed: %s", lemmas_text)

        for postproc in postproc_seq:
            postproc(answer_instance, hls)

        results.append((answer_instance.source, hls))
        all_tags.extend(hls)

    all_tags = Counter(all_tags)

    for i in sorted(all_tags.keys()):
        print(i, all_tags[i], file=sys.stderr)

    header_tagging = sorted(all_tags.keys())
    header = ["ID", "Исходный текст"] + header_tagging

    out_paths = generate_output_paths(args.output)

    with open(out_paths.clear, "w") as clear_file, open(out_paths.questioned, "w") as questioned_file, open(
            out_paths.trash, "w") as trash_file:
        c_writer = csv.writer(clear_file, delimiter=args.delimiter, quoting=csv.QUOTE_MINIMAL)
        q_writer = csv.writer(questioned_file, delimiter=args.delimiter, quoting=csv.QUOTE_MINIMAL)
        t_writer = csv.writer(trash_file, delimiter=args.delimiter, quoting=csv.QUOTE_MINIMAL)

        # c_writer.writerow(header)
        # q_writer.writerow(header)
        # t_writer.writerow(header)

        for num, (answer, tags) in enumerate(results):
            if not tags or "?" in tags and len(tags) == 1:
                active_writer = t_writer
            elif tags & QUESTIONED:
                active_writer = q_writer
            else:
                active_writer = c_writer
            line = [str(num + 2), answer] + sorted(tags) + [""] * (
                len(header_tagging) - len(tags))  # ["" if i not in tags else i for i in header_tagging]
            active_writer.writerow(line)
