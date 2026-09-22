import { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { FlaskConical } from 'lucide-react';
import Dashboard from './Dashboard';
import PaperConfirm from './PaperConfirm';
import './globals.css';

function App() {
  const [user,setUser]=useState<string|null>(null),[loading,setLoading]=useState(true);
  const [username,setUsername]=useState('admin'),[password,setPassword]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState(false);
  useEffect(()=>{fetch('/api/session').then(async r=>{if(r.ok)setUser((await r.json()).username)}).catch(()=>setError('Chưa kết nối được backend.')).finally(()=>setLoading(false));
    const expired=()=>setUser(null);window.addEventListener('session-expired',expired);return ()=>window.removeEventListener('session-expired',expired);
  },[]);
  async function login(e:React.FormEvent){e.preventDefault();setBusy(true);setError('');try{const r=await fetch('/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username,password})});const data=await r.json();if(!r.ok)throw Error(data.error||'Đăng nhập thất bại.');setUser(data.username);setPassword('')}catch(e){setError(e instanceof Error?e.message:'Không kết nối được backend.')}finally{setBusy(false)}}
  async function logout(){const r=await fetch('/api/logout',{method:'POST'});if(r.ok)setUser(null)}
  if(loading)return <div className="login-page">Đang kết nối MMLab…</div>;
  if(user)return <><button className="logout-control" onClick={logout}>Đăng xuất · {user}</button><Dashboard/></>;
  return <main className="login-page"><form className="login-card" onSubmit={login}><div className="brand-mark"><FlaskConical/></div><p className="eyebrow">MMLAB · UIT</p><h1>Đăng nhập admin</h1><p>Quản lý báo cáo hoạt động của phòng thí nghiệm.</p><label>Tên đăng nhập<input autoComplete="username" value={username} onChange={e=>setUsername(e.target.value)} required/></label><label>Mật khẩu<input autoComplete="current-password" type="password" value={password} onChange={e=>setPassword(e.target.value)} required/></label>{error&&<p role="alert" className="login-error">{error}</p>}<button type="submit" disabled={busy}>{busy?'Đang đăng nhập…':'Đăng nhập'}</button></form></main>;
}
function Root(){
 const [hash,setHash]=useState(window.location.hash);
 useEffect(()=>{const change=()=>setHash(window.location.hash);window.addEventListener('hashchange',change);return()=>window.removeEventListener('hashchange',change)},[]);
 const token=new URLSearchParams(hash.slice(1)).get('confirm');
 return token?<PaperConfirm key={token} token={token}/>:<App/>;
}
createRoot(document.getElementById('root')!).render(<Root/>);
