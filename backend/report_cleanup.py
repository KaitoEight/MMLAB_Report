"""Normalize stored exports without guessing missing evidence or identities."""
import copy
import re
from pydantic import ValidationError
from mmlab_pipeline.validator import WorkReport, LABELS
from mmlab_pipeline.normalization import normalize_role, normalize_ranking
from mmlab_pipeline.members import fold


def clean_report(record):
    r = copy.deepcopy(record)
    changes = list(r.get('normalizations', []))
    if r['type'] in ('Paper','Đề tài'):
        for field, normalizer in [('role',normalize_role),('ranking',normalize_ranking)]:
            old = r.get(field, '')
            value = normalizer(old) if field=='role' or r['type']=='Paper' else old
            if old != value:
                changes.append({'field':field, 'from':old, 'to':value})
                r[field] = value
        paper_fields = {'report_type':r['type'], **{k:r.get(k) or '' for k in ('title','authors','venue','role','index','ranking')}}
        # The inbox list may use Subject as a display fallback, not extracted evidence.
        if 'Title of Work' in r.get('missingFields',[]):
            paper_fields['title']=''
        old_labels = set(LABELS[k] for k in paper_fields)
        invalid = [e for e in r.get('invalidFields',[]) if
                   (e['field'] not in old_labels or e['reason'].startswith(('Trường xuất hiện nhiều lần','Xung đột')))
                   and not (e['field']=='Subject' and e['reason']=='Extra inputs are not permitted')]
        missing = [f for f in r.get('missingFields',[]) if f not in old_labels]
        try:
            model = WorkReport.model_validate(paper_fields)
            for k in ('title','authors','venue','role','index','ranking'):
                r[k] = getattr(model,k)
        except ValidationError as exc:
            for e in exc.errors(include_url=False,include_context=False):
                k=e['loc'][0]; label=LABELS.get(k,k)
                if not paper_fields.get(k): missing.append(label)
                else: invalid.append({'field':label,'value':paper_fields.get(k),'reason':e['msg']})
        r['invalidFields'],r['missingFields']=invalid,list(dict.fromkeys(missing))
        if r.get('status') in ('', 'Chưa rõ', None):
            subject=fold(r.get('subject',''))
            if not re.search(r'\b(?:not|no|non|reject\w*|withdraw\w*)\b',subject) and re.search(r'\bacceptance notification\b|\bnotification of acceptance\b|\b(?:paper|submission) (?:has been |is )?accepted\b',subject):
                changes.append({'field':'status','from':r.get('status'),'to':'Accepted','evidence':'Subject'})
                r['status']='Accepted'
    elif r['type']=='Báo cáo tháng':
        r['invalidFields']=[e for e in r.get('invalidFields',[]) if e['field'] not in ('Subject','Đã','Sẽ','Ranking','Index','Role','Venue')]
        r['missingFields']=[f for f in r.get('missingFields',[]) if f not in ('Subject','Đã','Sẽ','Ranking','Index','Role','Venue')]
        r['reportPeriod']=r['date'][:7]
    elif r['type'] in ('NCS','Seminar','Giải thưởng'):
        r['invalidFields']=[e for e in r.get('invalidFields',[]) if not (e['field'] in ('All authors','Venue','Role','Index','Ranking') and e['reason']=='Extra inputs are not permitted')]
    old_fields = [e['field']+':' for e in record.get('invalidFields',[])]
    old_missing = ['Thiếu '+f+'.' for f in record.get('missingFields',[])]
    r['issues']=[i for i in r.get('issues',[]) if not any(i.startswith(f) for f in old_fields) and i not in old_missing]
    r['issues'] += ['Thiếu '+f+'.' for f in r.get('missingFields',[])]
    r['issues'] += [e['field']+': '+e['reason'] for e in r.get('invalidFields',[])]
    r['isValid']=not r.get('missingFields') and not r.get('invalidFields')
    r['normalizations']=changes
    return r


def clean_bundle(bundle):
    d=copy.deepcopy(bundle)
    d['reports']=[clean_report(r) for r in d['reports']]
    d['summary']['valid']=sum(r['isValid'] for r in d['reports'])
    d['summary']['invalid']=len(d['reports'])-d['summary']['valid']
    return d
