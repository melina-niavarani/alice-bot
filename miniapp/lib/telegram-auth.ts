export async function validateTelegram(raw:string, secret:string, owner:string, now=Math.floor(Date.now()/1000)) {
 if(!raw||raw.length>12000||!/^\d+$/.test(owner)||! /^[a-f0-9]{64}$/.test(secret))return null;
 try {
  const params=new URLSearchParams(raw), seen=new Set<string>();
  for(const [k] of params){if(seen.has(k))return null;seen.add(k)}
  const hash=params.get('hash')||'';if(!/^[a-f0-9]{64}$/.test(hash))return null;
  params.delete('hash');
  const date=Number(params.get('auth_date'));if(!Number.isInteger(date)||now-date>3600||date>now+30)return null;
  const data=[...params.entries()].sort(([a],[b])=>a<b?-1:a>b?1:0).map(([k,v])=>`${k}=${v}`).join('\n');
  const bytes=Uint8Array.from(secret.match(/../g)!,s=>parseInt(s,16));
  const key=await crypto.subtle.importKey('raw',bytes,{name:'HMAC',hash:'SHA-256'},false,['verify']);
  if(!await crypto.subtle.verify('HMAC',key,Uint8Array.from(hash.match(/../g)!,s=>parseInt(s,16)),new TextEncoder().encode(data)))return null;
  const user=JSON.parse(params.get('user')||'null');
  if(!user||!Number.isSafeInteger(user.id)||String(user.id)!==owner)return null;
  return {id:user.id,firstName:typeof user.first_name==='string'?user.first_name:'مدیر آلیس',role:'owner' as const};
 } catch{return null}
}
