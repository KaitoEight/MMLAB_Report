import {useState} from 'react';
import {readApiResponse} from '@/lib/api';
import {Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription} from '@/components/ui/sheet';
import {Button} from '@/components/ui/button';
import {categories, members, type Report, type Category} from '@/lib/research';

type Props={report:Report; onClose:()=>void; onSaved:(report:Report)=>void};
export default function AdminReportEditor({report,onClose,onSaved}:Props){
 const [taskGroup,setTaskGroup]=useState(report.taskGroup||'unassigned');
 const [type,setType]=useState<Category>(report.type);
 const [fields,setFields]=useState({title:report.title,status:report.status,authors:report.authors,venue:report.venue,role:report.role,ranking:report.ranking,index:report.index||''});
 const [owner,setOwner]=useState(report.memberId?String(report.memberId):'');
 const [ids,setIds]=useState<number[]>(report.memberIds);
 const [doneNull,setDoneNull]=useState(report.monthlyTasks?.done==null),[plannedNull,setPlannedNull]=useState(report.monthlyTasks?.planned==null);
 const [done,setDone]=useState(report.monthlyTasks?.done?.map(t=>(t.date?t.date+', ':'')+t.content).join('\n')||'');
 const [planned,setPlanned]=useState(report.monthlyTasks?.planned?.join('\n')||'');
 const [busy,setBusy]=useState(false),[error,setError]=useState('');
 const work=type==='Paper'||type==='Đề tài';
 function tasks(){return done.split('\n').filter(x=>x.trim()).map(line=>{const match=line.match(/^\s*(\d{1,2}\/\d{1,2}(?:\/\d{4})?|\d{4}-\d{2}-\d{2})\s*,\s*(.*)$/);return match?{date:match[1],content:match[2]}:{date:'',content:line.trim()}})}
 async function save(e:React.FormEvent){e.preventDefault();setBusy(true);setError('');try{
  const response=await fetch('/api/reports/'+report.id,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({revision:report.reportVersion||0,type,taskGroup,...fields,memberId:owner?Number(owner):null,memberIds:ids,monthlyTasks:type==='Báo cáo tháng'?{done:doneNull?null:tasks(),planned:plannedNull?null:planned.split('\n').map(x=>x.trim()).filter(Boolean)}:null})});
  if(response.status===401)window.dispatchEvent(new Event('session-expired'));
  const data=await readApiResponse(response);
  onSaved(data.report);
 }catch(e){setError(e instanceof Error?e.message:'Không lưu được báo cáo.')}finally{setBusy(false)}}
 return <Sheet open onOpenChange={open=>{if(!open&&!busy)onClose()}}><SheetContent className="report-sheet admin-editor"><SheetHeader><SheetTitle>Sửa báo cáo</SheetTitle><SheetDescription>Ngày nhận email: {report.date}. Thay đổi của admin được giữ khi đồng bộ Gmail.</SheetDescription></SheetHeader>
 <form onSubmit={save} className="admin-edit-form">
  <label>Loại báo cáo<select value={type} onChange={e=>setType(e.target.value as Category)}>{categories.map(c=><option key={c}>{c}</option>)}</select></label>
  <label>Nhóm nhiệm vụ<select value={taskGroup} onChange={e=>setTaskGroup(e.target.value as typeof taskGroup)}><option value="unassigned">Chưa phân nhóm</option><option value="strategic">Phục vụ KHCL Trường</option><option value="routine">Thường xuyên và đột xuất</option></select></label>
  <label>Tiêu đề<textarea required maxLength={10000} rows={3} value={fields.title} onChange={e=>setFields({...fields,title:e.target.value})}/></label>
  <label>Người phụ trách<select value={owner} onChange={e=>setOwner(e.target.value)}><option value="">Chưa xác định</option>{members.map(m=><option key={m.id} value={m.id}>{m.name}</option>)}</select></label>
  {work?<>
   {([{key:'authors',label:'Tất cả tác giả',max:30000},{key:'venue',label:'Venue',max:3000},{key:'status',label:'Trạng thái bài / đề tài',max:300},{key:'role',label:'Role',max:300},{key:'index',label:'Index',max:1000},{key:'ranking',label:'Ranking',max:300}] as const).map(f=><label key={f.key}>{f.label}<textarea rows={f.key==='authors'?3:1} maxLength={f.max} value={fields[f.key]} onChange={e=>setFields({...fields,[f.key]:e.target.value})}/></label>)}
   <p className="editor-hint">Thành viên được đối soát lại từ tên tác giả. Người phụ trách phải có trong danh sách tác giả. Có thể lưu báo cáo đang thiếu thông tin; hệ thống sẽ giữ cảnh báo.</p>
  </>:<fieldset><legend>Thành viên được ghi nhận</legend><div className="editor-members">{members.map(m=><label key={m.id}><input type="checkbox" checked={ids.includes(m.id)} onChange={e=>setIds(e.target.checked?[...ids,m.id]:ids.filter(id=>id!==m.id))}/>{m.name}</label>)}</div></fieldset>}
  {type==='Báo cáo tháng'&&<>
   <fieldset><legend>Đã thực hiện</legend><label className="editor-check"><input type="checkbox" checked={doneNull} onChange={e=>setDoneNull(e.target.checked)}/>Không có mục Đã (null)</label><textarea aria-label="Công việc đã thực hiện" rows={5} disabled={doneNull} value={done} onChange={e=>setDone(e.target.value)}/></fieldset>
   <fieldset><legend>Dự kiến</legend><label className="editor-check"><input type="checkbox" checked={plannedNull} onChange={e=>setPlannedNull(e.target.checked)}/>Không có mục Sẽ (null)</label><textarea aria-label="Công việc dự kiến" rows={5} disabled={plannedNull} value={planned} onChange={e=>setPlanned(e.target.value)}/></fieldset>
   <p className="editor-hint">Mỗi dòng một công việc. Không bắt buộc ghi ngày. Tháng thống kê theo ngày nhận email.</p>
  </>}
  {error&&<p role="alert" className="login-error">{error}</p>}
  <div className="editor-actions"><Button type="button" variant="outline" disabled={busy} onClick={onClose}>Hủy</Button><Button disabled={busy}>{busy?'Đang lưu…':'Lưu thay đổi'}</Button></div>
 </form></SheetContent></Sheet>
}
