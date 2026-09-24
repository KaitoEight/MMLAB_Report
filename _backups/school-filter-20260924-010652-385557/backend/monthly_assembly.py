"""Readable monthly task assembly without inferred institutional classification."""
import re
from datetime import datetime, timezone, timedelta
from mmlab_pipeline.members import DIRECTORY, fold
from mmlab_pipeline.tasks import repair_tasks, format_task

TOPICS=('Công bố khoa học','Đề tài nghiên cứu','Đào tạo và nghiên cứu sinh',
        'Seminar và hội nghị','Giải thưởng','Hướng dẫn sinh viên và giảng dạy','Hoạt động nghiên cứu khác')


def topic(text, kind=None):
    value=fold(text)
    if kind=='Giải thưởng' or re.search(r'\b(?:giai [123]|giai thuong|best paper award)\b',value):return TOPICS[4]
    if not kind and re.search(r'huong dan sinh vien|giang day|khoa luan',value):return TOPICS[5]
    if kind=='Seminar' or re.search(r'\bseminar\b|tham du hoi nghi|bao cao (?:o|tai) ',value):return TOPICS[3]
    if kind=='Paper' or re.search(r'\b(?:paper|bai bao|journal|revision|review|rebuttal|resubmit|camera.ready)\b|\b(?:submit|nop)\s+(?:\d+\s+)?bai\b',value):return TOPICS[0]
    if kind=='NCS' or re.search(r'\b(?:ncs|phd|nghien cuu sinh|luan van|tieu luan tong quan)\b',value):return TOPICS[2]
    if kind=='Đề tài' or re.search(r'\bde tai\b',value):return TOPICS[1]
    if re.search(r'huong dan sinh vien|giang day|khoa luan',value):return TOPICS[5]
    return TOPICS[6]


def incomplete(text):
    return text.count('"')%2==1 or text.count('“')!=text.count('”')


def assemble(records, period, section_keys, strategy, work_key):
    records=[r for r in records if not r.get('deletedAt') and r.get('date','').startswith(period)]
    entries={key:[] for key in section_keys};review=[];seen=set();seen_tasks=set()
    counts={'acceptedConference':0,'acceptedJournal':0,'submittedConference':0,'submittedJournal':0,'unknownPaperStatus':0}
    for r in sorted(records,key=lambda x:(x['date'],x['id'])):
        group='1'
        member_ids=set(r.get('memberIds',[]))
        names=', '.join(m['name'] for m in DIRECTORY if m['id'] in member_ids)
        if r['type']=='Báo cáo tháng':
            tasks=r.get('monthlyTasks') or {}
            for phase,field in [('a','done'),('b','planned')]:
                for task in repair_tasks(tasks.get(field),join_wrapped=r.get('monthlyTasksVersion')!=2):
                    text=format_task(task)
                    if not names or incomplete(text):
                        reason='Chưa đối chiếu được người gửi với danh sách lab' if not names else 'Nội dung có dấu hiệu bị cắt, cần đọc lại email gốc'
                        review.append(f"{reason}. Nguồn: {r.get('sender') or names or r['id']}. Nội dung: {text}")
                        continue
                    ident=(phase,tuple(sorted(member_ids)),task['date'],task['content'].casefold().rstrip(' .;'))
                    if ident in seen_tasks:continue
                    seen_tasks.add(ident)
                    entries[phase+group].append((topic(task['content']),f'{text} ({names})'))
            continue
        key=work_key(r)
        if key in seen:continue
        seen.add(key)
        if r['type']=='Paper':
            copies=[x for x in records if work_key(x)==key]
            member_ids={mid for x in copies for mid in x.get('memberIds',[])}
            names=', '.join(m['name'] for m in DIRECTORY if m['id'] in member_ids)
            accepted=any(fold(x.get('status','')) in ('accepted','accept','duoc chap nhan','da chap nhan') for x in copies)
            submitted=any(fold(x.get('status','')) in ('submitted','da nop') for x in copies)
            rank=r.get('ranking','')
            kind='Journal' if rank in ('Q1','Q2','Q3','Q4','Q-Unranked') else 'Conference' if rank in ('A*','A','B','C','C-Unranked') else ''
            bucket='accepted'+kind if accepted and kind else 'submitted'+kind if submitted and kind else None
            if bucket and member_ids:
                counts[bucket]+=1
            elif not accepted and not submitted:counts['unknownPaperStatus']+=1
            text=f"{r['title']} — {r.get('venue') or 'chưa có venue'}; {rank or 'chưa có ranking'}; {r.get('index') or 'chưa có index'}"
        else:text=f"{r['type']}: {r['title']}"
        if names:entries['a'+group].append((topic(text,r['type']),f'{text} ({names})'))
        else:review.append('Chưa đối chiếu được thành viên lab: '+text)
    sections={}
    for key,items in entries.items():
        lines=[]
        for heading in TOPICS:
            content=list(dict.fromkeys(text for category,text in items if category==heading))
            if content:lines+=[heading+':']+content
        sections[key]='\n'.join(lines)
    y,m=map(int,period.split('-'));plan=f'{y+int(m==12):04d}-{1 if m==12 else m+1:02d}'
    return {'period':period,'planPeriod':plan,'strategyLabel':strategy,
            'signatory':'NGUYỄN VINH TIỆP','sections':sections,'reviewNotes':list(dict.fromkeys(review)),'assemblyVersion':2,
            'counts':counts,'records':len(records),'works':len(seen),
            'generatedAt':datetime.now(timezone(timedelta(hours=7))).isoformat()}
