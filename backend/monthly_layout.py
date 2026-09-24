"""Two editable bodies; repeat them in the school's four required slots."""
import re
from monthly_assembly import TOPICS

LAYOUT = 'paired-ab/1'
LEGACY_PREFIX = re.compile(
    r'^(?:Được chấp nhận|Đã nộp|Bài báo chưa rõ trạng thái|'
    r'Ghi nhận bài báo, chưa có trạng thái xác định|Accepted|Chưa xác nhận)\s*:\s*', re.I)
LEGACY_TOTAL = re.compile(r'^(?:Được chấp nhận|Đã nộp) \d+ bài báo (?:hội nghị|tạp chí)\.$')


def merge_legacy(blocks):
    """Keep unique legacy content, grouping repeated headings only once."""
    groups = {'': []}
    seen = set()
    for block in blocks:
        group = ''
        for raw in block.splitlines():
            line = raw.strip()
            if not line or LEGACY_TOTAL.fullmatch(line):
                continue
            line = LEGACY_PREFIX.sub('', line)
            if line.rstrip(':') in TOPICS:
                group = line.rstrip(':')
                groups.setdefault(group, [])
                continue
            if line not in seen:
                seen.add(line)
                groups.setdefault(group, []).append(line)
    result = []
    for group, lines in groups.items():
        if not lines:
            continue
        if group:
            result.append(group + ':')
        result.extend(lines)
    return '\n'.join(result)


def paired_report(report):
    """Non-mutating compatibility layer for saved drafts and old exports."""
    result = {**report, 'sections': dict(report['sections']), 'layoutVersion': LAYOUT}
    sections = result['sections']
    for phase in ('a', 'b'):
        if report.get('layoutVersion') == LAYOUT:
            body = sections.get(phase + '1', '')  # Empty means intentionally cleared.
        else:
            body = merge_legacy([sections.get(phase + suffix, '') for suffix in ('1', '2', 'Other')])
        sections[phase + '1'] = sections[phase + '2'] = body
        sections[phase + 'Other'] = ''
    # Keep legacy recommendations in stored payloads, but don't render a third part.
    sections.setdefault('recommendations', '')
    return result
