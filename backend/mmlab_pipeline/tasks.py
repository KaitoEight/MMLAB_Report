"""Conservative repair of line wrapping; no completion of missing prose."""
import re
import unicodedata
from datetime import date

BULLET=re.compile(r'^(?:[-*•+]\s+|\d+[.)]\s+)')
DATE_PREFIX=re.compile(r'^(?P<date>\d{4}-\d{2}-\d{2}|\d{1,2}(?:\s*[-–]\s*\d{1,2})?/\d{1,2}(?:/\d{4})?)(?:\s*[,;:]\s*|\s+)(?P<text>.+)$')
# Only clear grammatical continuations. Independent actions remain separate.
CONTINUATION=re.compile(r'^(?:tạp chí\b|hội nghị[, ]|trong\b|với\b|về\b|cho\b|của\b|và\b|để\b|bài toán\b|track\b)',re.I)


def display_date(value):
    s=value.strip()
    try:
        if re.fullmatch(r'\d{4}-\d{2}-\d{2}',s):return date.fromisoformat(s).strftime('%d/%m/%Y')
        if re.fullmatch(r'\d{1,2}/\d{1,2}/\d{4}',s):
            d,m,y=map(int,s.split('/'));return date(y,m,d).strftime('%d/%m/%Y')
    except ValueError:pass
    return s


def clean_text(value):
    s=re.sub(r'\s+',' ',value).strip()
    # An explicit, narrow typo alias. No fuzzy rewriting of scientific names.
    return re.sub(r'\bkhoa họca\b','khoa học',s)


def task_key(task):
    text=unicodedata.normalize('NFC',task['content']).casefold().rstrip(' .;')
    return (display_date(task['date']),text)


def repair_tasks(values, *, join_wrapped=True):
    """Accept stored task dictionaries or raw lines. Preserve distinct dates/bullets."""
    assembled=[]
    for value in values or []:
        raw=value.get('content','') if isinstance(value,dict) else str(value)
        explicit_date=value.get('date','') if isinstance(value,dict) else ''
        for i, line in enumerate(raw.splitlines()):
            line=line.strip();marked=bool(BULLET.match(line));line=BULLET.sub('',line).strip()
            if not re.search(r'\w',line):continue
            when=explicit_date if i==0 else ''
            match=DATE_PREFIX.match(line)
            if not when and match:when,line=match['date'],match['text']
            line=clean_text(line)
            closes_quote=bool(assembled and ((assembled[-1]['content'].count('"')%2 and '"' in line)
                              or (assembled[-1]['content'].count('“')>assembled[-1]['content'].count('”') and '”' in line)))
            if join_wrapped and assembled and not marked and not when and (CONTINUATION.match(line) or closes_quote):
                assembled[-1]['content']+=' '+line
            else:assembled.append({'date':display_date(when),'content':line})
    # Deduplicate complete tasks, never their identical opening fragments.
    seen=set();out=[]
    for task in assembled:
        key=task_key(task)
        if key not in seen:out.append(task);seen.add(key)
    return out


def format_task(task):
    return (task['date']+': ' if task['date'] else '')+task['content']


def task_lines(value):
    return [format_task(t) for t in repair_tasks(value.splitlines())]
