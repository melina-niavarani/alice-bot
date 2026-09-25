'use client';
import {messenger,miniApp} from '@/lib/messenger';
import AdminPanel from './admin-panel';
import Image from 'next/image';
import {useCallback,useEffect,useState} from 'react';
import {Dumbbell,Waves,MapPin,ChevronLeft,ArrowRight,Clock3,FileText,Bell,Navigation,Phone,RefreshCw} from 'lucide-react';
import {Table,TableBody,TableCell,TableHead,TableHeader,TableRow} from '@/components/ui/table';
import {initialContent,contentSchema,type Content} from '@/lib/content';
import {formatTariff,tariffs} from '@/lib/tariffs';
type View='admin'|'home'|'gym'|'pool'|'location'|'gym-rules'|'pool-rules';
export default function Home(){
 const [content,setContent]=useState<Content>(initialContent),[view,setView]=useState<View>('home'),[error,setError]=useState(false),[loading,setLoading]=useState(true);
 async function refresh(){setLoading(true);try{const r=await fetch('/api/content',{cache:'no-store'});if(!r.ok)throw Error();const j=await r.json() as {content:unknown};setContent(contentSchema.parse(j.content));setError(false)}catch{setError(true)}finally{setLoading(false)}}
 const go=useCallback((v:View)=>{if(messenger()==='bale'){setView(v);window.scrollTo(0,0)}else location.hash=v},[]);
 useEffect(()=>{const timer=window.setTimeout(()=>void refresh(),0);const onFocus=()=>{void refresh()};window.addEventListener('focus',onFocus);return()=>{window.clearTimeout(timer);window.removeEventListener('focus',onFocus)}},[]);
 useEffect(()=>{const script=document.createElement('script');script.src=messenger()==='bale'?'https://tapi.bale.ai/miniapp.js?3':'https://telegram.org/js/telegram-web-app.js';script.onload=()=>{const app=miniApp();app?.ready();app?.expand();app?.setHeaderColor?.('#1a507f');app?.setBackgroundColor?.('#f4f7fa')};document.head.appendChild(script);return()=>{script.remove()}},[]);
 useEffect(()=>{const read=()=>{const v=location.hash.slice(1);setView(['admin','gym','pool','location','gym-rules','pool-rules'].includes(v)?v as View:'home');window.scrollTo(0,0)};read();window.addEventListener('hashchange',read);return()=>window.removeEventListener('hashchange',read)},[]);
 useEffect(()=>{const app=miniApp();const back=()=>{go((view.endsWith('-rules')?view.replace('-rules',''):'home') as View)};if(view==='home')app?.BackButton?.hide();else app?.BackButton?.show();app?.BackButton?.onClick(back);return()=>app?.BackButton?.offClick(back)},[view,go]);
 const service=view.startsWith('gym')?content.gym:content.pool;
 const serviceTitle=view.startsWith('gym')?'بدنسازی':'استخر و سونا';
 const map='https://www.google.com/maps/search/?api=1&query='+encodeURIComponent(content.name+' '+content.address);
 return <main className="app-shell">
  <header className="brand"><div className="wordmark"><strong>مجموعه ورزشی آلیس</strong><span>ALICE SPORT CLUB</span></div><div className="brand-logo"><Image src="/alice-white-center.png" alt="نشان مجموعه ورزشی آلیس" width={105} height={77} priority /></div></header>
  {view!=='home'&&<button className="back" onClick={()=>go(view.endsWith('-rules')?(view.startsWith('gym')?'gym':'pool'):'home')}><ArrowRight size={19}/>بازگشت</button>}
  {view==='admin'?<AdminPanel onPublished={()=>void refresh()}/>:view==='home'?<>
   <section className="intro"><p className="eyebrow">تهرانپارس · ورزش و تندرستی</p><h1>{content.name}</h1><p>{content.greeting} <span aria-hidden>🌿</span></p></section>
   <div className="section-heading"><h2>خدمات مجموعه</h2><span>همه‌چیز، همین‌جا</span></div>
   <div className="services">
    <button className="service-card gym" onClick={()=>go('gym')}><div className="service-icon"><Dumbbell size={32}/></div><div><h3>بدنسازی</h3><p>برنامه فعالیت و تعرفه‌ها</p></div><ChevronLeft className="chevron" size={21}/></button>
    <button className="service-card pool" onClick={()=>go('pool')}><div className="service-icon"><Waves size={32}/></div><div><h3>استخر و سونا</h3><p>سانس‌ها، تعرفه‌ها و قوانین</p></div><ChevronLeft className="chevron" size={21}/></button>
    <button className="service-card location" onClick={()=>go('location')}><div className="service-icon"><MapPin size={29}/></div><div><h3>آدرس و مسیریابی</h3><p>مسیر رسیدن به آلیس</p></div><ChevronLeft className="chevron" size={21}/></button>
   </div>
   <section className="notices"><div className="section-heading"><h2><Bell size={19}/>اطلاعیه‌ها</h2><button className="icon-button" disabled={loading} onClick={()=>void refresh()} aria-label="به‌روزرسانی اطلاعیه‌ها"><RefreshCw size={17} className={loading?'spin':''}/></button></div>{content.notices.length?content.notices.map((n,i)=><article className="notice" key={i}><h3>{n.title}</h3><p>{n.body}</p></article>):<p className="empty-note">هنوز اطلاعیه‌ای منتشر نشده است.</p>}</section>
  </>:view==='location'?<><section className="page-title"><div className="title-icon"><MapPin/></div><h1>آدرس و مسیریابی</h1><p>{content.name}</p></section><section className="white-card address"><span className="eyebrow">نشانی مجموعه</span><p>{content.address}</p><a className="primary" href={map} target="_blank" rel="noopener noreferrer"><Navigation size={20}/>مسیریابی در نقشه</a>{content.phone&&<a className="secondary" href={'tel:'+content.phone}><Phone size={19}/><bdi>{content.phone}</bdi></a>}</section></>:view.endsWith('-rules')?<><section className="page-title"><div className="title-icon"><FileText/></div><h1>قوانین {serviceTitle}</h1></section><section className="white-card"><p className="multiline">{service.rules||'قوانین این بخش هنوز اعلام نشده است.'}</p></section></>:<>
   <section className="page-title"><div className={'title-icon '+(view==='pool'?'blue':'')}>{view==='gym'?<Dumbbell/>:<Waves/>}</div><h1>{serviceTitle}</h1><p>{service.description}</p></section>
   <section className="white-card tariffs"><h2>تعرفه‌ها</h2>
    {service.singlePrice&&<div className="price-line"><span>{view==='pool'?'ورودی آزاد استخر':'تک‌جلسه'}</span><strong>{service.singlePrice}</strong></div>}
    {service.packagePrice&&<div className="price-line"><span>پکیج / اشتراک</span><strong>{service.packagePrice}</strong></div>}
    {tariffs[view==='gym'?'gym':'pool'].map(section=><div className="tariff-group" key={section.title}><h3>{section.title}</h3>{section.items.map(item=><div className="price-line" key={item.label}><span>{item.label}</span><strong>{formatTariff(item.price)}</strong></div>)}</div>)}
   </section>
   <section className="white-card"><h2><Clock3 size={20}/>{view==='gym'?'برنامه فعالیت':'برنامه سانس‌ها'}</h2>{service.sessions.length?<Table className="schedule"><TableHeader><TableRow><TableHead>روز</TableHead><TableHead>ساعت</TableHead><TableHead>ویژه</TableHead></TableRow></TableHeader><TableBody>{service.sessions.map((s,i)=><TableRow key={i}><TableCell>{s.day}</TableCell><TableCell><bdi>{s.start} – {s.end}</bdi></TableCell><TableCell>{s.audience||'—'}</TableCell></TableRow>)}</TableBody></Table>:<div className="empty-state"><Clock3 size={29}/><p>برنامه هنوز اعلام نشده است.</p><span>سانس‌های جدید در همین بخش قرار می‌گیرند.</span></div>}</section>
   <button className="secondary" onClick={()=>go(view==='gym'?'gym-rules':'pool-rules')}><FileText size={19}/>مشاهده قوانین<ChevronLeft size={18}/></button><button className="text-link" onClick={()=>go('location')}><MapPin size={18}/>مسیریابی مجموعه</button>
  </>}
  {error&&<div role="status" className="error-note">دریافت اطلاعات تازه ممکن نشد. <button onClick={()=>void refresh()}>تلاش دوباره</button></div>}
  <button className="text-link" onClick={()=>go('admin')}>ورود مدیر</button>
  <footer>آلیس <span>·</span> مجموعه ورزشی تهرانپارس</footer>
 </main>
}
