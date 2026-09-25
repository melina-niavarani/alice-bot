export const platforms = {
  telegram: { api: 'https://api.telegram.org', owner: 'TELEGRAM_OWNER_ID', token: 'TELEGRAM_BOT_TOKEN' },
  bale: { api: 'https://tapi.bale.ai', owner: 'BALE_OWNER_ID', token: 'BALE_BOT_TOKEN' },
};

export const menuLabels = new Set(['بدنسازی', 'استخر و سونا', 'نشانی مجموعه', 'بازگشت', 'مدیریت ارسال', 'ارسال همگانی', 'گزارش ارسال', 'مقصدهای ارسال']);
export const audienceButtons = [
  ['ارسال به همهٔ اعضا و گروه‌ها'],
  ['ارسال فقط به اعضای بات'],
  ['ارسال به همهٔ گروه‌ها و کانال‌ها'],
  ['انتخاب گروه‌ها و کانال‌ها'],
  ['تغییر پیام', 'لغو ارسال'],
];

export function miniappUrl(env, platform) {
  const raw = String(env.MINIAPP_URL || '');
  if (!raw.startsWith('https://')) return '';
  const url = new URL(raw);
  if (platform === 'bale') url.searchParams.set('platform', 'bale');
  return url.toString();
}

export function menu(env, platform, chat) {
  const rows = [['بدنسازی', 'استخر و سونا'], ['نشانی مجموعه']];
  const url = miniappUrl(env, platform);
  if (url) rows.push([{ text: 'ورود به مجموعه آلیس 🌿', web_app: { url } }]);
  if (String(chat) === String(env[platforms[platform].owner])) rows.push(['مدیریت ارسال', 'ارسال همگانی']);
  return rows;
}

export const copy = {
  welcome: 'به مجموعه ورزشی آلیس خوش آمدی 🌿\nبرای دیدن خدمات، سانس‌ها و تعرفه‌ها وارد آلیس شو.',
  gym: '🏋️ بدنسازی آلیس\n\nهر روز:\nبانوان: ۸:۰۰ تا ۱۶:۰۰\nآقایان: ۱۶:۰۰ تا ۲۳:۰۰\n\nبرای دیدن تعرفه‌ها، کلید «ورود به مجموعه آلیس 🌿» را بزنید.',
  pool: '🏊 استخر و سونای آلیس\n\nشنبه: بانوان ۹:۰۰ تا ۲۲:۰۰\nیکشنبه، سه‌شنبه، پنجشنبه: بانوان ۹:۰۰ تا ۱۶:۰۰؛ آقایان ۱۶:۰۰ تا ۲۳:۰۰\nدوشنبه، چهارشنبه: بانوان ۹:۰۰ تا ۱۵:۰۰؛ آقایان ۱۵:۰۰ تا ۲۳:۰۰\nجمعه: آقایان ۹:۰۰ تا ۲۳:۰۰\n\nورودی استخر: ۸۰۰٬۰۰۰ تومان\n\nبرای دیدن تعرفه‌های آموزش شنا، کلید «ورود به مجموعه آلیس 🌿» را بزنید.',
  address: '📍 تهران، تهرانپارس، خیابان شهید ملکی، نبش خیابان ۱۲۰، پلاک ۶',
};
