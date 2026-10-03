'use client';
import {messenger} from '@/lib/messenger';
import {adminRequest} from '@/lib/admin-client';
import {useState} from 'react';
import {Input} from '@/components/ui/input';
import {Textarea} from '@/components/ui/textarea';
import {Button} from '@/components/ui/button';
import AdminMembers from './admin-members';
import AdminReports from './admin-reports';
export default function AdminPanel({onPublished}:{onPublished:()=>void}){
 const [user,setUser]=useState<{firstName:string;id:number}|null>(null),[busy,setBusy]=useState(false),[message,setMessage]=useState(''),[title,setTitle]=useState(''),[body,setBody]=useState(''),[preview,setPreview]=useState(false);
 const [tab,setTab]=useState<'members'|'reports'|'notices'>('members');
 async function login(){setBusy(true);setMessage('');try{const r=await adminRequest<{user:{firstName:string;id:number}}>('/api/admin/session');setUser(r.user);setTab('members')}catch(e){setMessage(e instanceof Error?e.message:'ورود انجام نشد.')}finally{setBusy(false)}}
 async function publish(){setBusy(true);setMessage('');try{await adminRequest('/api/admin/notices',{title,body});setTitle('');setBody('');setPreview(false);setMessage('اطلاعیه در مینی‌اپ منتشر شد.');onPublished()}catch(e){setMessage(e instanceof Error?e.message:'انتشار انجام نشد.')}finally{setBusy(false)}}
 return <section className="admin-panel"><div className="page-title"><h1>مدیریت آلیس</h1><p>{user?'مدیر اصلی · '+user.firstName:'ورود امن با حساب پیام‌رسان'}</p></div>{!user?<div className="white-card"><p>با حساب مدیر، مینی‌اپ را از دکمه «ورود به مجموعه آلیس» در بات باز کن و وارد شو.</p><Button className="primary" disabled={busy} onClick={()=>void login()}>{busy?'در حال بررسی…':'ورود با حساب پیام‌رسان'}</Button><a className="text-link" href={messenger()==='bale'?'https://ble.ir/alicesportclubbot':'https://t.me/AliceSportClubBot'}>رفتن به بات آلیس</a></div>:<>
 <nav className="admin-tabs" aria-label="بخش‌های مدیریت">{([['members','اعضای بات‌ها'],['reports','گزارش ارسال'],['notices','اطلاعیه']] as const).map(([key,label])=><button key={key} aria-current={tab===key?'page':undefined} disabled={busy} onClick={()=>{setTab(key);setMessage('')}}>{label}</button>)}</nav>
 {tab==='members'?<AdminMembers/>:tab==='reports'?<AdminReports/>:<form className="white-card" onSubmit={e=>{e.preventDefault();setPreview(true);setMessage('')}}><h2>اطلاعیه جدید</h2><label htmlFor="notice-title">عنوان</label><Input id="notice-title" required maxLength={120} value={title} disabled={busy} onChange={e=>{setTitle(e.target.value);setPreview(false)}}/><label htmlFor="notice-body">متن اطلاعیه</label><Textarea id="notice-body" required maxLength={1600} rows={6} value={body} disabled={busy} onChange={e=>{setBody(e.target.value);setPreview(false)}}/><p className="eyebrow">مقصد انتشار: اطلاعیه‌های مینی‌اپ آلیس</p><Button type="submit" className="secondary" disabled={busy||!title.trim()||!body.trim()}>پیش‌نمایش اطلاعیه</Button>{preview&&<div className="notice"><h3>{title}</h3><p>{body}</p><Button type="button" className="primary" disabled={busy} onClick={()=>void publish()}>{busy?'در حال انتشار…':'تأیید و انتشار در مینی‌اپ'}</Button></div>}</form>}
 <Button className="secondary" disabled={busy} onClick={()=>{setUser(null);setMessage('');setTitle('');setBody('');setPreview(false)}}>بستن پنل مدیریت</Button></>}{message&&<p role="status" className="error-note">{message}</p>}</section>
}
