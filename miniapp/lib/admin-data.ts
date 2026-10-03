import {env} from 'cloudflare:workers';
import {z} from 'zod';

const filterSchema=z.object({
  q:z.string().max(100).default(''),
  platform:z.enum(['all','telegram','bale']).default('all'),
  status:z.enum(['all','active','stopped','unavailable']).default('all'),
  page:z.number().int().min(1).max(100000).default(1),
});
export async function memberFilters(request:Request){
  const raw=await request.text();
  if(raw.length>2000)throw new Error('INVALID_FILTER');
  return filterSchema.parse(raw?JSON.parse(raw):{});
}
export function botDatabase(){
  const database=(env as unknown as {BOT_DB?:D1Database}).BOT_DB;
  if(!database)throw new Error('BOT_DATABASE_UNAVAILABLE');
  return database.withSession('first-primary');
}
export function memberOwners(){
  const e=env as unknown as Record<string,string>;
  return {telegram:e.TELEGRAM_OWNER_ID||e.ALICE_OWNER_ID,bale:e.BALE_OWNER_ID||e.ALICE_BALE_OWNER_ID};
}
