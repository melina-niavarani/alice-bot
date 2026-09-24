import {env} from 'cloudflare:workers';
import {validateTelegram} from './telegram-auth';
export const adminHeaders={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'};
export async function adminUser(request:Request){
 const e=env as unknown as Record<string,string>;
 const origin=request.headers.get('origin');
 if(origin&&origin!==new URL(request.url).origin)return null;
 const platform=request.headers.get('x-messenger')||'telegram';
 if(platform!=='telegram'&&platform!=='bale')return null;
 const secret=platform==='bale'?e.BALE_WEBAPP_SECRET:e.TELEGRAM_WEBAPP_SECRET;
 const owner=platform==='bale'?e.ALICE_BALE_OWNER_ID:e.ALICE_OWNER_ID;
 return validateTelegram(request.headers.get('x-telegram-init-data')||'',secret||'',owner||'');
}
