import csv


def read_csv_dictionaries(fns, ignore_fst_col):
    matches = {}
    for fn in fns:
        with open(fn) as kwf:
            reader = csv.reader(kwf, delimiter=",")
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


def _iter_lines(file):
    for line in file:
        line = line.strip()
        if line:
            yield [line]


def read_wordlists(fns, as_csv=True):
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
