import {adminUser,adminHeaders as headers} from '@/lib/admin';
import {readContent,writeContent} from '@/lib/content-store';
import {contentSchema} from '@/lib/content';
export const dynamic='force-dynamic';
export async function POST(request:Request){
 if(!await adminUser(request))return Response.json({error:'دسترسی مدیر معتبر نیست؛ مینی‌اپ را دوباره از منوی بات باز کن.'},{status:401,headers});
 try{
  const raw=await request.text();if(raw.length>12000)return Response.json({error:'متن بیش از حد طولانی است.'},{status:413,headers});
  const input=JSON.parse(raw);
  if(typeof input.title!=='string'||typeof input.body!=='string'||!input.title.trim()||!input.body.trim()||input.title.length>120||input.body.length>1600)return Response.json({error:'عنوان و متن معتبر وارد کن.'},{status:400,headers});
  const {content}=await readContent();
  if(content.notices.length>=30)return Response.json({error:'ظرفیت اطلاعیه‌ها پر است؛ از پنل محتوا اطلاعیه‌های قدیمی را حذف کن.'},{status:409,headers});
  const next=contentSchema.parse({...content,notices:[{title:input.title.trim(),body:input.body.trim()},...content.notices]});
  await writeContent(next);return Response.json({ok:true},{headers});
 }catch{return Response.json({error:'انتشار انجام نشد؛ دوباره تلاش کن.'},{status:503,headers})}
}
