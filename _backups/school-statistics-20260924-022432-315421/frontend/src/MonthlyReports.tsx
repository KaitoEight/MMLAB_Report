import {useEffect,useState} from 'react';
import {readApiResponse} from '@/lib/api';
import {Button} from '@/components/ui/button';
type Draft={period:string;planPeriod:string;revision:number;strategyLabel:string;signatory:string;sections:Record<string,string>;records:number;counts:Record<string,number>;reviewNotes?:string[];assemblyVersion?:number;customized?:boolean};
const labels:Record<string,string>={a1:'Phần A · Toàn bộ công việc đã thực hiện',b1:'Phần B · Toàn bộ kế hoạch công việc'};
export default function MonthlyReports(){
 const [period,setPeriod]=useState(new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Ho_Chi_Minh',year:'numeric',month:'2-digit'}).format(new Date()));
 const [draft,setDraft]=useState<Draft|null>(null),[error,setError]=useState(''),[notice,setNotice]=useState(''),[busy,setBusy]=useState(false),[dirty,setDirty]=useState(false);
 const [next,setNext]=useState('');
 useEffect(()=>{let alive=true;setDraft(null);setError('');setDirty(false);fetch('/api/monthly/'+period).then(readApiResponse).then(d=>{if(alive)setDraft(d)}).catch(e=>{if(alive)setError(e.message)});return()=>{alive=false}},[period]);
 useEffect(()=>{fetch('/api/monthly/schedule').then(readApiResponse).then(d=>setNext(d.enabled?new Date(d.nextRun).toLocaleString('vi-VN',{timeZone:'Asia/Ho_Chi_Minh'}):'Đã tắt')).catch(()=>{});},[]);
 async function save(){if(!draft)return;setBusy(true);setError('');try{const d=await fetch('/api/monthly/'+period,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({revision:draft.revision,strategyLabel:draft.strategyLabel,signatory:draft.signatory,sections:{a1:draft.sections.a1,b1:draft.sections.b1}})}).then(readApiResponse);setDraft(d);setDirty(false);setNotice('Đã lưu hai bản báo cáo.')}catch(e){setError(e instanceof Error?e.message:'Không lưu được.')}finally{setBusy(false)}}
 async function refresh(){if(dirty&&!window.confirm('Bỏ thay đổi chưa lưu và tổng hợp lại từ Gmail?'))return;try{setDraft(await fetch('/api/monthly/'+period+'?fresh=true').then(readApiResponse));setDirty(true);setNotice('Đã tổng hợp lại. Bấm Lưu để dùng bản này khi tải hoặc gửi.')}catch(e){setError(e instanceof Error?e.message:'Không tải được.')}}
 return <section className="monthly-workspace"><div className="monthly-toolbar"><label>Tháng tổng hợp <input aria-label="Tháng tổng hợp" type="month" value={period} onChange={e=>{if(e.target.value&&(!dirty||window.confirm('Bỏ thay đổi chưa lưu và đổi tháng?')))setPeriod(e.target.value)}}/></label><Button variant="outline" onClick={()=>void refresh()}>Tổng hợp lại</Button><Button onClick={()=>void save()} disabled={!draft||busy||!dirty}>{busy?'Đang lưu…':'Lưu báo cáo'}</Button></div>
 <p className="monthly-schedule">Hai bản được gửi đến 12 thành viên lúc 09:00 thứ Hai cuối cùng mỗi tháng. Lịch tiếp theo: {next||'Đang tải…'}.</p>
 {error&&<p className="login-error" role="alert">{error}</p>}{notice&&<p role="status">{notice}</p>}
 {draft&&<>{draft.customized&&(!draft.assemblyVersion||draft.assemblyVersion<2)&&<p className="editor-hint">Đây là bản đã lưu bằng cách tổng hợp cũ. Bấm Tổng hợp lại để nối dòng và gộp mục trùng; kiểm tra nội dung trước khi lưu.</p>}<div className="monthly-downloads"><div><h2>Bản thảo luận · Đã và Sẽ</h2><p>Toàn bộ Đã tháng {period} và Sẽ tháng {draft.planPeriod}, gồm tất cả nhóm công việc.</p><a aria-disabled={dirty} href={dirty?undefined:`/api/monthly/${period}/discussion.docx`}>Tải Word</a></div><div><h2>Bản nộp trường · A và B</h2><p>Chỉ bài báo, NCS và đề tài. Đã → A.1/A.2; Sẽ → B.1/B.2. Mã đơn vị: 6.</p><a aria-disabled={dirty} href={dirty?undefined:`/api/monthly/${period}/school.docx`}>Tải Word</a></div></div>{dirty&&<p className="editor-hint">Lưu thay đổi trước khi tải Word.</p>}
 <p>Nhập đầy đủ Đã và Sẽ ở hai ô dưới. Bản thảo luận giữ toàn bộ nội dung. Bản nộp trường tự lọc bài báo, NCS, đề tài và chép A.1 sang A.2, B.1 sang B.2.</p>
 {Object.entries(labels).map(([key,label])=><label className="monthly-section" key={key}><strong>{label}</strong><textarea rows={Math.min(12,Math.max(3,(draft.sections[key]||'').split('\n').length+1))} value={draft.sections[key]||''} onChange={e=>{setDraft({...draft,sections:{...draft.sections,[key]:e.target.value,[key==='a1'?'a2':'b2']:e.target.value}});setDirty(true)}}/></label>)}
 </>}
 </section>
}
