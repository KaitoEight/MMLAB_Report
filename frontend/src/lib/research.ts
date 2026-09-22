export type Member = { id: number; name: string; alias: string[]; email: string; initials: string };
export const members: Member[] = [
  {id:1,name:'Nguyễn Vinh Tiệp',alias:['Vinh-Tiep Nguyen'],email:'tiepnv@uit.edu.vn',initials:'VT'},
  {id:2,name:'Đặng Văn Thìn',alias:['Thin Dang','Dang Van Thin','Dang Thin'],email:'thindv@uit.edu.vn',initials:'VT'},
  {id:3,name:'Nguyễn Đức Vũ',alias:['Duc-Vu Nguyen'],email:'vund@uit.edu.vn',initials:'DV'},
  {id:4,name:'Nguyễn Ngọc Thừa',alias:['Ngoc-Thua Nguyen','Thua Nguyen'],email:'thuann@uit.edu.vn',initials:'NT'},
  {id:5,name:'Lưu Đức Tuấn',alias:['Duc-Tuan Luu'],email:'tuanld@uit.edu.vn',initials:'DT'},
  {id:6,name:'Nguyễn Thành Danh',alias:['Thanh-Danh Nguyen'],email:'danhnt@uit.edu.vn',initials:'TD'},
  {id:7,name:'Chế Quang Huy',alias:['Quang-Huy Che','Huy Che'],email:'huycq@uit.edu.vn',initials:'QH'},
  {id:8,name:'Trương Quốc Trường',alias:['Quoc-Truong Truong'],email:'truongtq@uit.edu.vn',initials:'QT'},
  {id:9,name:'Trần Gia Nghĩa',alias:['Gia-Nghia Tran'],email:'nghiatg@uit.edu.vn',initials:'GN'},
  {id:10,name:'Đàm Vũ Trọng Tài',alias:['Trong-Tai Dam Vu'],email:'taidvt@uit.edu.vn',initials:'TT'},
  {id:11,name:'Phạm Thị Bích Nga',alias:['Bich-Nga Pham'],email:'ngaptb@uit.edu.vn',initials:'BN'},
  {id:12,name:'Nguyễn Duy Tâm Anh',alias:['Tam-Anh Nguyen Duy'],email:'anhntd@uit.edu.vn',initials:'TA'},
];
export const categories = ['Paper','Đề tài','NCS','Seminar','Giải thưởng','Báo cáo tháng'] as const;
export type Category = typeof categories[number];
export type Report = {
  taskGroup?:'strategic'|'routine'|'unassigned'; reportVersion?:number; adminEditedAt?:string; adminEditedBy?:string;
  approvalStatus?:'approved'; approvalSource?:'automatic'; approvedAt?:string; confirmationSource?:'admin'|'sender'; confirmedBy?:string; confirmedAt?:string; receiptIssue?: string; confirmationStatus?:'pending'|'confirmed'; id:string; date:string; memberId:number|null; type:Category; title:string; status:string; role:string; authors:string; venue:string; ranking:string; index:string|null; memberIds:number[]; source:'sample'|'gmail'; forwarded:boolean|null; gmailId?:string; issues:string[]; sourceId?:string; messageId?:string; isValid?:boolean; missingFields?:string[]; warnings?:string[]; reportPeriod?:string|null; monthlyTasks?:{done:{date:string;content:string}[]|null;planned:string[]|null}|null };
export const normalize = (v:string) => v.normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/[đĐ]/g,'d').toLowerCase().replace(/[-‐‑–—\s]+/g,' ').trim();
export function resolveMembers(text:string):number[] {
 const t=normalize(text);
 return members.filter(m=>[m.name,...m.alias].some(a=>new RegExp('(^|[^a-z0-9])'+normalize(a).replace(/[.*+?^${}()|[\]\\]/g,'\\$&')+'(?=$|[^a-z0-9])').test(t))).map(m=>m.id);
}
const fmri='Efficient fMRI and Textual Alignment for Image Reconstruction from Human Brain Activity';
const fmriAuthors='Bich-Nga Pham, Trong-Tai Dam Vu, Anh-Khoa Nguyen Vu, Vinh-Tiep Nguyen';
const seed = [
 ['2026-07-07',3,'Efficient Frame Retrieval for Traffic Law Question Answering over Dashcam Videos','Co-author','Van-Hoang Le, Duc-Vu Nguyen, Kiet Van Nguyen, Dien Dinh, Ngan Luu-Thuy Nguyen','MAPR2026'],
 ['2026-07-07',3,'Alignment of Superseded and Replacement Vietnamese Legal Documents: Task, Baseline Models and Challenges','Co-author','Nhi Huynh-Thu Ho, Nhat Dinh Vu, Duc-Vu Nguyen, Kiet Van Nguyen, Ngan Luu-Thuy Nguyen','MAPR2026'],
 ['2026-07-26',11,fmri,'First author',fmriAuthors,'MAPR 2026'],
 ['2026-07-07',10,fmri,'Co-author',fmriAuthors,'MAPR2026'],
 ['2026-07-07',1,fmri,'Co-author',fmriAuthors,'MAPR2026'],
 ['2026-07-26',11,'Lightweight Stable Diffusion via StableKOT: Knowledge Distillation Meets Optimal Transport','First author','Bich-Nga Pham, Quoc-Truong Truong, Anh-Khoa Nguyen Vu, Vinh-Tiep Nguyen','MAPR 2026'],
] as const;
export const sampleReports:Report[] = seed.map((r,i)=>({id:`sample-${i+1}`,date:r[0],memberId:r[1],type:'Paper',title:r[2],status:'Accepted',role:r[3],authors:r[4],venue:r[5],ranking:'C-Unranked',index:null,memberIds:resolveMembers(r[4]),source:'sample',forwarded:null,issues:['Bảng mẫu chưa có trường Index.']}));
export function workKey(r:Report) {return [r.type,normalize(r.title),normalize(r.venue).replace(/\s/g,''),r.type==='Báo cáo tháng'?(r.memberId??r.id):''].join('|')}
export function uniqueWorks(reports:Report[]) {return [...new Map([...reports].sort((a,b)=>b.date.localeCompare(a.date)).map(r=>[workKey(r),r])).values()];}
export type Period = 'month'|'quarter'|'year'|'all';
export function inPeriod(date:string,period:Period,year:number,month:number,quarter:number) {
 const [y,m] = date.split('-').map(Number);
 return period==='all'||(y===year&&(period==='year'||(period==='month'?m===month:Math.ceil(m/3)===quarter)));
}
export function participation(reports:Report[]) {
 const works=uniqueWorks(reports);
 return members.map(m=>({...m,count:works.filter(r=>r.memberIds.includes(m.id)).length,reported:reports.filter(r=>r.memberId===m.id).length})).sort((a,b)=>b.count-a.count||a.id-b.id);
}
export function trend(reports:Report[],period:Period,year:number,month:number,quarter:number) {
 const keys=period==='month'?Array.from({length:new Date(year,month,0).getDate()},(_,i)=>String(i+1).padStart(2,'0')):period==='quarter'?Array.from({length:3},(_,i)=>String((quarter-1)*3+i+1).padStart(2,'0')):period==='year'?Array.from({length:12},(_,i)=>String(i+1).padStart(2,'0')):[...new Set(reports.map(r=>r.date.slice(0,4)))].sort();
 const works=uniqueWorks(reports);
 return keys.map(key=>{const match=(r:Report)=>period==='month'?r.date.slice(8,10)===key:period==='all'?r.date.slice(0,4)===key:r.date.slice(5,7)===key;return {label:period==='year'||period==='quarter'?`T${Number(key)}`:key,reports:reports.filter(match).length,works:works.filter(match).length}});
}
