import { miniappUrl, platforms } from './config.js';
import { adminMenu, campaignSummary, handleUpdate } from './flow.js';

const now = () => Math.floor(Date.now() / 1000);
const json = (body, status = 200) => Response.json(body, { status, headers: { 'Cache-Control': 'no-store' } });
const parse = value => { try { return JSON.parse(value); } catch { return null; } };

async function api(env, platform, method, payload = {}, signal = AbortSignal.timeout(12000)) {
  const token = env[platforms[platform].token];
  if (!token) throw new Error('BOT_TOKEN_MISSING');
  const response = await fetch(`${platforms[platform].api}/bot${token}/${method}`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload), signal,
  });
  const result = await response.json().catch(() => null);
  if (!result?.ok) {
    const error = new Error(`API_${result?.error_code || response.status}`);
    error.status = Number(result?.error_code || response.status);
    error.retryAfter = Number(result?.parameters?.retry_after || 0);
    error.notModified = /message is not modified/i.test(result?.description || '');
    throw error;
  }
  return result.result;
}

async function setTelegramMenu(env, chat) {
  const url = miniappUrl(env, 'telegram');
  if (!url) return;
  const payload = { menu_button: { type: 'web_app', text: 'ورود به آلیس', web_app: { url } } };
  if (chat != null) payload.chat_id = Number(chat);
  await api(env, 'telegram', 'setChatMenuButton', payload);
}

async function transferMedia(env, targetPlatform, outbound, signal) {
  const source = outbound._media_source;
  const field = outbound.method === 'sendVideo' ? 'video' : 'photo';
  const sourceToken = env[platforms[source].token];
  const info = await api(env, source, 'getFile', { file_id: outbound[field] }, signal);
  const path = String(info?.file_path || '');
  if (!path || path.startsWith('/') || path.split('/').includes('..')) throw new Error('INVALID_FILE_PATH');
  const file = await fetch(`${platforms[source].api}/file/bot${sourceToken}/${path}`, { signal });
  if (!file.ok) throw new Error(`FILE_${file.status}`);
  const bytes = await file.arrayBuffer();
  if (bytes.byteLength > 20 * 1024 * 1024) throw new Error('FILE_TOO_LARGE');
  const form = new FormData();
  form.set('chat_id', String(outbound.chat_id));
  if (outbound.caption) form.set('caption', outbound.caption);
  form.set(field, new Blob([bytes], { type: field === 'video' ? 'video/mp4' : 'image/jpeg' }), field === 'video' ? 'video.mp4' : 'photo.jpg');
  const token = env[platforms[targetPlatform].token];
  const response = await fetch(`${platforms[targetPlatform].api}/bot${token}/${outbound.method}`, { method: 'POST', body: form, signal });
  const result = await response.json().catch(() => null);
  if (!result?.ok) {
    const error = new Error(`API_${result?.error_code || response.status}`);
    error.status = Number(result?.error_code || response.status);
    error.retryAfter = Number(result?.parameters?.retry_after || 0);
    error.notModified = /message is not modified/i.test(result?.description || '');
    throw error;
  }
}

function failureReason(status) {
  if (status === 403) return 'بات مسدود است یا اجازهٔ ارسال در این مقصد را ندارد.';
  if (status === 400 || status === 404) return 'مقصد یا فایل در دسترس نیست؛ دسترسی بات را بررسی کن.';
  if (status === 429) return 'محدودیت موقت پیام‌رسان؛ مهلت تلاش دوباره تمام شد.';
  return 'ارتباط قطع شد و تحویل قطعی مشخص نیست؛ برای جلوگیری از تکرار، خودکار دوباره ارسال نشد.';
}

async function deliver(env, row, signal) {
  const payload = parse(row.payload) || {};
  const outbound = { ...payload, chat_id: row.chat };
  delete outbound.method;
  const source = outbound._media_source;
  delete outbound._media_source;
  try {
    if (source) await transferMedia(env, row.platform, { ...outbound, method: row.method, _media_source: source }, signal);
    else await api(env, row.platform, row.method, outbound, signal);
    await env.DB.prepare("UPDATE outbox SET status='sent' WHERE id=?").bind(row.id).run();
  } catch (error) {
    const status = Number(error?.status || 0);
    if (row.method === 'editMessageText' && error.notModified) {
      await env.DB.prepare("UPDATE outbox SET status='sent' WHERE id=?").bind(row.id).run(); return;
    }
    // If the selector was deleted / can no longer be edited, send a fresh one.
    if (row.method === 'editMessageText' && status === 400) {
      delete payload.message_id;
      await env.DB.prepare("UPDATE outbox SET method='sendMessage',payload=?,status='pending',due=0 WHERE id=?").bind(JSON.stringify(payload),row.id).run(); return;
    }
    const retry = status === 429 && row.attempts < 8;
    const state = retry ? 'pending' : status >= 400 && status < 500 ? 'failed' : 'unknown';
    await env.DB.batch([
      env.DB.prepare('UPDATE outbox SET status=?,due=? WHERE id=?').bind(state,retry ? now()+Math.max(1,Number(error.retryAfter||30)):0,row.id),
      env.DB.prepare('INSERT INTO delivery_errors(outbox_id,reason) VALUES (?,?) ON CONFLICT(outbox_id) DO UPDATE SET reason=excluded.reason').bind(row.id,failureReason(status)),
    ]);
    // A blocked account is inactive; it did not explicitly opt out of news.
    if (status === 403 && !row.destination && row.method.startsWith('send')) await env.DB.prepare('UPDATE members SET subscribed=0 WHERE platform=? AND chat=?').bind(row.platform,row.chat).run();
    console.warn(JSON.stringify({event:'delivery_error',platform:row.platform,outbox:row.id,status:state,code:status}));
  }
}

async function finishCampaigns(env) {
  const finished = (await env.DB.prepare(`SELECT c.id,c.source_platform,c.owner FROM campaigns c JOIN campaign_meta m ON m.campaign=c.id
    WHERE m.notified=0 AND NOT EXISTS (SELECT 1 FROM outbox o WHERE o.campaign=c.id AND o.status IN ('pending','sending'))`).all()).results || [];
  for (const c of finished) {
    let text = 'ارسال پایان یافت.\n'+await campaignSummary(env.DB,c.id);
    const errors=(await env.DB.prepare(`SELECT DISTINCT o.platform,o.destination,d.title,e.reason FROM outbox o
      LEFT JOIN destinations d ON d.platform=o.platform AND d.chat=o.chat
      LEFT JOIN delivery_errors e ON e.outbox_id=o.id WHERE o.campaign=? AND o.status IN ('failed','unknown') LIMIT 5`).bind(c.id).all()).results||[];
    if(errors.length) text+='\n\n'+errors.map(e=>`${e.platform==='bale'?'بله':'تلگرام'}${e.destination?' · '+(e.title||'گروه/کانال'):''}: ${e.reason||'نتیجهٔ تحویل مشخص نیست؛ مقصد را بررسی کن.'}`).join('\n');
    await env.DB.batch([
      env.DB.prepare(`INSERT INTO outbox(platform,chat,method,payload) SELECT ?,?,'sendMessage',? FROM campaign_meta WHERE campaign=? AND notified=0`)
        .bind(c.source_platform,c.owner,JSON.stringify({text,reply_markup:{keyboard:adminMenu,resize_keyboard:true}}),c.id),
      env.DB.prepare('UPDATE campaign_meta SET notified=1 WHERE campaign=? AND notified=0').bind(c.id),
    ]);
  }
}

async function drain(env, limit = 8, options = {}) {
  const lease=crypto.randomUUID(), start=Date.now(), budget=options.budget || 25000;
  const claimed=await env.DB.prepare('UPDATE delivery_lock SET owner=?,expires=? WHERE id=1 AND expires<=?').bind(lease,now()+90,now()).run();
  if(!claimed.meta.changes) return;
  try {
    await env.DB.prepare("UPDATE outbox SET status='unknown' WHERE status='sending' AND due<?").bind(now()-90).run();
    for(let i=0;i<limit && Date.now()-start<budget-2000;i++) {
      await finishCampaigns(env);
      // Control messages have priority; a large broadcast cannot hide the menu.
      const row=await env.DB.prepare("SELECT * FROM outbox WHERE status='pending' AND due<=? ORDER BY (campaign IS NOT NULL),id LIMIT 1").bind(now()).first();
      if(!row) break;
      await env.DB.prepare('UPDATE delivery_lock SET expires=? WHERE id=1 AND owner=?').bind(now()+90,lease).run();
      const sent=await env.DB.prepare("UPDATE outbox SET status='sending',attempts=attempts+1,due=? WHERE id=? AND status='pending'").bind(now(),row.id).run();
      if(!sent.meta.changes) continue;
      await deliver(env,{...row,attempts:row.attempts+1},AbortSignal.timeout(Math.max(1000,budget-(Date.now()-start)-1000)));
      if(i+1<limit) await new Promise(resolve=>setTimeout(resolve,options.pauseMs ?? 1100));
    }
    await finishCampaigns(env);
  } finally {
    await env.DB.prepare('UPDATE delivery_lock SET expires=0 WHERE id=1 AND owner=?').bind(lease).run();
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
      payload.allowed_updates = ['message', 'channel_post', 'my_chat_member', 'callback_query'];
    }
    await api(env, platform, 'setWebhook', payload);
    if (platform === 'telegram') await setTelegramMenu(env);
    done[platform] = 'registered';
  }
  const members = await env.DB.prepare("SELECT chat FROM members WHERE platform='telegram'").all();
  const chats = new Set([String(env.TELEGRAM_OWNER_ID), ...(members.results || []).map(row => String(row.chat))]);
  let menusUpdated = 0;
  for (const chat of chats) {
    try { await setTelegramMenu(env, chat); menusUpdated++; } catch { /* The user may have blocked the bot. */ }
  }
  done.telegramMenusUpdated = menusUpdated;
  return json(done);
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    if (url.pathname === '/health' && request.method === 'GET') return json({ ok: true, service: 'alice-bot', version: 'broadcast-v2' });
    if (url.pathname === '/ops/menu' && request.method === 'GET') {
      if (!env.SETUP_SECRET || request.headers.get('authorization') !== `Bearer ${env.SETUP_SECRET}`) return json({ error: 'Unauthorized' }, 401);
      try {
        const [defaultMenu, ownerMenu] = await Promise.all([
          api(env, 'telegram', 'getChatMenuButton'),
          api(env, 'telegram', 'getChatMenuButton', { chat_id: Number(env.TELEGRAM_OWNER_ID) }),
        ]);
        return json({ defaultMenu, ownerMenu });
      } catch { return json({ error: 'Menu lookup failed' }, 502); }
    }
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
      const feedback = await handleUpdate(env, platform, update);
      if (update.callback_query?.id) ctx.waitUntil(api(env,platform,'answerCallbackQuery',{
        callback_query_id:update.callback_query.id,text:feedback || '',show_alert:Boolean(feedback && feedback.length>40),
      }).catch(()=>{}));
      ctx.waitUntil(drain(env, 4));
      return json({ ok: true });
    } catch (error) {
      console.error(JSON.stringify({event:'update_failed',platform,kind:error?.message==='UPDATE_CONFLICT'?'conflict':'processing'}));
      return json({ error: 'Update failed' }, 500);
    }
  },
  async scheduled(_event, env) {
    await drain(env,48,{budget:50000});
  },
};

export { handleUpdate, drain };
