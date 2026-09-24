"""Quantitative school summaries from the two editable discussion bodies.

Counts refer to the selected receipt month. A target is configured per draft;
no annual scope or denominator is inferred. Structured Paper entries are counted
once by title/venue, independent of acknowledgement or publication-status labels.
"""
from collections import Counter, defaultdict
import re
from mmlab_pipeline.members import fold, resolve_members, DIRECTORY
from school_report import filtered_body

RANKS = ('Q1','Q2','Q3','Q4','A* và A','Rank B','Rank C','Scopus khác')
PAPER_ROW = re.compile(r'^(?P<title>.+) — (?P<venue>.*?); (?P<rank>[^;]+); (?P<index>.+?) \((?P<owners>[^\n]*)\)$')
QUANTITY = r'(\d+|mot)'
PAPER_NUMBER = re.compile(QUANTITY + r'\s+(?:bai(?: bao)?|papers?|journals?)\b(?:\s+(tap chi|hoi nghi))?(?:\s+(q[1-4]|scopus|isi))?')
NEGATED = re.compile(r'\b(?:chua|khong|huy|hoan lai|khong con)\b')
PREPARATION = re.compile(r'\b(?:chuan bi|du kien|se|cho|dang chuan bi)\b')


def clean_task(text):
    owner = re.search(r'\s+\(([^()]*)\)\s*$', text)
    owners = tuple(m['id'] for m in resolve_members(owner.group(1))) if owner else ()
    if owner and owners:
        text = text[:owner.start()]
    # Dates must never be misread as a task quantity or a doctoral stage.
    text = re.sub(r'^\s*(?:\d{4}-\d{1,2}-\d{1,2}|\d{1,2}(?:-\d{1,2})?/\d{1,2}(?:/\d{4})?)\s*[,.:–-]?\s*', '', text)
    return text.strip().rstrip('.'), owners


def qty(value):
    n = 1 if value == 'mot' else int(value)
    return n if 0 < n <= 10000 else None


def number_before(value, noun, owners):
    match = re.search(QUANTITY + r'\s+(?:ho so\s+)?(?:' + noun + r')\b', value)
    if match:
        return qty(match.group(1))
    # Singular project declarations or individual doctoral reports can denote one.
    if re.search(r'\b(?:cac|nhieu|nhung)\b', value):
        return None
    if noun == 'de tai' and re.search(r'\bde tai\b', value):
        return 1
    if noun != 'de tai' and len(owners) == 1 and not re.search(r'\b(?:hai|ba|bon|nam|sau|bay|tam|chin|muoi)\s+(?:ncs|nghien cuu sinh)\b',value):
        return 1
    return None


def paper_catalog(rows, notes):
    papers = {}
    for text in rows:
        match = PAPER_ROW.fullmatch(text)
        if not match:
            continue
        row = match.groupdict()
        if not resolve_members(row['owners']):
            continue
        key = (fold(row['title']).strip(), re.sub(r'\W+', '', fold(row['venue'])))
        entry = papers.setdefault(key, {'indices':set(), 'ranks':set()})
        tokens = set(re.findall(r'[a-z]+', fold(row['index'])))
        if tokens and tokens <= {'scopus','isi','and','va'}:
            entry['indices'].update(tokens & {'scopus','isi'})
        rank = row['rank'].upper().strip()
        if rank in ('Q1','Q2','Q3','Q4','A*','A','B','C','C-UNRANKED','Q-UNRANKED'):
            entry['ranks'].add(rank)
    ranks = Counter();isi_only = 0
    for entry in papers.values():
        if 'scopus' not in entry['indices']:
            isi_only += int('isi' in entry['indices'])
            if not entry['indices']:notes.append('Có công trình chưa đủ thông tin chỉ mục để tính tổng Scopus.')
            continue
        rank = next(iter(entry['ranks'])) if len(entry['ranks']) == 1 else ''
        if len(entry['ranks']) > 1:notes.append('Có công trình khai báo nhiều hạng khác nhau; chỉ tính một lần ở Scopus khác.')
        bucket = rank if rank in ('Q1','Q2','Q3','Q4') else 'A* và A' if rank in ('A*','A') else 'Rank '+rank if rank in ('B','C') else 'Scopus khác'
        ranks[bucket] += 1
    return {'works':len(papers),'scopus':sum(ranks.values()),'isiOnly':isi_only,'ranks':dict(ranks)}


def milestone(value):
    cd = re.search(r'\b(?:chuyen de|cd)\s*([123])\b', value)
    if cd:return 'chuyên đề '+cd.group(1)
    for pattern, label in [(r'tieu luan tong quan|tltq','tiểu luận tổng quan'),
                           (r'don vi chuyen mon|dvcm','đơn vị chuyên môn'),
                           (r'cap truong','cấp Trường'), (r'seminar','seminar')]:
        if re.search(pattern,value):return label
    return None


def project_level(value):
    after = value.split('de tai',1)[-1]
    match = re.search(r'\b(?:cap\s+)?(d[12]|cs\d+|nafosted|dhqg|bo|co so|[abc])\b',after)
    if not match:return ''
    return {'bo':'Bộ','dhqg':'ĐHQG','co so':'cơ sở'}.get(match.group(1),match.group(1).upper())


def aggregate_tasks(rows, phase, catalog, notes):
    totals = Counter(); seen = set(); declarations = []
    for kind, raw in rows:
        if kind == 'paper' and PAPER_ROW.fullmatch(raw):continue
        text, owners = clean_task(raw); value = fold(text)
        if NEGATED.search(value):continue
        # Completed reports may still contain a future intent. It is not a result.
        if phase == 'a' and PREPARATION.search(value):continue
        if kind == 'paper':
            if phase == 'a' and re.search(r'\bhoan thanh\s+\d+(?:\s*/\s*\d+)?\s+bai(?: bao)?\s+scopus\b',value):
                declarations.append(text);continue
            action = 'nộp' if re.search(r'\b(?:nop|submit|resubmit)\b',value) else 'hoàn thành' if re.search(r'\bhoan thanh\b',value) else None
            if not action:
                notes.append('Có nội dung bài báo chưa nêu số lượng và hành động đủ rõ để tổng hợp.');continue
            found = list(PAPER_NUMBER.finditer(value))
            if not found:
                notes.append('Có kế hoạch bài báo chưa nêu số lượng; không tự quy đổi một dòng thành một bài.');continue
            for match in found:
                n = qty(match.group(1))
                if n is None:continue
                journal, rank = match.group(2), match.group(3)
                label = 'bài tạp chí '+rank.upper() if rank and rank.startswith('q') else 'bài báo '+{'hoi nghi':'hội nghị','tap chi':'tạp chí'}[journal] if journal else 'bài báo '+rank.upper() if rank else 'bài báo'
                identity = (kind,action,fold(text),owners if n==1 else (),match.start())
                if identity not in seen:
                    seen.add(identity);totals[(kind,action,label)] += n
            continue
        if kind == 'ncs':
            stage = milestone(value)
            if phase == 'a':
                action = 'mới' if re.search(r'\b(?:duoc|moi|da)\b.*\bcong nhan\b|\bcong nhan them\b',value) else 'báo cáo '+stage if stage and re.search(r'\b(?:hoan thanh|xong|da bao cao)\b',value) else 'nhập học' if re.search(r'\b(?:da|hoan thanh)\b.*\bnhap hoc\b',value) else None
            else:
                action = 'nộp hồ sơ' if re.search(r'\b(?:nop|chuan bi)\b.*\bho so\b',value) else 'báo cáo '+stage if stage else 'nhập học' if 'nhap hoc' in value else None
            n = number_before(value, 'ncs|nghien cuu sinh|phd', owners)
            level = ''
        else:
            action = 'nghiệm thu' if 'nghiem thu' in value else 'đăng ký' if 'dang ky' in value else None
            # Submitting acceptance paperwork is not completed project acceptance.
            if phase == 'a' and re.search(r'\b(?:ho so|nop|de nghi|de xuat)\b',value):action=None
            if phase == 'b' and action and ('ho so' in value or 'chuan bi' in value):action='chuẩn bị '+action
            n = number_before(value,'de tai',owners);level = project_level(value)
        if not action or n is None:
            notes.append('Có nội dung NCS/đề tài chưa nêu rõ số lượng hoặc mốc thực hiện; chưa đưa vào tổng số.');continue
        # Duplicate batch declarations are counted once; individual reports retain
        # their resolved reporter to distinguish different researchers.
        identity = (kind,action,level,value,owners if n == 1 and kind == 'ncs' else ())
        if identity not in seen:
            seen.add(identity);totals[(kind,action,level)] += n
    return totals, list(dict.fromkeys(declarations))


def render_tasks(totals, phase):
    lines = [];paper_groups = defaultdict(list)
    order=lambda item: ({'paper':0,'ncs':1,'project':2}[item[0][0]],0 if item[0][1]=='mới' else 1,item[0][1],item[0][2])
    for (kind,action,label), n in sorted(totals.items(),key=order):
        if kind == 'paper':
            paper_groups[action].append((0 if 'tạp chí' in label else 1 if 'hội nghị' in label else 2,f'{n:02d} {label}'))
        elif kind == 'ncs':
            if action == 'mới':lines.append(f'KPI NCS: mới được công nhận thêm {n:02d} NCS.')
            elif action == 'nộp hồ sơ':lines.append(f'KPI NCS: chuẩn bị nộp {n:02d} hồ sơ NCS.')
            elif action.startswith('báo cáo '):
                stage=action[len('báo cáo '):]
                lines.append(f'{n:02d} NCS '+('đã báo cáo xong ' if phase=='a' else 'sẽ báo cáo ')+stage+'.')
            else:lines.append(f'{n:02d} NCS '+('đã ' if phase=='a' else 'sẽ ')+action+'.')
        else:
            verb=action[:1].upper()+action[1:]
            lines.append(f'{verb} {n} đề tài'+(' '+label if label else '')+'.')
    paper_lines = [f'KPI bài báo: '+('đã ' if phase=='a' else '')+action+' '+', '.join(v for _,v in sorted(values))+'.' for action,values in sorted(paper_groups.items())]
    return paper_lines + lines


def summarize(report):
    notes=[];phase_rows={}
    for phase in ('a','b'):
        rows=[]
        for line in filtered_body(report['sections'].get(phase+'1','')).splitlines():
            prefix,_,text=line.partition(': ')
            kind={'KPI bài báo':'paper','KPI NCS':'ncs','Đề tài NCKH':'project'}[prefix]
            rows.append((kind,text))
        phase_rows[phase]=rows
    paper_rows=[v for k,v in phase_rows['a'] if k=='paper']
    scope=report.get('paperScope','month')
    if scope=='year':paper_rows+=report.get('paperHistory',[])
    catalog=paper_catalog(paper_rows,notes)
    target=report.get('scopusTarget')
    output={};metrics={'paper':catalog,'period':report['period'],'paperScope':scope,'scopusTarget':target}
    for phase in ('a','b'):
        totals,declarations=aggregate_tasks(phase_rows[phase],phase,catalog,notes)
        lines=[]
        if phase=='a' and catalog['scopus']:
            n=catalog['scopus'];ratio=f'{n} / {target}' if target is not None else str(n)
            parts=[f'{rank}: {catalog["ranks"][rank]} bài' for rank in RANKS if catalog['ranks'].get(rank)]
            scope_label=f' (lũy kế năm {report["period"][:4]} đến {report["period"][5:]}/{report["period"][:4]})' if scope=='year' else ''
            lines.append(f'KPI bài báo{scope_label}: hoàn thành {ratio} bài báo Scopus. Trong đó: '+', '.join(parts)+'.')
        if phase=='a' and catalog['isiOnly']:
            lines.append(f'KPI bài báo: {catalog["isiOnly"]} bài ISI ngoài nhóm Scopus.')
        if phase=='a' and declarations:
            if catalog['works']:
                notes.append('Có cả tổng số bài báo khai báo và danh sách Paper; dùng danh sách công trình, không cộng chồng tổng số.')
            elif len(declarations)==1:
                lines.append('KPI bài báo: '+declarations[0].rstrip('.')+'.')
                notes.append('Tổng số bài báo lấy từ dòng tổng hợp khai báo; chưa đối chiếu với danh sách công trình.')
            else:notes.append('Có nhiều tổng số bài báo khai báo khác nhau; cần thống nhất một tổng số.')
        lines.extend(render_tasks(totals,phase))
        output[phase]='\n'.join(lines)
        metrics[phase]=[{'category':k,'action':action,'group':group,'count':n} for (k,action,group),n in sorted(totals.items())]
    return {**output,'metrics':metrics,'notes':list(dict.fromkeys(notes))}


def prior_papers(records, period):
    """Earlier receipt months in the same year; current month's editable body wins."""
    result=[]
    for row in records:
        stamp=row.get('date','')[:7]
        if row.get('deletedAt') or row.get('type')!='Paper' or not stamp.startswith(period[:4]+'-') or stamp>=period:
            continue
        names=', '.join(m['name'] for m in DIRECTORY if m['id'] in row.get('memberIds',[]))
        if names:
            result.append(f"{row['title']} — {row.get('venue') or 'chưa có venue'}; {row.get('ranking') or 'chưa có ranking'}; {row.get('index') or 'chưa có index'} ({names})")
    return result
