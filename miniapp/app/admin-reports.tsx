'use client';
import {useCallback,useEffect,useState} from 'react';
import {adminRequest,fa} from '@/lib/admin-client';
type Counts={total:number;sent:number;failed:number;pending:number;unknown:number};
type Report={id:number;preview:string;media:string;timeLabel:string;status:string;total:Counts;platforms:(Counts&{platform:string;members:Counts;groups:Counts;channels:Counts})[];errors:{platform:string;destination:number;title:string;reason:string;n:number}[]};
const platform=(p:string)=>p==='bale'?'بله':'تلگرام';
function breakdown(c:Counts){return [`${fa(c.sent)} موفق`,...(c.failed?[`${fa(c.failed)} ناموفق`]:[]),...(c.pending?[`${fa(c.pending)} در انتظار`]:[]),...(c.unknown?[`${fa(c.unknown)} نامشخص`]:[])].join('، ')}
export default function AdminReports(){
  const [reports,setReports]=useState<Report[]>([]),[loading,setLoading]=useState(true),[error,setError]=useState('');
  const refresh=useCallback(async(signal?:AbortSignal)=>{try{const result=await adminRequest<{reports:Report[]}>('/api/admin/reports',{},signal);setReports(result.reports);setError('')}catch(e){if(!signal?.aborted){setReports([]);setError(e instanceof Error?e.message:'گزارش‌ها دریافت نشد.')}}finally{if(!signal?.aborted)setLoading(false)}},[]);
  useEffect(()=>{const controller=new AbortController();const timer=setTimeout(()=>void refresh(controller.signal),0);return()=>{clearTimeout(timer);controller.abort()}},[refresh]);
  const pending=reports.some(r=>r.total.pending>0);
  useEffect(()=>{if(!pending)return;const controller=new AbortController();const timer=setInterval(()=>{if(!document.hidden)void refresh(controller.signal)},15000);return()=>{clearInterval(timer);controller.abort()}},[pending,refresh]);
  return <div className="admin-reports"><div className="admin-section-heading"><h2>گزارش ارسال</h2><button className="admin-refresh" disabled={loading} onClick={()=>{setLoading(true);setError('');void refresh()}}>به‌روزرسانی</button></div><p className="admin-hint">۱۰ ارسال آخر، از تازه به قدیم. موفق یعنی پیام‌رسان ارسال را پذیرفته است؛ خوانده‌شدن پیام را نشان نمی‌دهد.</p>
    {loading&&<p className="admin-hint" role="status">در حال دریافت گزارش…</p>}{error&&<p className="error-note" role="alert">{error}</p>}{!loading&&!error&&!reports.length&&<p className="empty-note">هنوز ارسال همگانی ثبت نشده است.</p>}
    {reports.map((r,index)=><details className="report-card" key={r.id} open={index===0}><summary><span className="report-title">پیام شمارهٔ {fa(r.id)}<span className={`report-state ${r.status}`}>{r.status==='sending'?'در حال ارسال':r.status==='complete'?'ارسال کامل شد':r.status==='empty'?'بدون مقصد':'پایان ارسال؛ نیازمند بررسی'}</span></span><time>{r.timeLabel} · تهران</time><p>{r.media}: {r.preview||'بدون کپشن'}</p></summary><div className="report-body"><p className="report-total">{fa(r.total.sent)} ارسال موفق از {fa(r.total.total)} مقصد</p><dl className="report-counts">{([['sent','موفق'],['failed','ناموفق'],['pending','در انتظار / در حال ارسال'],['unknown','نتیجه نامشخص']] as const).map(([key,label])=><div key={key}><dt>{label}</dt><dd>{fa(r.total[key])}</dd></div>)}</dl>
      {r.platforms.map(p=><section className="report-platform" key={p.platform}><h3>{platform(p.platform)}</h3>{!p.total?<p>مقصدی در این پیام‌رسان انتخاب نشده بود.</p>:(['members','groups','channels'] as const).filter(k=>p[k].total>0).map(k=><p key={k}><strong>{k==='members'?'اعضای بات':k==='groups'?'گروه‌ها':'کانال‌ها'} ({fa(p[k].total)})</strong><span>{breakdown(p[k])}</span></p>)}</section>)}
      {r.errors.length>0&&<div className="report-errors"><h3>موارد نیازمند بررسی</h3><ul>{r.errors.map((e,i)=><li key={i}><strong>{platform(e.platform)} · {e.destination?e.title:'اعضای بات'} ({fa(e.n)})</strong><p>{e.reason}</p></li>)}</ul></div>}
      {r.total.unknown>0&&<p className="admin-hint">نتیجهٔ نامشخص یعنی تأیید قطعی از پیام‌رسان نرسیده؛ برای جلوگیری از پیام تکراری، خودکار دوباره ارسال نشده است.</p>}<p className="admin-hint">هر گروه یا کانال یک مقصد شمرده می‌شود، نه تعداد افراد داخل آن.</p></div></details>)}
  </div>;
}
