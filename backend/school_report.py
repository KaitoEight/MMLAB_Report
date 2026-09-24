"""School report projection: publication, doctoral study and research projects only.

The discussion draft remains the complete source. This projection never changes
publication status, invents targets or interprets receipt approval as acceptance.
"""
import re
from mmlab_pipeline.members import fold
from monthly_layout import paired_report
from monthly_assembly import TOPICS

LABELS = {'paper': 'KPI bài báo', 'ncs': 'KPI NCS', 'project': 'Đề tài NCKH'}
HEADINGS = {fold(TOPICS[0]): 'paper', fold(TOPICS[1]): 'project',
            fold(TOPICS[2]): 'education',
            **{fold(t): 'other' for t in TOPICS[3:]},
            'kpi bai bao': 'paper', 'bai bao': 'paper', 'paper': 'paper',
            'kpi ncs': 'ncs', 'ncs': 'ncs', 'de tai nckh': 'project', 'de tai': 'project'}
NCS = re.compile(r'\b(?:ncs|phd|nghien cuu sinh|tieu luan tong quan|tltq|chuyen de [123]|cd [123])\b')
PROJECT = re.compile(r'\bde tai\b|\bnafosted\b')
PAPER = re.compile(r'\b(?:paper|bai bao|journal|tap chi|scopus|isi|camera.ready|rebuttal|resubmit)\b|\b(?:nop|submit)\s+(?:\d+\s+)?bai\b')
OTHER = re.compile(r'\b(?:giang day|huong dan sinh vien|khoa luan|luan van thac si|best paper award|giai thuong|dat giai|tham du hoi nghi)\b')


def category(text, heading=None):
    value = fold(text)
    # Such tasks stay in discussion; no lab member was resolved from their source.
    if re.search(r'\(nguon: [^\n]+\)\s*$', value):
        return None
    # Explicit report kinds outrank keywords inside a title.
    if re.match(r'^(?:seminar|giai thuong)\s*:', value):
        return None
    for prefix, kind in [('paper', 'paper'), ('ncs', 'ncs'), ('de tai', 'project'),
                         ('kpi bai bao', 'paper'), ('kpi ncs', 'ncs'), ('de tai nckh', 'project')]:
        if re.match(r'^' + prefix + r'\s*:', value):
            return kind
    if heading=='paper' and re.search(r'.+ — .*; .*; .* \([^\n]*\)$',text):
        return 'paper'
    if OTHER.search(value):
        return None
    # Doctoral seminars are a doctoral milestone, not a general lab seminar.
    if NCS.search(value):
        return 'ncs'
    if PROJECT.search(value):
        return 'project'
    if re.search(r'\bseminar\b', value):
        return None
    if heading in ('paper','project','ncs'):
        return heading
    if PAPER.search(value):
        return 'paper'
    return None


def filtered_body(body):
    """Use headings as context, then emit only permitted content as short bullets."""
    grouped = {key: [] for key in LABELS}
    seen = set()
    heading = None
    for raw in body.splitlines():
        text = re.sub(r'^\s*[-*•+]\s*', '', raw).strip()
        if not text:
            continue
        normalized = fold(text.rstrip(':').strip())
        if normalized in HEADINGS:
            heading = HEADINGS[normalized]
            continue
        if text.endswith(':'):
            heading = None
            continue
        kind = category(text, heading)
        if not kind:
            continue
        # Existing KPI declarations are kept verbatim, including supplied numbers.
        text = re.sub(r'^(?:KPI bài báo|KPI NCS|Đề tài NCKH|Paper|NCS|Đề tài)\s*:\s*', '', text, flags=re.I)
        identity = (kind, text.casefold())
        if identity not in seen:
            seen.add(identity)
            grouped[kind].append(text)
    return '\n'.join(f'{LABELS[kind]}: {text}' for kind in LABELS for text in grouped[kind])


def with_statistics(report):
    from school_statistics import summarize
    result=paired_report(report)
    result.setdefault('scopusTarget',None)
    result.setdefault('paperScope','month')
    result['schoolSummary']=summarize(result)
    return result


def school_projection(report):
    result=paired_report(report)
    if result.get('isTemplate'):return result
    from school_statistics import summarize
    summary=summarize(result)
    for phase in ('a','b'):
        result['sections'][phase+'1']=result['sections'][phase+'2']=summary[phase]
    return result
