"""Conservative label normalization; never fuzzy-match member identities."""
import math
import re
from collections import Counter
from .members import fold


def key(value):
    return re.sub(r'[\s\-‐‑–—]+', ' ', fold(value)).strip()


def cosine(a, b):
    def grams(s):
        s = '^' + key(s) + '$'
        return Counter(s[i:i+n] for n in (2, 3) for i in range(len(s)-n+1))
    a, b = grams(a), grams(b)
    norm = math.sqrt(sum(v*v for v in a.values()) * sum(v*v for v in b.values()))
    return sum(v*b[g] for g,v in a.items()) / norm if norm else 0.0


def normalize_role(value):
    if not isinstance(value, str):
        return value
    aliases = {'first author':'First author','first authors':'First author','tac gia chinh':'First author',
               'co author':'Co-author','co authors':'Co-author','coauthor':'Co-author',
               'coauthors':'Co-author','dong tac gia':'Co-author'}
    k = key(value)
    if k in aliases:
        return aliases[k]
    # Only short English role typos; reject negations and unrelated roles.
    if len(k.split()) > 2 or re.search(r'\b(?:not|no|non|khong)\b', k):
        return value
    scores = sorted(((cosine(k, candidate), canonical) for candidate,canonical in
                     [('first author','First author'),('co author','Co-author')]), reverse=True)
    if scores[0][0] >= .78 and scores[0][0]-scores[1][0] >= .15:
        return scores[0][1]
    return value


def normalize_ranking(value):
    if not isinstance(value, str):
        return value
    aliases={key(v):v for v in ('A*','A','B','C','C-Unranked','Q1','Q2','Q3','Q4','Q-Unranked')}
    aliases.update({'c unrank':'C-Unranked','q unrank':'Q-Unranked',
                    'a ranked':'A','b ranked':'B','c ranked':'C'})
    return aliases.get(key(value), value)
