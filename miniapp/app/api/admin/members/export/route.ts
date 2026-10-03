import {adminUser,adminHeaders as headers} from '@/lib/admin';
import {botDatabase,memberFilters,memberOwners} from '@/lib/admin-data';
import {membersXlsx} from '@/lib/members-xlsx';
import {exportMembers} from '../../../../../../cloudflare-bot/src/members.js';
export const dynamic='force-dynamic';
export async function POST(request:Request){
  if(!await adminUser(request))return Response.json({error:'دریافت فایل فقط با حساب مدیر امکان‌پذیر است.'},{status:401,headers});
  let filters;
  try{filters=await memberFilters(request)}catch{return Response.json({error:'جست‌وجو یا فیلتر معتبر نیست.'},{status:400,headers})}
  try{
    const members=await exportMembers(botDatabase(),filters,memberOwners());
    const bytes=membersXlsx(members);
    return new Response(bytes.buffer as ArrayBuffer,{headers:{...headers,
      'Content-Type':'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      'Content-Disposition':`attachment; filename="alice-members-${new Date().toISOString().slice(0,10)}.xlsx"`,
    }});
  }catch(error){return Response.json({error:error instanceof Error&&error.message==='EXPORT_TOO_LARGE'?'بیش از ۱۰ هزار حساب انتخاب شده است؛ برای خروجی، فیلتر پیام‌رسان یا جست‌وجو را محدودتر کن.':'فایل آماده نشد؛ دوباره تلاش کن.'},{status:503,headers})}
}
