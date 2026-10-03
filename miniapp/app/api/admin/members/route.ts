import {adminUser,adminHeaders as headers} from '@/lib/admin';
import {botDatabase,memberFilters,memberOwners} from '@/lib/admin-data';
import {readMembers} from '../../../../../cloudflare-bot/src/members.js';
export const dynamic='force-dynamic';
export async function POST(request:Request){
  if(!await adminUser(request))return Response.json({error:'برای مشاهدهٔ اعضا، مینی‌اپ را با حساب مدیر از داخل بات باز کن.'},{status:401,headers});
  let filters;
  try{filters=await memberFilters(request)}catch{return Response.json({error:'جست‌وجو یا فیلتر معتبر نیست.'},{status:400,headers})}
  try{return Response.json(await readMembers(botDatabase(),filters,memberOwners()),{headers})}
  catch{return Response.json({error:'فهرست اعضا دریافت نشد؛ دوباره تلاش کن.'},{status:503,headers})}
}
