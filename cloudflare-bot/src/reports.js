const fa = n => Number(n).toLocaleString('fa-IR');
const platformName = p => p === 'bale' ? 'بله' : 'تلگرام';
const emptyCounts = () => ({ total: 0, sent: 0, failed: 0, pending: 0, unknown: 0 });

export function reportTime(created) {
  const date = new Date(created?.endsWith('Z') ? created : String(created).replace(' ', 'T') + 'Z');
  if (!Number.isFinite(date.getTime())) return 'زمان ثبت نشده';
  return new Intl.DateTimeFormat('fa-IR', { timeZone: 'Asia/Tehran', dateStyle: 'medium', timeStyle: 'short' }).format(date);
}

export async function readCampaignReport(db, id) {
  const campaign = await db.prepare('SELECT id,created,source_platform FROM campaigns WHERE id=?').bind(id).first();
  if (!campaign) return null;
  const [counts, sample, errors] = await Promise.all([
    db.prepare(`SELECT o.platform, CASE WHEN o.destination=0 THEN 'members'
      WHEN d.kind='channel' THEN 'channels' ELSE 'groups' END audience, o.status, COUNT(*) n
      FROM outbox o LEFT JOIN destinations d ON d.platform=o.platform AND d.chat=o.chat
      WHERE o.campaign=? GROUP BY o.platform,audience,o.status`).bind(id).all(),
    db.prepare('SELECT method,payload FROM outbox WHERE campaign=? ORDER BY id LIMIT 1').bind(id).first(),
    db.prepare(`SELECT o.platform,o.destination,o.status,
      CASE WHEN o.destination=1 THEN COALESCE(d.title,'گروه یا کانال') ELSE '' END title,
      e.reason,COUNT(*) n FROM outbox o
      LEFT JOIN destinations d ON d.platform=o.platform AND d.chat=o.chat
      LEFT JOIN delivery_errors e ON e.outbox_id=o.id
      WHERE o.campaign=? AND o.status IN ('failed','unknown')
      GROUP BY o.platform,o.destination,o.status,title,e.reason ORDER BY o.destination DESC,o.platform LIMIT 6`).bind(id).all(),
  ]);
  const total = emptyCounts();
  const platforms = ['telegram','bale'].map(platform => ({ platform, ...emptyCounts(), members:emptyCounts(), groups:emptyCounts(), channels:emptyCounts() }));
  for (const row of counts.results || []) {
    const p = platforms.find(p => p.platform === row.platform);
    if (!p) continue;
    const status = ['pending','sending'].includes(row.status) ? 'pending' : ['sent','failed'].includes(row.status) ? row.status : 'unknown';
    const n = Number(row.n);
    for (const item of [total,p,p[row.audience]]) { item.total += n; item[status] += n; }
  }
  let payload = {};
  try { payload = JSON.parse(sample?.payload || '{}'); } catch { /* Legacy invalid payloads still get a report. */ }
  const preview = String(payload.text || payload.caption || '').replace(/\s+/g,' ').slice(0,140);
  return { id:campaign.id, created:campaign.created, timeLabel:reportTime(campaign.created),
    sourcePlatform:campaign.source_platform, preview,
    media:sample?.method === 'sendVideo' ? 'ویدئو' : sample?.method === 'sendPhoto' ? 'عکس' : 'متن',
    status:!total.total ? 'empty' : total.pending ? 'sending' : total.failed || total.unknown ? 'attention' : 'complete',
    total, platforms, errors:(errors.results || []).map(e=>({...e,title:String(e.title||'').slice(0,60),reason:String(e.reason || (e.status==='unknown'?'نتیجهٔ ارسال مشخص نیست؛ برای جلوگیری از پیام تکراری خودکار تکرار نشد.':'پیام‌رسان ارسال را نپذیرفت.')).slice(0,170)})),
  };
}

export async function recentCampaignReports(db, limit=10) {
  const rows = await db.prepare('SELECT id FROM campaigns ORDER BY id DESC LIMIT ?').bind(limit).all();
  return (await Promise.all((rows.results || []).map(r=>readCampaignReport(db,r.id)))).filter(Boolean);
}

export function formatCampaignReport(report) {
  if (!report) return 'هنوز ارسال همگانی ثبت نشده است.';
  const lines = [report.total.pending ? 'ارسال در حال انجام است.' : report.total.total ? 'ارسال پایان یافت.' : 'برای این ارسال مقصدی ثبت نشده است.',
    `گزارش پیام شمارهٔ ${fa(report.id)}`, `زمان: ${report.timeLabel} (تهران)`,
    `${report.media}: ${report.preview || 'بدون کپشن'}`, '',
    `در مجموع: ${fa(report.total.sent)} ارسال موفق از ${fa(report.total.total)} مقصد`,
  ];
  for (const p of report.platforms) {
    lines.push('',platformName(p.platform));
    if (!p.total) { lines.push('در این پیام‌رسان مقصدی انتخاب نشده بود.'); continue; }
    for (const [key,title] of [['members','اعضای بات'],['groups','گروه‌ها'],['channels','کانال‌ها']]) {
      const c=p[key];
      if (!c.total) continue;
      const parts=[`${fa(c.sent)} موفق`];
      if(c.failed) parts.push(`${fa(c.failed)} ناموفق`);
      if(c.pending) parts.push(`${fa(c.pending)} در انتظار یا در حال ارسال`);
      if(c.unknown) parts.push(`${fa(c.unknown)} با نتیجهٔ نامشخص`);
      lines.push(`${title} (${fa(c.total)}): ${parts.join('، ')}`);
    }
  }
  if(report.errors.length) {
    lines.push('','موارد نیازمند بررسی:');
    for(const e of report.errors) lines.push(`• ${platformName(e.platform)} · ${e.destination ? e.title : 'اعضای بات'} (${fa(e.n)}): ${e.reason}`);
  }
  if(report.total.pending) lines.push('','ارسال ادامه دارد؛ نتیجهٔ نهایی همین‌جا اعلام می‌شود.');
  lines.push('','موفق یعنی پیام‌رسان ارسال را پذیرفته است؛ به معنی خوانده‌شدن پیام نیست.');
  if(report.platforms.some(p=>p.groups.total || p.channels.total)) lines.push('هر گروه یا کانال یک مقصد شمرده می‌شود، نه تعداد افراد داخل آن.');
  return lines.join('\n');
}
