import {adminUser,adminHeaders as headers} from '@/lib/admin';
export const dynamic='force-dynamic';
export async function POST(request:Request){const user=await adminUser(request);return user?Response.json({user},{headers}):Response.json({error:'ورود مدیر فقط از حساب مجاز در پیام‌رسان امکان‌پذیر است. مینی‌اپ را ببند و از دکمه ورود به آلیس در بات دوباره باز کن.'},{status:401,headers})}
