import {env} from 'cloudflare:workers';
import {contentSchema} from '@/lib/content';
import {readContent,writeContent} from '@/lib/content-store';
export const dynamic='force-dynamic';
const headers={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'};
export async function GET(){try{return Response.json(await readContent(),{headers})}catch{return Response.json({error:'اطلاعات موقتاً در دسترس نیست.'},{status:503,headers})}}
async function authenticated(request:Request){
 const key=(env as unknown as Record<string,string>).ALICE_CONTENT_KEY;
 if(!key)return false;
 const expected=new TextEncoder().encode('Bearer '+key),received=new TextEncoder().encode(request.headers.get('authorization')||'');
 const a=new Uint8Array(await crypto.subtle.digest('SHA-256',expected)),b=new Uint8Array(await crypto.subtle.digest('SHA-256',received));
 let diff=0;for(let i=0;i<a.length;i++)diff|=a[i]^b[i];return diff===0;
}
export async function PUT(request:Request){
 if(!await authenticated(request))return Response.json({error:'Unauthorized'},{status:401,headers});
 if(Number(request.headers.get('content-length')||0)>200000)return Response.json({error:'Too large'},{status:413,headers});
 let content;
 try{const raw=await request.text();if(raw.length>100000)throw Error();content=contentSchema.parse(JSON.parse(raw))}catch{return Response.json({error:'اطلاعات معتبر نیست.'},{status:400,headers})}
 try{const updatedAt=await writeContent(content);return Response.json({ok:true,updatedAt},{headers})}catch{return Response.json({error:'ذخیره اطلاعات انجام نشد.'},{status:503,headers})}
}
