import {useEffect,useState} from 'react';
import {FlaskConical,CheckCircle2,AlertCircle} from 'lucide-react';

type Fields={title:string;authors:string;venue:string;role:string;index:string;ranking:string};
type ErrorField={field:string;reason:string};
type Record={id:string;fields:Fields;errors:ErrorField[];status:string;confirmationSource?:string;revision:number;warnings:string[]};
const labels:{key:keyof Fields;label:string;hint:string}[]=[
 {key:'title',label:'Title of Work',hint:'Tên đầy đủ của bài báo'},
 {key:'authors',label:'All authors',hint:'Tất cả tác giả, gồm cả người ngoài lab'},
 {key:'venue',label:'Venue',hint:'Tên hội nghị hoặc tạp chí'},
 {key:'role',label:'Role',hint:'Vai trò của người báo cáo: First author hoặc Co-author'},
 {key:'index',label:'Index',hint:'Scopus, ISI hoặc Scopus; ISI'},
 {key:'ranking',label:'Ranking',hint:'A*, A, B, C, C-Unranked, Q1–Q4, Q-Unranked'},
];
export default function PaperConfirm({token}:{token:string}){
 const [record,setRecord]=useState<Record|null>(null),[fields,setFields]=useState<Fields>({title:'',authors:'',venue:'',role:'',index:'',ranking:''});
 const [errors,setErrors]=useState<ErrorField[]>([]),[error,setError]=useState(''),[busy,setBusy]=useState(false),[confirmed,setConfirmed]=useState(false),[done,setDone]=useState(false),[warnings,setWarnings]=useState<string[]>([]);
 useEffect(()=>{let active=true;fetch('/api/paper-confirm',{headers:{Authorization:'Bearer '+token}}).then(async r=>{const data=await r.json();if(!r.ok)throw Error(data.error||'Không mở được form.');if(active){setRecord(data);setFields(data.fields);setErrors(data.errors);setDone(data.status==='confirmed')}}).catch(e=>{if(active)setError(e.message)});return()=>{active=false}},[token]);
 async function submit(e:React.FormEvent){e.preventDefault();if(!record)return;setBusy(true);setError('');try{const r=await fetch('/api/paper-confirm',{method:'POST',headers:{'Content-Type':'application/json',Authorization:'Bearer '+token},body:JSON.stringify({fields,revision:record.revision,confirmed})});const data=await r.json();if(!r.ok){if(data.errors){setErrors(data.errors);setError('Vui lòng bổ sung hoặc sửa các trường được đánh dấu.');return}throw Error(data.error||'Chưa gửi được form.')}setDone(true);setRecord(old=>old?{...old,confirmationSource:data.confirmationSource||'sender'}:old);setWarnings(data.warnings||[])}catch(e){setError(e instanceof Error?e.message:'Không kết nối được máy chủ.')}finally{setBusy(false)}}
 return <main className="confirmation-page"><div className="confirmation-card"><div className="confirm-brand"><div className="brand-mark"><FlaskConical/></div><span>MMLAB / UIT</span></div><p className="eyebrow">XÁC NHẬN BÁO CÁO PAPER</p>
  <h1>{done?(record?.confirmationSource==='admin'?'Admin đã xác nhận báo cáo':'Đã ghi nhận xác nhận'):'Kiểm tra thông tin bài báo'}</h1>
  {done?<div className="confirmation-success"><CheckCircle2 size={36}/><p>Thông tin đã được lưu và cập nhật trên dashboard của lab. Anh/chị có thể đóng trang này.</p>{warnings.map((w,i)=><p key={i}>{w}</p>)}</div>:<>
   <p>Trang này không yêu cầu đăng nhập hoặc mã OTP. Hệ thống đã điền những thông tin đọc được từ email. Vui lòng kiểm tra tất cả trường; ô còn thiếu được đánh dấu để bổ sung.</p>
   {record&&<p className="confirmation-meta">Mã tiếp nhận #{record.id} · Type of Report: Paper</p>}
   {error&&<p role="alert" className="login-error"><AlertCircle size={16}/> {error}</p>}
   {!record&&!error&&<p>Đang tải thông tin…</p>}
   {record&&<form onSubmit={submit} noValidate><div className="confirmation-fields">{labels.map(({key,label,hint})=>{const issue=errors.filter(e=>e.field===key);const missing=!fields[key].trim();return <label className={(missing||issue.length)?'incomplete':''} key={key}><span>{label} <b>*</b>{missing&&<small>Cần bổ sung</small>}</span>
    {key==='role'?<select aria-invalid={!!issue.length} value={fields[key]} onChange={e=>setFields({...fields,[key]:e.target.value})}><option value="">Chọn vai trò</option><option value="First author">First author</option><option value="Co-author">Co-author</option>{fields.role&&!['First author','Co-author'].includes(fields.role)&&<option value={fields.role}>{fields.role} — cần kiểm tra</option>}</select>:<textarea rows={key==='title'||key==='authors'?2:1} aria-invalid={!!issue.length} value={fields[key]} placeholder={hint} onChange={e=>setFields({...fields,[key]:e.target.value})}/>}<em>{hint}</em>{issue.map((v,i)=><strong className="field-error" key={i}>{v.reason}</strong>)}</label>})}</div>
    <label className="confirm-checkbox"><input type="checkbox" checked={confirmed} onChange={e=>setConfirmed(e.target.checked)}/><span>Tôi đã kiểm tra và xác nhận thông tin trên là đúng.</span></label>
    <button className="confirm-submit" disabled={!confirmed||busy}>{busy?'Đang lưu…':'Xác nhận & gửi'}</button>
    <p className="confirmation-meta">Xác nhận của người gửi không thay thế việc xác minh Index/Ranking từ nguồn học thuật. Link này chỉ cấp quyền cho báo cáo trên.</p>
   </form>}
  </>}
 </div></main>;
}
