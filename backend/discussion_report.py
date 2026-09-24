"""Group current editable task bodies by explicit member attribution."""
import re
from mmlab_pipeline.members import DIRECTORY, normalized_name
from monthly_assembly import TOPICS
from monthly_layout import paired_report

NAMES = {normalized_name(alias): m['id'] for m in DIRECTORY
         for alias in (m['name'], m['email'], *m['aliases'])}


def by_member(report):
    report = paired_report(report)
    groups = {m['id']: {'id':m['id'], 'name':m['name'], 'done':[], 'planned':[]} for m in DIRECTORY}
    common = {'id':None, 'name':'Nội dung chung / chưa gắn thành viên', 'done':[], 'planned':[]}
    for key, phase in (('a1', 'done'), ('b1', 'planned')):
        for raw in report['sections'].get(key, '').splitlines():
            text = re.sub(r'^\s*[*•+]\s+', '', raw).strip()
            if not text or text.rstrip(':') in TOPICS:
                continue
            suffix = re.search(r'\s+\(([^()]*)\)\s*$', text)
            owners = []
            if suffix:
                parts = re.split(r'[,;]', suffix[1])
                ids = [NAMES.get(normalized_name(part)) for part in parts]
                # Full attribution only: a mention in task prose is not ownership.
                if ids and all(ids):
                    owners = list(dict.fromkeys(ids)); text = text[:suffix.start()].rstrip()
            targets = [groups[mid] for mid in owners] if owners else [common]
            for group in targets:
                if text not in group[phase]:group[phase].append(text)
    return [*groups.values(), *([common] if common['done'] or common['planned'] else [])]
