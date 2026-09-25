import { copy, menu, menuLabels, platforms, audienceButtons } from './config.js';

export const adminMenu = [['ارسال همگانی', 'گزارش ارسال'], ['مقصدهای ارسال', 'بازگشت']];
const now = () => Math.floor(Date.now() / 1000);
const parse = value => { try { return JSON.parse(value); } catch { return null; } };
const own = (env, platform, id) => id != null && String(id) === String(env[platforms[platform].owner]);
const label = platform => platform === 'bale' ? 'بله' : 'تلگرام';
const fa = n => Number(n).toLocaleString('fa-IR');
const commandLabels = new Set([...menuLabels, ...audienceButtons.flat(), 'لغو ارسال', 'بازگشت به مقصدها', 'ارسال به انتخاب‌شده‌ها']);
const keyboard = rows => rows ? { keyboard: rows, resize_keyboard: true } : { remove_keyboard: true };
const button = (text, key, action) => ({ text, callback_data: `bc:${key}:${action}` });

export function contentOf(message) {
  if (message.media_group_id) return { error: 'عکس‌ها یا ویدئوهای آلبوم را جداگانه بفرست؛ هر ارسال شامل یک عکس یا یک ویدئو است.' };
  if (message.video && Number(message.video.file_size || 0) > 20 * 1024 * 1024) return { error: 'حجم ویدئو باید حداکثر ۲۰ مگابایت باشد.' };
  if ((message.caption || '').length > 1024) return { error: 'کپشن طولانی است؛ آن را به حداکثر ۱۰۲۴ نویسه کوتاه کن.' };
  if (message.video?.file_id) return { method: 'sendVideo', video: message.video.file_id, caption: message.caption || '' };
  if (message.photo?.length) return { method: 'sendPhoto', photo: message.photo.at(-1).file_id, caption: message.caption || '' };
  const text = String(message.text || '').trim();
  if (text.length > 4096) return { error: 'متن طولانی است؛ آن را به حداکثر ۴۰۹۶ نویسه کوتاه کن.' };
  if (text) return { method: 'sendMessage', text };
  return { error: 'متن، یک عکس یا یک ویدئو بفرست. عکس و ویدئو می‌توانند کپشن داشته باشند.' };
}

function audienceMarkup(key) {
  return { inline_keyboard: [
    [button('ارسال به اعضای هر دو بات', key, 'members')],
    [button('ارسال به همهٔ گروه‌ها و کانال‌ها', key, 'groups_all')],
    [button('ارسال به همه‌جا', key, 'all')],
    [button('انتخاب گروه‌ها و کانال‌ها', key, 'choose')],
    [button('تغییر پیام', key, 'change'), button('لغو ارسال', key, 'cancel')],
  ] };
}
function groupMarkup(data, selected) {
  const pages = Math.max(1, Math.ceil(data.places.length / 8));
  const page = Math.min(pages - 1, data.page || 0);
  const rows = data.places.slice(page * 8, (page + 1) * 8).map((p, i) => [button(
    `${selected.includes(`${p.platform}:${p.chat}`) ? '✅ ' : ''}${label(p.platform)} · ${p.kind === 'channel' ? 'کانال' : 'گروه'} ${p.title.slice(0, 32)}`,
    data.key, `g${page * 8 + i}`)]);
  if (pages > 1) rows.push([button('صفحهٔ قبل', data.key, `p${Math.max(0,page-1)}`), button('صفحهٔ بعد', data.key, `p${Math.min(pages-1,page+1)}`)]);
  rows.push([button(`ارسال به ${fa(selected.length)} مقصد انتخاب‌شده`, data.key, 'send')]);
  rows.push([button('بازگشت به مقصدها', data.key, 'back'), button('لغو ارسال', data.key, 'cancel')]);
  return { inline_keyboard: rows };
}

export async function campaignSummary(db, campaign) {
  const rows = (await db.prepare('SELECT platform,status,COUNT(*) n FROM outbox WHERE campaign=? GROUP BY platform,status').bind(campaign).all()).results || [];
  const names = { sent:'موفق', pending:'در انتظار', sending:'در حال ارسال', failed:'ناموفق', unknown:'نتیجه نامشخص' };
  return Object.keys(platforms).map(p => {
    const counts = rows.filter(r=>r.platform===p);
    return counts.length ? `${label(p)}: ${counts.map(r=>`${fa(r.n)} ${names[r.status] || 'نامشخص'}`).join('، ')}` : '';
  }).filter(Boolean).join('\n');
}

// Bale can restart its update sequence. Message identity includes chat/date;
// identical webhook retries retain the same key, fresh messages do not collide.
export function eventKey(platform, update) {
  if (update.callback_query?.id != null) return `${platform}:callback:${update.callback_query.id}`;
  const m = update.message || update.channel_post;
  if (m?.message_id != null && m.chat?.id != null) return `${platform}:message:${m.chat.id}:${m.message_id}:${m.date || 0}`;
  if (update.update_id != null && Number.isSafeInteger(Number(update.update_id))) return `${platform}:update:${update.update_id}`;
  throw new Error('INVALID_UPDATE');
}

async function planUpdate(env, platform, update, write) {
  const db = env.DB;
  const queue = (chat, text, markup = keyboard(menu(env,platform,chat))) => write('INSERT INTO outbox(platform,chat,method,payload) VALUES (?,?,?,?)', platform,chat,'sendMessage',JSON.stringify({text,reply_markup:markup}));
  const edit = (chat, messageId, text, markup = {inline_keyboard:[]}) => write('INSERT INTO outbox(platform,chat,method,payload) VALUES (?,?,?,?)', platform,chat,'editMessageText',JSON.stringify({message_id:messageId,text,reply_markup:markup}));
  const saveDraft = (owner,stage,data={},selected=[]) => write('INSERT INTO drafts(platform,owner,stage,payload,targets,expires) VALUES (?,?,?,?,?,?) ON CONFLICT(platform,owner) DO UPDATE SET stage=excluded.stage,payload=excluded.payload,targets=excluded.targets,expires=excluded.expires',platform,owner,stage,JSON.stringify(data),JSON.stringify(selected),now()+3600);
  const clearDraft = owner => write('DELETE FROM drafts WHERE platform=? AND owner=?',platform,owner);
  const places = async () => (await db.prepare('SELECT platform,chat,title,kind FROM destinations WHERE active=1 ORDER BY platform,title,chat').all()).results || [];
  const savePlace = (chat,active) => write('INSERT INTO destinations(platform,chat,title,kind,active) VALUES (?,?,?,?,?) ON CONFLICT(platform,chat) DO UPDATE SET title=excluded.title,kind=excluded.kind,active=excluded.active',platform,chat.id,chat.title||'مقصد آلیس',chat.type==='channel'?'channel':'group',Number(active));

  const cb = update.callback_query;
  if (cb) {
    const chat = cb.message?.chat;
    if (!chat || chat.type !== 'private' || !own(env,platform,cb.from?.id) || String(cb.from.id)!==String(chat.id)) return 'این بخش مخصوص مدیر مجموعه است.';
    const match = /^bc:([a-f0-9]{12}):([a-z0-9_]+)$/.exec(cb.data || '');
    if (!match) return 'این دکمه قدیمی است. «ارسال همگانی» را بزن.';
    const draft = await db.prepare('SELECT * FROM drafts WHERE platform=? AND owner=?').bind(platform,cb.from.id).first();
    const data = parse(draft?.payload);
    if (!draft || data?.key!==match[1] || draft.expires < now()) return 'این پیام قبلاً ارسال یا لغو شده، یا زمان آن گذشته است. برای پیام تازه «ارسال همگانی» را بزن.';
    const action = match[2], selected = parse(draft.targets) || [];
    if (action==='cancel') { clearDraft(cb.from.id); edit(chat.id,cb.message.message_id,'ارسال لغو شد؛ پیامی منتشر نشد.'); return 'لغو شد'; }
    if (action==='change') { saveDraft(cb.from.id,'content'); edit(chat.id,cb.message.message_id,'متن، عکس یا ویدئوی تازه را بفرست.'); return 'منتظر پیام تازه هستم'; }
    if (action==='back') { saveDraft(cb.from.id,'targets',data); edit(chat.id,cb.message.message_id,'مقصد را انتخاب کن؛ دکمه‌های «ارسال» پیام را منتشر می‌کنند. همهٔ گزینه‌ها شامل تلگرام و بله‌اند.',audienceMarkup(data.key)); return ''; }
    if (draft.stage==='targets' && action==='choose') {
      data.places = await places(); data.page=0;
      if (!data.places.length) return 'هنوز گروه یا کانالی متصل نشده است.';
      saveDraft(cb.from.id,'groups',data);
      edit(chat.id,cb.message.message_id,'گروه‌ها و کانال‌های دلخواه را علامت بزن؛ سپس «ارسال به مقصدهای انتخاب‌شده» را بزن.',groupMarkup(data,[])); return '';
    }
    if (draft.stage==='groups' && /^g\d+$/.test(action)) {
      const p = data.places?.[Number(action.slice(1))];
      if (!p) return 'این مقصد در فهرست نیست.';
      const key = `${p.platform}:${p.chat}`;
      const next = selected.includes(key)?selected.filter(x=>x!==key):[...selected,key];
      saveDraft(cb.from.id,'groups',data,next);
      edit(chat.id,cb.message.message_id,`${fa(next.length)} مقصد انتخاب شده. با زدن دکمهٔ ارسال، پیام منتشر می‌شود.`,groupMarkup(data,next)); return '';
    }
    if (draft.stage==='groups' && /^p\d+$/.test(action)) {
      const page=Number(action.slice(1));
      if (page===data.page) return '';
      data.page=Math.min(Math.max(0,Math.ceil(data.places.length/8)-1),page);
      saveDraft(cb.from.id,'groups',data,selected);
      edit(chat.id,cb.message.message_id,`${fa(selected.length)} مقصد انتخاب شده.`,groupMarkup(data,selected)); return '';
    }
    const validSend = draft.stage==='targets' && ['members','groups_all','all'].includes(action) || draft.stage==='groups' && action==='send';
    if (!validSend || !data.content?.method) return 'از دکمه‌های همین مرحله استفاده کن.';
    const currentPlaces=await places();
    const recipients=new Map();
    if (['members','all'].includes(action)) {
      for (const m of (await db.prepare('SELECT platform,chat FROM members WHERE subscribed=1').all()).results || []) recipients.set(`${m.platform}:${m.chat}`,{...m,destination:0});
    }
    if (['groups_all','all','send'].includes(action)) {
      for (const p of currentPlaces) if (action!=='send'||selected.includes(`${p.platform}:${p.chat}`)) recipients.set(`${p.platform}:${p.chat}`,{...p,destination:1});
    }
    if (action==='send' && currentPlaces.filter(p=>selected.includes(`${p.platform}:${p.chat}`)).length!==selected.length) return 'یکی از مقصدها دیگر فعال نیست؛ به فهرست مقصدها برگرد و دوباره انتخاب کن.';
    if (!recipients.size) return 'مخاطبی انتخاب نشده یا مقصد فعالی وجود ندارد؛ چیزی ارسال نشد.';
    const campaign=(await db.prepare('SELECT COALESCE(MAX(id),0)+1 id FROM campaigns').first()).id;
    write('INSERT INTO campaigns(id,source_platform,owner) VALUES (?,?,?)',campaign,platform,cb.from.id);
    write('INSERT INTO campaign_meta(campaign,draft_key) VALUES (?,?)',campaign,`${platform}:${data.key}`);
    // One INSERT SELECT per audience chunk avoids partial broadcasts and D1's
    // statement/bind limits, even when the audience grows beyond a few members.
    const targets=[...recipients.values()].map(p=>({platform:p.platform,chat:p.chat,destination:p.destination}));
    for(let offset=0;offset<targets.length;offset+=200) {
      write(`INSERT INTO outbox(platform,chat,method,payload,campaign,destination)
        SELECT json_extract(value,'$.platform'),json_extract(value,'$.chat'),?,
        CASE WHEN json_extract(value,'$.platform')<>? AND ?<>'sendMessage' THEN json_set(?, '$._media_source', ?) ELSE ? END,
        ?,json_extract(value,'$.destination') FROM json_each(?)`,data.content.method,platform,data.content.method,JSON.stringify(data.content),platform,JSON.stringify(data.content),campaign,JSON.stringify(targets.slice(offset,offset+200)));
    }
    clearDraft(cb.from.id);
    const breakdown=Object.keys(platforms).map(p=>`${label(p)}: ${fa(targets.filter(x=>x.platform===p).length)} مقصد`).join(' · ');
    edit(chat.id,cb.message.message_id,`ارسال آغاز شد.\n${breakdown}\nنتیجهٔ نهایی همین‌جا اعلام می‌شود.`);
    return 'ارسال آغاز شد';
  }

  const memberEvent=update.my_chat_member;
  if (memberEvent?.chat && ['group','supergroup','channel'].includes(memberEvent.chat.type)) {
    const existing=await db.prepare('SELECT active FROM destinations WHERE platform=? AND chat=?').bind(platform,memberEvent.chat.id).first();
    savePlace(memberEvent.chat,['member','administrator','creator'].includes(memberEvent.new_chat_member?.status)&&Boolean(existing?.active));
  }
  const message=update.message||update.channel_post;
  if (!message?.chat) return '';
  const chat=message.chat, text=String(message.text||'').trim();
  const command=text.split(/\s+/)[0].split('@')[0];
  if(chat.type!=='private') {
    const channel=chat.type==='channel';
    if((channel || own(env,platform,message.from?.id)&&!message.sender_chat) && ['/connect','/disconnect'].includes(command)) {
      savePlace(chat,command==='/connect');
      queue(channel?Number(env[platforms[platform].owner]):chat.id,`${channel?'کانال':'گروه'} ${chat.title||''} ${command==='/connect'?'به مقصدهای آلیس اضافه شد.':'از مقصدهای فعال خارج شد.'}`,channel?keyboard(adminMenu):keyboard(null));
    }
    return '';
  }
  if(message.from?.id==null || String(message.from.id)!==String(chat.id)) return '';
  write('INSERT INTO members(platform,chat,name,subscribed) VALUES (?,?,?,1) ON CONFLICT(platform,chat) DO UPDATE SET name=excluded.name',platform,chat.id,String(message.from.first_name||'عضو آلیس').slice(0,100));
  if(own(env,platform,message.from.id)) {
    const owner=message.from.id;
    if(['/report','گزارش ارسال'].includes(text)) {
      const runs=(await db.prepare('SELECT id FROM campaigns ORDER BY id DESC LIMIT 3').all()).results||[];
      const summaries=[];
      for(const run of runs) summaries.push(`ارسال ${fa(run.id)}\n${await campaignSummary(db,run.id)}`);
      queue(chat.id,summaries.join('\n\n')||'هنوز پیامی منتشر نشده است.',keyboard(adminMenu)); return '';
    }
    if(['/admin','مدیریت ارسال','مقصدهای ارسال'].includes(text)) {
      const list=await places();
      queue(chat.id,'پیام، عکس یا ویدئو را همین‌جا بفرست؛ سپس مقصد را انتخاب کن.\nهمهٔ انتخاب‌ها تلگرام و بله را پوشش می‌دهند.\n\nگروه‌ها و کانال‌های متصل:\n'+(list.map(p=>`${label(p.platform)} · ${p.title}`).join('\n')||'هنوز مقصدی متصل نشده است.'),keyboard(adminMenu));return '';
    }
    if(['/broadcast','ارسال همگانی','تغییر پیام'].includes(text)) {
      saveDraft(owner,'content');queue(chat.id,'متن، یک عکس یا یک ویدئو را بفرست؛ بعد مقصد را انتخاب می‌کنی.\nعکس و ویدئو می‌توانند کپشن داشته باشند. ویدئو حداکثر ۲۰ مگابایت باشد.',keyboard(adminMenu));return '';
    }
    const draft=await db.prepare('SELECT * FROM drafts WHERE platform=? AND owner=?').bind(platform,owner).first();
    if(['/cancel','لغو ارسال'].includes(text)) {clearDraft(owner);queue(chat.id,'پیش‌نویس لغو شد؛ پیامی منتشر نشد.',keyboard(adminMenu));return '';}
    if(['/start','/menu','بازگشت'].includes(command)) clearDraft(owner);
    else if(!text.startsWith('/') && !menuLabels.has(text)) {
      if(commandLabels.has(text)||text.startsWith('✅ ')||/^(گروه|کانال) (بله|تلگرام) ·/.test(text)) {
        const data=parse(draft?.payload);
        if(data?.key && data.content && draft.expires>=now()) queue(chat.id,'مقصد را از دکمه‌های زیر انتخاب کن. زدن «ارسال» پیام را منتشر می‌کند.',audienceMarkup(data.key));
        else queue(chat.id,'این دکمه مربوط به ارسال قبلی است. برای پیام تازه «ارسال همگانی» را بزن.',keyboard(adminMenu));
        return '';
      }
      const content=contentOf(message);
      if(content.error) {queue(chat.id,content.error,keyboard(adminMenu));return '';}
      const data={key:crypto.randomUUID().replaceAll('-','').slice(0,12),content};
      saveDraft(owner,'targets',data);
      queue(chat.id,'پیام آماده است. کجا منتشر شود؟\n«همه‌جا» یعنی اعضای هر دو بات و تمام گروه‌ها و کانال‌های متصل.\nبا زدن دکمهٔ ارسال، انتشار شروع می‌شود.',audienceMarkup(data.key));return '';
    }
  }
  if(command==='/start'||['/menu','/cancel','بازگشت'].includes(text)) {
    if(command==='/start') write('UPDATE members SET subscribed=1 WHERE platform=? AND chat=? AND news_opt_out=0',platform,chat.id);
    queue(chat.id,`${copy.welcome}\nخبرها و پیشنهادها همین‌جا می‌آیند. توقف دریافت: /stop`);
  } else if(command==='/stop'||['لغو خبرها','توقف خبرها'].includes(text)) {
    write('UPDATE members SET subscribed=0,news_opt_out=1 WHERE platform=? AND chat=?',platform,chat.id);queue(chat.id,'دریافت خبرهای خصوصی متوقف شد.');
  } else if(command==='/subscribe') {
    write('UPDATE members SET subscribed=1,news_opt_out=0 WHERE platform=? AND chat=?',platform,chat.id);queue(chat.id,'دریافت خبرها دوباره فعال شد.');
  } else if(command==='/myid') queue(chat.id,`شناسه حساب تو در ${label(platform)}:\n${message.from.id}`);
  else if(text==='بدنسازی') queue(chat.id,copy.gym);
  else if(text==='استخر و سونا') queue(chat.id,copy.pool);
  else if(text==='نشانی مجموعه') queue(chat.id,copy.address);
  else queue(chat.id,'خدمات موردنظرت را از منو انتخاب کن.');
  return '';
}

export async function handleUpdate(env, platform, update) {
  const key=eventKey(platform,update);
  // Primary reads and optimistic versioning serialize changes across both bots.
  // D1 batch rolls everything back on a version conflict or duplicate event.
  for(let attempt=0;attempt<6;attempt++) {
    const db=env.DB.withSession?env.DB.withSession('first-primary'):env.DB;
    const version=(await db.prepare('SELECT version FROM bot_revision WHERE id=1').first()).version;
    if(await db.prepare('SELECT 1 FROM bot_events WHERE event_key=?').bind(key).first()) return '';
    const statements=[];
    const write=(sql,...args)=>statements.push(db.prepare(sql).bind(...args));
    const feedback=await planUpdate({...env,DB:db},platform,update,write);
    try {
      await db.batch([
        db.prepare('UPDATE bot_revision SET version=CASE WHEN version=? THEN version+1 ELSE NULL END WHERE id=1').bind(version),
        db.prepare('INSERT INTO bot_events(event_key) VALUES (?)').bind(key),
        ...statements,
      ]);
      return feedback;
    } catch(error) {
      if(!/bot_revision.version|bot_events.event_key|campaign_meta.draft_key|campaigns.id/.test(String(error.message))) throw error;
    }
  }
  throw new Error('UPDATE_CONFLICT');
}
