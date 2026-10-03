export function memberStatus(member) {
  return member.subscribed ? 'active' : member.news_opt_out ? 'stopped' : 'unavailable';
}
export const memberStatusLabels = { active:'دریافت پیام فعال', stopped:'توقف دریافت به درخواست عضو', unavailable:'ارسال فعلاً ممکن نیست' };

function filters(options={}) {
  const where=[], values=[];
  const platform=['telegram','bale'].includes(options.platform) ? options.platform : 'all';
  const status=['active','stopped','unavailable'].includes(options.status) ? options.status : 'all';
  const q=String(options.q || '').trim().slice(0,100).replace(/[۰-۹٠-٩]/g,c=>'۰۱۲۳۴۵۶۷۸۹'.includes(c)?String('۰۱۲۳۴۵۶۷۸۹'.indexOf(c)):String('٠١٢٣٤٥٦٧٨٩'.indexOf(c))).replaceAll('ي','ی').replaceAll('ك','ک');
  if(platform!=='all'){where.push('platform=?');values.push(platform);}
  if(status==='active')where.push('subscribed=1');
  if(status==='stopped')where.push('subscribed=0 AND news_opt_out=1');
  if(status==='unavailable')where.push('subscribed=0 AND news_opt_out=0');
  if(q){where.push("(replace(replace(name,'ي','ی'),'ك','ک') LIKE ? ESCAPE '\\' OR CAST(chat AS TEXT) LIKE ? ESCAPE '\\')");const term='%'+q.replace(/[\\%_]/g,'\\$&')+'%';values.push(term,term);}
  return {clause:where.length?' WHERE '+where.join(' AND '):'',values,filters:{platform,status,q}};
}
function formatMember(row,owners) {
  return {platform:row.platform,id:String(row.chat),name:row.name || 'بدون نام',created:row.created,
    status:memberStatus(row),isOwner:String(owners[row.platform] || '')===String(row.chat)};
}

export async function readMembers(db,options={},owners={}) {
  const query=filters(options);
  const pageSize=25;
  const count=await db.prepare('SELECT COUNT(*) n FROM members'+query.clause).bind(...query.values).first();
  const total=Number(count?.n || 0), pages=Math.max(1,Math.ceil(total/pageSize));
  const requestedPage=Number(options.page);
  const page=Number.isSafeInteger(requestedPage)?Math.min(pages,Math.max(1,requestedPage)):1;
  const [rows,summary]=await Promise.all([
    db.prepare('SELECT platform,chat,name,created,subscribed,news_opt_out FROM members'+query.clause+' ORDER BY created DESC,platform,chat LIMIT ? OFFSET ?').bind(...query.values,pageSize,(page-1)*pageSize).all(),
    db.prepare(`SELECT platform,COUNT(*) total,SUM(CASE WHEN subscribed=1 THEN 1 ELSE 0 END) active,
      SUM(CASE WHEN subscribed=0 AND news_opt_out=1 THEN 1 ELSE 0 END) stopped,
      SUM(CASE WHEN subscribed=0 AND news_opt_out=0 THEN 1 ELSE 0 END) unavailable FROM members GROUP BY platform`).all(),
  ]);
  return {members:(rows.results || []).map(r=>formatMember(r,owners)),total,page,pages,pageSize,filters:query.filters,
    summary:['telegram','bale'].map(platform=>{const r=(summary.results || []).find(r=>r.platform===platform);return {platform,total:Number(r?.total||0),active:Number(r?.active||0),stopped:Number(r?.stopped||0),unavailable:Number(r?.unavailable||0)};})};
}

export async function exportMembers(db,options={},owners={}) {
  const query=filters(options);
  const rows=await db.prepare('SELECT platform,chat,name,created,subscribed,news_opt_out FROM members'+query.clause+' ORDER BY created DESC,platform,chat LIMIT 10001').bind(...query.values).all();
  if((rows.results || []).length>10000)throw new Error('EXPORT_TOO_LARGE');
  return (rows.results || []).map(r=>formatMember(r,owners));
}
