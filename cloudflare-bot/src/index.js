import { audienceButtons, copy, menu, menuLabels, miniappUrl, platforms } from './config.js';

const adminMenu = [['ارسال همگانی', 'گزارش ارسال'], ['مقصدهای ارسال', 'بازگشت']];
const now = () => Math.floor(Date.now() / 1000);
const json = (body, status = 200) => Response.json(body, { status, headers: { 'Cache-Control': 'no-store' } });
const own = (env, platform, id) => id != null && String(id) === String(env[platforms[platform].owner]);
const keyboard = rows => rows ? { keyboard: rows, resize_keyboard: true } : { remove_keyboard: true };
const parse = value => { try { return JSON.parse(value); } catch { return null; } };

async function api(env, platform, method, payload = {}) {
  const token = env[platforms[platform].token];
  if (!token) throw new Error('BOT_TOKEN_MISSING');
  const response = await fetch(`${platforms[platform].api}/bot${token}/${method}`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
  });
  const result = await response.json().catch(() => null);
  if (!result?.ok) {
    const error = new Error(`API_${result?.error_code || response.status}`);
    error.status = Number(result?.error_code || response.status);
    error.retryAfter = Number(result?.parameters?.retry_after || 0);
    throw error;
  }
  return result.result;
}

async function queue(env, platform, chat, text, rows = menu(env, platform, chat), campaign = null) {
  const payload = { text, reply_markup: keyboard(rows) };
  await env.DB.prepare('INSERT INTO outbox(platform,chat,method,payload,campaign) VALUES (?,?,?,?,?)')
    .bind(platform, chat, 'sendMessage', JSON.stringify(payload), campaign).run();
}

async function saveDestination(env, platform, chat, title, kind, active) {
  await env.DB.prepare('INSERT INTO destinations(platform,chat,title,kind,active) VALUES (?,?,?,?,?) ON CONFLICT(platform,chat) DO UPDATE SET title=excluded.title,kind=excluded.kind,active=excluded.active')
    .bind(platform, chat, title || 'مقصد آلیس', kind, Number(active)).run();
}

async function destinations(env) {
  const result = await env.DB.prepare('SELECT platform,chat,title,kind FROM destinations WHERE active=1 ORDER BY platform,title').all();
  return result.results || [];
}

async function setDraft(env, platform, owner, stage, payload = {}, targets = []) {
  await env.DB.prepare('INSERT INTO drafts(platform,owner,stage,payload,targets,expires) VALUES (?,?,?,?,?,?) ON CONFLICT(platform,owner) DO UPDATE SET stage=excluded.stage,payload=excluded.payload,targets=excluded.targets,expires=excluded.expires')
    .bind(platform, owner, stage, JSON.stringify(payload), JSON.stringify(targets), now() + 3600).run();
}

async function report(env, platform, chat) {
  const runs = await env.DB.prepare('SELECT id FROM campaigns ORDER BY id DESC LIMIT 5').all();
  const lines = [];
  for (const run of runs.results || []) {
    const counts = await env.DB.prepare('SELECT platform,status,COUNT(*) n FROM outbox WHERE campaign=? GROUP BY platform,status').bind(run.id).all();
    const summary = (counts.results || []).map(row => `${row.platform === 'bale' ? 'بله' : 'تلگرام'} ${row.status}: ${row.n}`).join(' · ');
    lines.push(`#${run.id}: ${summary || 'بدون مقصد'}`);
  }
  await queue(env, platform, chat, lines.join('\n') || 'هنوز ارسال همگانی ثبت نشده است.', adminMenu);
}

function contentOf(message) {
  if (message.media_group_id) return null;
  if (message.video) {
    if (Number(message.video.file_size || 0) > 20 * 1024 * 1024) return null;
    return { method: 'sendVideo', video: message.video.file_id, caption: message.caption || '' };
  }
  if (message.photo?.length) return { method: 'sendPhoto', photo: message.photo.at(-1).file_id, caption: message.caption || '' };
  if (message.text?.trim()) return { method: 'sendMessage', text: message.text.trim() };
  return null;
}

async function publish(env, sourcePlatform, owner, payload, targets, sourceChat) {
  const recipients = [];
  if (targets.includes('members')) {
    const members = await env.DB.prepare('SELECT platform,chat FROM members WHERE subscribed=1').all();
    for (const row of members.results || []) recipients.push({ ...row, destination: 0 });
  }
  for (const item of await destinations(env)) {
    if (targets.includes(`${item.platform}:${item.chat}`)) recipients.push({ platform: item.platform, chat: item.chat, destination: 1 });
  }
  if (!recipients.length) {
    await queue(env, sourcePlatform, sourceChat, 'مخاطب فعالی برای این انتخاب پیدا نشد؛ چیزی منتشر نشد.', audienceButtons);
    return;
  }
  const run = await env.DB.prepare('INSERT INTO campaigns(source_platform,owner) VALUES (?,?)').bind(sourcePlatform, owner).run();
  const campaign = run.meta.last_row_id;
  for (const target of recipients) {
    const outbound = { ...payload };
    if (target.platform !== sourcePlatform && payload.method !== 'sendMessage') outbound._media_source = sourcePlatform;
    await env.DB.prepare('INSERT INTO outbox(platform,chat,method,payload,campaign,destination) VALUES (?,?,?,?,?,?)')
      .bind(target.platform, target.chat, outbound.method, JSON.stringify(outbound), campaign, target.destination).run();
  }
  await env.DB.prepare('DELETE FROM drafts WHERE platform=? AND owner=?').bind(sourcePlatform, owner).run();
  await queue(env, sourcePlatform, sourceChat, `ارسال به ${recipients.length} مقصد شروع شد. نتیجه را در «گزارش ارسال» ببین.`, adminMenu);
}

async function broadcast(env, platform, message) {
  const chat = message.chat.id, owner = message.from.id, text = (message.text || '').trim();
  if (text === '/report' || text === 'گزارش ارسال') { await report(env, platform, chat); return true; }
  if (text === '/admin' || text === 'مدیریت ارسال' || text === 'مقصدهای ارسال') {
    const places = await destinations(env);
    await queue(env, platform, chat, 'مدیریت ارسال آلیس\nپیام، عکس یا ویدئو را همین‌جا بفرست؛ سپس مقصد را انتخاب کن.\n\nمقصدهای فعال:\n' + (places.map(x => `${x.platform === 'bale' ? 'بله' : 'تلگرام'} · ${x.title}`).join('\n') || 'هنوز گروه یا کانالی ثبت نشده است.'), adminMenu);
    return true;
  }
  if (text === '/broadcast' || text === 'ارسال همگانی') {
    await setDraft(env, platform, owner, 'content');
    await queue(env, platform, chat, 'پیام را بفرست: متن، یک عکس یا یک ویدئوی کوتاه همراه کپشن. آلبوم پشتیبانی نمی‌شود.', [['لغو ارسال']]);
    return true;
  }
  let draft = await env.DB.prepare('SELECT * FROM drafts WHERE platform=? AND owner=?').bind(platform, owner).first();
  if (!draft && !text.startsWith('/') && !menuLabels.has(text) && contentOf(message)) {
    await setDraft(env, platform, owner, 'content');
    draft = { stage: 'content' };
  }
  if (!draft) return false;
  if (draft.expires && draft.expires < now() || ['لغو ارسال', '/cancel', '/start', '/menu', 'بازگشت'].includes(text)) {
    await env.DB.prepare('DELETE FROM drafts WHERE platform=? AND owner=?').bind(platform, owner).run();
    if (['/start', '/menu', 'بازگشت'].includes(text)) return false;
    await queue(env, platform, chat, 'پیش‌نویس لغو شد.', adminMenu);
    return true;
  }
  if (text === 'تغییر پیام') {
    await setDraft(env, platform, owner, 'content');
    await queue(env, platform, chat, 'پیام تازه را بفرست.', [['لغو ارسال']]);
    return true;
  }
  if (draft.stage === 'content') {
    const payload = contentOf(message);
    if (!payload || (payload.method !== 'sendMessage' && payload.caption.length > 1024) || (payload.text?.length || 0) > 4096) {
      await queue(env, platform, chat, 'متن، یک عکس یا یک ویدئوی کوتاه همراه کپشن بفرست؛ ویدئو حداکثر ۲۰ مگابایت باشد.', [['لغو ارسال']]);
      return true;
    }
    await setDraft(env, platform, owner, 'targets', payload);
    await queue(env, platform, chat, 'پیام آماده است. کجا منتشر شود؟ «همه» شامل اعضای هر دو بات و گروه‌ها و کانال‌های ثبت‌شده است.', audienceButtons);
    return true;
  }
  const payload = parse(draft.payload);
  if (!payload?.method) { await setDraft(env, platform, owner, 'content'); return true; }
  const places = await destinations(env);
  const groupTargets = places.map(x => `${x.platform}:${x.chat}`);
  if (draft.stage === 'targets') {
    if (text === 'ارسال به همهٔ اعضا و گروه‌ها') return await publish(env, platform, owner, payload, ['members', ...groupTargets], chat), true;
    if (text === 'ارسال فقط به اعضای بات') return await publish(env, platform, owner, payload, ['members'], chat), true;
    if (text === 'ارسال به همهٔ گروه‌ها و کانال‌ها') return await publish(env, platform, owner, payload, groupTargets, chat), true;
    if (text === 'انتخاب گروه‌ها و کانال‌ها') {
      await setDraft(env, platform, owner, 'groups', payload, []);
      await queue(env, platform, chat, 'مقصدها را انتخاب کن.', groupKeyboard(places, []));
      return true;
    }
    await queue(env, platform, chat, 'یکی از مقصدها را انتخاب کن.', audienceButtons);
    return true;
  }
  const selected = parse(draft.targets) || [];
  if (text === 'بازگشت به مقصدها') {
    await setDraft(env, platform, owner, 'targets', payload);
    await queue(env, platform, chat, 'کجا منتشر شود؟', audienceButtons);
    return true;
  }
  if (text === 'ارسال به انتخاب‌شده‌ها') return await publish(env, platform, owner, payload, selected, chat), true;
  const choices = [['اعضای بات', 'members'], ...places.map(x => [`${x.kind === 'channel' ? 'کانال' : 'گروه'} ${x.platform === 'bale' ? 'بله' : 'تلگرام'} · ${x.title.slice(0, 35)} · ${x.chat}`, `${x.platform}:${x.chat}`])];
  const key = text.startsWith('✅ ') ? text.slice(2) : text;
  const target = choices.find(x => x[0] === key)?.[1];
  if (target) {
    const next = selected.includes(target) ? selected.filter(x => x !== target) : [...selected, target];
    await setDraft(env, platform, owner, 'groups', payload, next);
    await queue(env, platform, chat, `${next.length} مقصد انتخاب شده.`, groupKeyboard(places, next));
  } else await queue(env, platform, chat, 'مقصدهای دلخواه را انتخاب کن.', groupKeyboard(places, selected));
  return true;
}

function groupKeyboard(places, selected) {
  const choices = [['اعضای بات', 'members'], ...places.map(x => [`${x.kind === 'channel' ? 'کانال' : 'گروه'} ${x.platform === 'bale' ? 'بله' : 'تلگرام'} · ${x.title.slice(0, 35)} · ${x.chat}`, `${x.platform}:${x.chat}`])];
  return [...choices.map(([label, value]) => [`${selected.includes(value) ? '✅ ' : ''}${label}`]), ['ارسال به انتخاب‌شده‌ها'], ['بازگشت به مقصدها'], ['تغییر پیام', 'لغو ارسال']];
}

async function handleUpdate(env, platform, update) {
  const id = update.update_id;
  if (!Number.isSafeInteger(id)) throw new Error('INVALID_UPDATE');
  const seen = await env.DB.prepare('SELECT 1 FROM processed_updates WHERE platform=? AND update_id=?').bind(platform, id).first();
  if (seen) return;
  const memberEvent = update.my_chat_member;
  if (memberEvent?.chat && ['group', 'supergroup', 'channel'].includes(memberEvent.chat.type)) {
    const newStatus = memberEvent.new_chat_member?.status;
    const existing = await env.DB.prepare('SELECT active FROM destinations WHERE platform=? AND chat=?').bind(platform, memberEvent.chat.id).first();
    const joined = ['member', 'administrator', 'creator'].includes(newStatus);
    await saveDestination(env, platform, memberEvent.chat.id, memberEvent.chat.title, memberEvent.chat.type === 'channel' ? 'channel' : 'group', joined && Boolean(existing?.active));
  }
  const message = update.message || update.channel_post;
  if (message?.chat) {
    const chat = message.chat;
    const command = (message.text || '').trim().split(/\s+/)[0].split('@')[0];
    if (chat.type !== 'private') {
      const channel = chat.type === 'channel';
      const allowed = channel || own(env, platform, message.from?.id) && !message.sender_chat;
      if (allowed && ['/connect', '/disconnect'].includes(command)) {
        await saveDestination(env, platform, chat.id, chat.title, channel ? 'channel' : 'group', command === '/connect');
        const note = `${channel ? 'کانال' : 'گروه'} ${chat.title || ''} ${command === '/connect' ? 'به مقصدهای آلیس اضافه شد.' : 'از مقصدهای فعال خارج شد.'}`;
        await queue(env, platform, channel ? Number(env[platforms[platform].owner]) : chat.id, note, channel ? adminMenu : null);
      }
    } else if (message.from?.id === chat.id) {
      await env.DB.prepare('INSERT INTO members(platform,chat,name,subscribed) VALUES (?,?,?,1) ON CONFLICT(platform,chat) DO UPDATE SET name=excluded.name')
        .bind(platform, chat.id, String(message.from.first_name || 'عضو آلیس').slice(0, 100)).run();
      const text = (message.text || '').trim();
      if (own(env, platform, message.from.id) && await broadcast(env, platform, message)) {
        // The owner composer handles this update.
      } else if (command === '/start' || ['/menu', '/cancel', 'بازگشت'].includes(text)) {
        if (command === '/start') await env.DB.prepare('UPDATE members SET subscribed=1 WHERE platform=? AND chat=? AND news_opt_out=0').bind(platform, chat.id).run();
        await queue(env, platform, chat.id, `${copy.welcome}\nخبرها و پیشنهادها همین‌جا می‌آیند. توقف دریافت: /stop`);
      } else if (command === '/stop' || ['لغو خبرها', 'توقف خبرها'].includes(text)) {
        await env.DB.prepare('UPDATE members SET subscribed=0,news_opt_out=1 WHERE platform=? AND chat=?').bind(platform, chat.id).run();
        await queue(env, platform, chat.id, 'دریافت خبرهای خصوصی متوقف شد.');
      } else if (command === '/subscribe') {
        await env.DB.prepare('UPDATE members SET subscribed=1,news_opt_out=0 WHERE platform=? AND chat=?').bind(platform, chat.id).run();
        await queue(env, platform, chat.id, 'دریافت خبرها دوباره فعال شد.');
      } else if (command === '/myid') {
        await queue(env, platform, chat.id, `شناسه حساب تو در ${platform === 'bale' ? 'بله' : 'تلگرام'}:\n${message.from.id}`);
      } else if (text === 'بدنسازی') await queue(env, platform, chat.id, copy.gym);
      else if (text === 'استخر و سونا') await queue(env, platform, chat.id, copy.pool);
      else if (text === 'نشانی مجموعه') await queue(env, platform, chat.id, copy.address);
      else await queue(env, platform, chat.id, 'به آلیس خوش آمدی. خدمات موردنظرت را از منو انتخاب کن.');
    }
  }
  await env.DB.prepare('INSERT OR IGNORE INTO processed_updates(platform,update_id) VALUES (?,?)').bind(platform, id).run();
}

async function transferMedia(env, targetPlatform, outbound) {
  const source = outbound._media_source;
  const field = outbound.method === 'sendVideo' ? 'video' : 'photo';
  const sourceToken = env[platforms[source].token];
  const info = await api(env, source, 'getFile', { file_id: outbound[field] });
  const path = String(info?.file_path || '');
  if (!path || path.startsWith('/') || path.split('/').includes('..')) throw new Error('INVALID_FILE_PATH');
  const file = await fetch(`${platforms[source].api}/file/bot${sourceToken}/${path}`);
  if (!file.ok) throw new Error(`FILE_${file.status}`);
  const bytes = await file.arrayBuffer();
  if (bytes.byteLength > 20 * 1024 * 1024) throw new Error('FILE_TOO_LARGE');
  const form = new FormData();
  form.set('chat_id', String(outbound.chat_id));
  if (outbound.caption) form.set('caption', outbound.caption);
  form.set(field, new Blob([bytes], { type: field === 'video' ? 'video/mp4' : 'image/jpeg' }), field === 'video' ? 'video.mp4' : 'photo.jpg');
  const token = env[platforms[targetPlatform].token];
  const response = await fetch(`${platforms[targetPlatform].api}/bot${token}/${outbound.method}`, { method: 'POST', body: form });
  const result = await response.json().catch(() => null);
  if (!result?.ok) {
    const error = new Error(`API_${result?.error_code || response.status}`);
    error.status = Number(result?.error_code || response.status);
    error.retryAfter = Number(result?.parameters?.retry_after || 0);
    throw error;
  }
}

async function deliver(env, row) {
  const payload = parse(row.payload) || {};
  const outbound = { ...payload, chat_id: row.chat };
  delete outbound.method;
  const source = outbound._media_source;
  delete outbound._media_source;
  try {
    if (source) await transferMedia(env, row.platform, { ...outbound, method: row.method, _media_source: source });
    else await api(env, row.platform, row.method, outbound);
    await env.DB.prepare("UPDATE outbox SET status='sent' WHERE id=?").bind(row.id).run();
  } catch (error) {
    const status = Number(error?.status || 0);
    const retry = status === 429 && row.attempts < 8;
    await env.DB.prepare('UPDATE outbox SET status=?,due=? WHERE id=?')
      .bind(retry ? 'pending' : status >= 400 && status < 500 ? 'failed' : 'unknown', retry ? now() + Math.max(1, Number(error.retryAfter || 30)) : 0, row.id).run();
    if (status === 403 && !row.destination) await env.DB.prepare('UPDATE members SET subscribed=0,news_opt_out=1 WHERE platform=? AND chat=?').bind(row.platform, row.chat).run();
  }
}

async function drain(env, limit = 8) {
  for (let i = 0; i < limit; i++) {
    const row = await env.DB.prepare("SELECT * FROM outbox WHERE status='pending' AND due<=? ORDER BY id LIMIT 1").bind(now()).first();
    if (!row) break;
    const claimed = await env.DB.prepare("UPDATE outbox SET status='sending',attempts=attempts+1 WHERE id=? AND status='pending'").bind(row.id).run();
    if (!claimed.meta.changes) continue;
    await deliver(env, { ...row, attempts: row.attempts + 1 });
    if (i + 1 < limit) await new Promise(resolve => setTimeout(resolve, 1100));
  }
}

async function install(env, request) {
  const actual = request.headers.get('authorization') || '';
  if (!env.SETUP_SECRET || actual !== `Bearer ${env.SETUP_SECRET}`) return json({ error: 'Unauthorized' }, 401);
  const root = new URL(request.url).origin;
  if (!env.TELEGRAM_BOT_TOKEN || !env.BALE_BOT_TOKEN || !env.TELEGRAM_WEBHOOK_SECRET || !env.BALE_WEBHOOK_SECRET) {
    return json({ error: 'Bot tokens and webhook secrets are required before registration' }, 500);
  }
  const done = {};
  for (const platform of Object.keys(platforms)) {
    const path = platform === 'telegram' ? '/webhook/telegram' : `/webhook/bale/${env.BALE_WEBHOOK_SECRET}`;
    const payload = { url: root + path };
    if (platform === 'telegram') {
      payload.secret_token = env.TELEGRAM_WEBHOOK_SECRET;
      payload.allowed_updates = ['message', 'channel_post', 'my_chat_member'];
    }
    await api(env, platform, 'setWebhook', payload);
    if (platform === 'telegram' && miniappUrl(env, platform)) {
      await api(env, platform, 'setChatMenuButton', { menu_button: { type: 'web_app', text: 'ورود به آلیس', web_app: { url: miniappUrl(env, platform) } } });
    }
    done[platform] = 'registered';
  }
  return json(done);
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    if (url.pathname === '/health' && request.method === 'GET') return json({ ok: true, service: 'alice-bot' });
    if (url.pathname === '/ops/install' && request.method === 'POST') {
      try { return await install(env, request); } catch { return json({ error: 'Registration failed' }, 502); }
    }
    const platform = url.pathname === '/webhook/telegram' ? 'telegram' : url.pathname.startsWith('/webhook/bale/') ? 'bale' : null;
    if (!platform || request.method !== 'POST') return json({ error: 'Not found' }, 404);
    if (platform === 'telegram' && (!env.TELEGRAM_WEBHOOK_SECRET || request.headers.get('x-telegram-bot-api-secret-token') !== env.TELEGRAM_WEBHOOK_SECRET)) return json({ error: 'Forbidden' }, 403);
    if (platform === 'bale' && (!env.BALE_WEBHOOK_SECRET || url.pathname !== `/webhook/bale/${env.BALE_WEBHOOK_SECRET}`)) return json({ error: 'Forbidden' }, 403);
    if (Number(request.headers.get('content-length') || 0) > 262144) return json({ error: 'Too large' }, 413);
    try {
      const update = await request.json();
      await handleUpdate(env, platform, update);
      ctx.waitUntil(drain(env, 4));
      return json({ ok: true });
    } catch { return json({ error: 'Update failed' }, 500); }
  },
  async scheduled(_event, env) {
    await env.DB.prepare("UPDATE outbox SET status='unknown' WHERE status='sending' AND created < datetime('now','-5 minutes')").run();
    await drain(env, 48);
  },
};

export { handleUpdate, drain };
