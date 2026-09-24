import {useEffect,useRef,useState} from 'react';
import {Button} from '@/components/ui/button';
import {readApiResponse} from '@/lib/api';
import type {Report} from '@/lib/research';
type Email={recipient:string;subject:string;body:string;link:string;mailStatus:string;expired:boolean};
type Info={report:Report;mailMode:string;email:Email|null};
export default function PaperActions({report,onChanged}:{report:Report;onChanged:(r:Report)=>void}){
 const changing=useRef(false);
 const [info,setInfo]=useState<Info|null>(null),[busy,setBusy]=useState(''),[error,setError]=useState(''),[notice,setNotice]=useState('');
 useEffect(()=>{let active=true,pending=false;setInfo(null);
  async function refresh(){if(pending||changing.current)return;pending=true;try{const d:Info=await fetch('/api/reports/'+report.id+'/confirmation').then(readApiResponse);if(active&&!changing.current)setInfo(old=>!old||(d.report.reportVersion||0)>=(old.report.reportVersion||0)?d:old)}catch(e){if(active)setError(e instanceof Error?e.message:'Không tải được thông tin xác nhận.')}finally{pending=false}}
  void refresh();const timer=window.setInterval(refresh,10000);return()=>{active=false;window.clearInterval(timer)}
 },[report.id]);
 const current=info?.report||report,email=info?.email;
 const confirmed=current.confirmationStatus==='confirmed';
 const queued=!!email&&!email.expired&&['pending','retry'].includes(email.mailStatus);
 const resend=!!email&&(!queued||email.expired);
 async function send(){
  if(resend&&!window.confirm('Gửi lại email xác nhận cho '+email?.recipient+'? Link cũ sẽ hết hiệu lực. Nếu lần gửi trước chưa rõ kết quả, kiểm tra thư đã gửi trước khi tiếp tục.'))return;
  changing.current=true;setBusy('mail');setError('');setNotice('');
  try{const d:Info=await fetch('/api/reports/'+current.id+'/request-confirmation',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({revision:current.reportVersion||0,resend})}).then(readApiResponse);setInfo(d);onChanged(d.report);setNotice(d.mailMode==='smtp'?'Đã tạo email và đưa vào hàng đợi gửi.':'Đã tạo email và link. Để gửi thật, đặt MAIL_MODE=smtp trong .env rồi khởi động lại app.')}catch(e){setError(e instanceof Error?e.message:'Không tạo được email.')}finally{changing.current=false;setBusy('')}
 }
 async function approve(){
  if(!window.confirm('Xác nhận bạn đã kiểm tra toàn bộ thông tin Paper này? Hệ thống sẽ ghi nhận người xác nhận là admin và hủy email yêu cầu xác nhận còn đang chờ.'))return;
  changing.current=true;setBusy('admin');setError('');setNotice('');
  try{const d=await fetch('/api/reports/'+current.id+'/admin-confirm',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({revision:current.reportVersion||0,confirmed:true})}).then(readApiResponse);onChanged(d.report);setInfo(old=>old?{...old,report:d.report,email:old.email?{...old.email,mailStatus:queued?'cancelled':old.email.mailStatus}:null}:old);setNotice('Admin đã xác nhận thông tin Paper.')}catch(e){setError(e instanceof Error?e.message:'Không xác nhận được.')}finally{changing.current=false;setBusy('')}
 }
 return <section className="paper-actions" aria-label="Xác nhận Paper"><h3>Xác nhận thông tin Paper</h3>
 <p>{confirmed?`Đã xác nhận bởi ${current.confirmationSource==='admin'?'admin '+(current.confirmedBy||''): 'người gửi'+(current.confirmedBy?' '+current.confirmedBy:'')}${current.confirmedAt?' · '+new Date(current.confirmedAt).toLocaleString('vi-VN',{timeZone:'Asia/Ho_Chi_Minh'}):''}`:'Chọn gửi form cho người báo cáo hoặc admin kiểm tra và xác nhận trực tiếp.'}</p>
 <div className="paper-action-buttons"><Button variant="outline" onClick={()=>void send()} disabled={!info||!!busy||confirmed||queued||email?.mailStatus==='sending'}>{busy==='mail'?'Đang tạo…':queued?'Email đang chờ gửi':resend?'Gửi lại email xác nhận':'Gửi email xác nhận'}</Button><Button onClick={()=>void approve()} disabled={!info||!!busy||confirmed}>{busy==='admin'?'Đang xác nhận…':confirmed?'Đã xác nhận':'Admin xác nhận'}</Button></div>
 {queued&&info?.mailMode!=='smtp'&&<p>Chưa bật gửi email thật. Đặt MAIL_MODE=smtp trong .env rồi khởi động lại app.</p>}
 {confirmed&&<p>Muốn thay đổi thông tin, bấm Sửa báo cáo. Sau khi lưu cần xác nhận lại phiên bản mới.</p>}
 {error&&<p className="login-error" role="alert">{error}</p>}{notice&&<p role="status">{notice}</p>}
 {email&&<details><summary>Xem email và link xác nhận</summary><p><strong>Gửi đến:</strong> {email.recipient}</p><p><strong>Tiêu đề:</strong> {email.subject}</p><pre>{email.body}</pre>{email.expired?<p>Link đã hết hạn. Gửi lại email để cấp link mới.</p>:<a href={email.link} target="_blank" rel="noreferrer">Mở trang xác nhận</a>}</details>}
 </section>
}
