import {adminUser,adminHeaders as headers} from '@/lib/admin';
import {botDatabase} from '@/lib/admin-data';
import {recentCampaignReports} from '../../../../../cloudflare-bot/src/reports.js';
export const dynamic='force-dynamic';
export async function POST(request:Request){
  if(!await adminUser(request))return Response.json({error:'گزارش ارسال فقط برای مدیر قابل مشاهده است.'},{status:401,headers});
  try{return Response.json({reports:await recentCampaignReports(botDatabase(),10)},{headers})}
  catch{return Response.json({error:'گزارش‌ها دریافت نشد؛ دوباره تلاش کن.'},{status:503,headers})}
}
