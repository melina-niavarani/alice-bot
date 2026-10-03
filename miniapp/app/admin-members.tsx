'use client';
import {useEffect,useRef,useState} from 'react';
import {adminRequest,adminRequestHeaders,fa,memberDate} from '@/lib/admin-client';
type Status='active'|'stopped'|'unavailable';
type Member={platform:'telegram'|'bale';id:string;name:string;created:string;status:Status;isOwner:boolean};
type Result={members:Member[];total:number;page:number;pages:number;summary:{platform:string;total:number;active:number}[]};
const labels:Record<Status,string>={active:'دریافت پیام فعال',stopped:'دریافت پیام متوقف شده',unavailable:'ارسال فعلاً ممکن نیست'};
export default function AdminMembers(){
  const [filters,setFiltersValue]=useState({q:'',platform:'all',status:'all',page:1});
  const [search,setSearch]=useState(''),[revision,setRevision]=useState(0);
  const [data,setData]=useState<Result|null>(null),[loading,setLoading]=useState(true),[error,setError]=useState('');
  const [exporting,setExporting]=useState(false),[exportError,setExportError]=useState(''),[download,setDownload]=useState('');
  const downloadRef=useRef('');
  function beginLoad(){setLoading(true);setError('');setData(null);setExportError('');setDownload('');if(downloadRef.current){URL.revokeObjectURL(downloadRef.current);downloadRef.current=''}}
  function setFilters(next:typeof filters){beginLoad();setFiltersValue(next)}
  function reload(){beginLoad();setRevision(x=>x+1)}
  useEffect(()=>()=>{if(downloadRef.current)URL.revokeObjectURL(downloadRef.current)},[]);
  useEffect(()=>{
    const controller=new AbortController();
    adminRequest<Result>('/api/admin/members',filters,controller.signal).then(setData).catch(e=>{
      if(!controller.signal.aborted)setError(e instanceof Error?e.message:'فهرست اعضا دریافت نشد.');
    }).finally(()=>{if(!controller.signal.aborted)setLoading(false)});
    return()=>controller.abort();
  },[filters,revision]);
  async function exportFile(){
    setExporting(true);setExportError('');
    try{
      const response=await fetch('/api/admin/members/export',{method:'POST',headers:adminRequestHeaders(),body:JSON.stringify(filters),cache:'no-store'});
      if(!response.ok){const result=await response.json() as {error?:string};throw new Error(result.error||'فایل آماده نشد.')}
      const blob=await response.blob();
      if(downloadRef.current)URL.revokeObjectURL(downloadRef.current);
      const url=URL.createObjectURL(blob);downloadRef.current=url;setDownload(url);
      const link=document.createElement('a');link.href=url;link.download='alice-members.xlsx';document.body.appendChild(link);link.click();link.remove();
    }catch(e){setExportError(e instanceof Error?e.message:'فایل آماده نشد.')}finally{setExporting(false)}
  }
  return <div className="admin-members">
    <div className="admin-section-heading"><h2>اعضای بات‌ها</h2><button className="admin-refresh" disabled={loading||exporting} onClick={reload}>به‌روزرسانی</button></div>
    {data&&<div className="member-stats">{data.summary.map(s=><div className="member-stat" key={s.platform}><span>{s.platform==='bale'?'بله':'تلگرام'}</span><strong>{fa(s.total)} حساب</strong><small>{fa(s.active)} دریافت‌کنندهٔ فعال</small></div>)}</div>}
    <p className="admin-hint">حساب‌های ثبت‌شده در دو بات جدا شمرده می‌شوند؛ ممکن است یک نفر در هر دو عضو باشد.</p>
    <form className="admin-search" onSubmit={e=>{e.preventDefault();setFilters({...filters,q:search.trim(),page:1})}}><label htmlFor="member-search">جست‌وجوی نام یا شناسهٔ حساب</label><div><input id="member-search" value={search} onChange={e=>setSearch(e.target.value)} maxLength={100} placeholder="نام یا شناسه را بنویس"/><button type="submit" disabled={exporting}>جست‌وجو</button></div></form>
    <div className="member-filters"><label>پیام‌رسان<select value={filters.platform} disabled={exporting} onChange={e=>setFilters({...filters,platform:e.target.value,page:1})}><option value="all">هر دو پیام‌رسان</option><option value="telegram">تلگرام</option><option value="bale">بله</option></select></label><label>دریافت پیام<select value={filters.status} disabled={exporting} onChange={e=>setFilters({...filters,status:e.target.value,page:1})}><option value="all">همهٔ وضعیت‌ها</option><option value="active">فعال</option><option value="stopped">متوقف به درخواست عضو</option><option value="unavailable">ارسال فعلاً ممکن نیست</option></select></label></div>
    {loading&&<p className="admin-hint" role="status">در حال دریافت اعضا…</p>}
    {error&&<p className="error-note" role="alert">{error} <button onClick={reload}>تلاش دوباره</button></p>}
    {data&&<><div className="admin-list-heading"><span>{fa(data.total)} حساب در این فهرست</span><button disabled={loading||exporting||!data.total} onClick={()=>void exportFile()}>{exporting?'در حال آماده‌سازی…':'دریافت اکسل'}</button></div><p className="admin-hint">اکسل شامل تمام نتایج جست‌وجو در همهٔ صفحه‌هاست.</p>
      {exportError&&<p className="error-note" role="alert">{exportError}</p>}{download&&<p className="admin-hint" role="status">فایل آماده شد. <a href={download} download="alice-members.xlsx">دریافت فایل اکسل</a></p>}
      {!data.members.length?<div className="empty-note">{filters.q||filters.platform!=='all'||filters.status!=='all'?'عضوی با این جست‌وجو و فیلترها پیدا نشد.':'هنوز حسابی در بات‌ها ثبت نشده است.'}</div>:<ul className="member-list">{data.members.map(m=><li className="member-card" key={`${m.platform}:${m.id}`}><div className="member-card-heading"><strong>{m.name}</strong><span className="platform-tag">{m.platform==='bale'?'بله':'تلگرام'}{m.isOwner?' · مدیر':''}</span></div><div className="member-id">شناسهٔ حساب: <bdi>{m.id}</bdi></div><div className="member-card-footer"><span className={`member-status ${m.status}`}>{labels[m.status]}</span><time>ثبت: {memberDate(m.created)}</time></div></li>)}</ul>}
      {data.pages>1&&<div className="admin-pagination"><button disabled={data.page<=1||exporting} onClick={()=>setFilters({...filters,page:data.page-1})}>قبلی</button><span>صفحهٔ {fa(data.page)} از {fa(data.pages)}</span><button disabled={data.page>=data.pages||exporting} onClick={()=>setFilters({...filters,page:data.page+1})}>بعدی</button></div>}
    </>}
    <p className="admin-hint">این فهرست، اعضای بات‌هاست و از شماره‌های اکسل مشتریان جداست. شمارهٔ تماس با شروع بات خودکار دریافت نمی‌شود.</p>
  </div>;
}
