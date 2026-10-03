import {messenger,miniApp} from './messenger';
export function adminRequestHeaders(){return {'Content-Type':'application/json','x-messenger':messenger(),'x-telegram-init-data':miniApp()?.initData||''}}
export async function adminRequest<T>(path:string,data?:unknown,signal?:AbortSignal):Promise<T>{
  const response=await fetch(path,{method:'POST',headers:adminRequestHeaders(),body:JSON.stringify(data||{}),signal,cache:'no-store'});
  const result=await response.json() as {error?:string};
  if(!response.ok)throw new Error(result.error||'ارتباط برقرار نشد؛ دوباره تلاش کن.');
  return result as T;
}
export const fa=(n:number)=>n.toLocaleString('fa-IR');
export function memberDate(value:string){
  const d=new Date(value.endsWith('Z')?value:value.replace(' ','T')+'Z');
  return Number.isFinite(d.getTime())?new Intl.DateTimeFormat('fa-IR',{timeZone:'Asia/Tehran',dateStyle:'medium'}).format(d):'ثبت نشده';
}
