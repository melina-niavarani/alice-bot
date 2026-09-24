"""Alice Telegram/Bale bot. Python 3.8+, standard library only."""
import base64
import contextlib
import hmac
import html
import json
import logging
import os
from pathlib import Path
import re
import secrets
import sqlite3
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs
from urllib.request import Request, urlopen
import miniapp_manager
import broadcast

ROOT = Path(__file__).resolve().parent
MENU = [["بدنسازی", "استخر و سونا"], ["نشانی مجموعه"]]
BACK = "بازگشت"


def load_env():
    path = ROOT / ".env"
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip() and not line.lstrip().startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def phone_number(text):
    text = text.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))
    text = re.sub(r"[\s()\-]", "", text)
    if text.startswith("+98"):
        text = "0" + text[3:]
    elif text.startswith("0098"):
        text = "0" + text[4:]
    elif text.startswith("98"):
        text = "0" + text[2:]
    return text if re.fullmatch(r"09[0-9]{9}", text) else None


class APIError(Exception):
    def __init__(self, code=0, retry_after=0, uncertain=False):
        super().__init__("API failure %s" % code)  # Never include token-bearing URLs.
        self.code, self.retry_after, self.uncertain = code, retry_after, uncertain


class API:
    HOSTS = {"telegram": "https://api.telegram.org", "bale": "https://tapi.bale.ai"}

    def __init__(self, platform, token):
        self.platform = platform
        self.file_base = self.HOSTS[platform] + "/file/bot" + token + "/"
        self.base = self.HOSTS[platform] + "/bot" + token + "/"

    def call(self, method, **data):
        request = Request(self.base + method, json.dumps(data).encode(),
                          {"Content-Type": "application/json"})
        return self._request(request)

    def _request(self, request):
        try:
            with urlopen(request, timeout=40) as response:
                result = json.load(response)
        except HTTPError as exc:
            try:
                result = json.loads(exc.read())
            except (ValueError, OSError):
                raise APIError(exc.code, uncertain=exc.code >= 500) from None
        except (URLError, OSError, ValueError):
            raise APIError(uncertain=True) from None
        if not isinstance(result, dict):
            raise APIError(uncertain=True)
        if not result.get("ok"):
            code = int(result.get("error_code", 0))
            raise APIError(code, result.get("parameters", {}).get("retry_after", 0), code >= 500)
        return result.get("result")


    def download_file(self, file_id, max_bytes=10 * 1024 * 1024):
        info = self.call('getFile', file_id=file_id)
        path = info.get('file_path', '')
        if not path or path.startswith('/') or ':' in path or '..' in path.split('/'):
            raise APIError(400)
        try:
            with urlopen(self.file_base + path, timeout=40) as response:
                content = response.read(max_bytes + 1)
        except (URLError, OSError, ValueError):
            raise APIError(502) from None
        if not content or len(content) > max_bytes:
            raise APIError(413)
        return content

    def download_photo(self, file_id):
        return self.download_file(file_id)

    def download_video(self, file_id):
        return self.download_file(file_id, 20 * 1024 * 1024)

    def upload_media(self, method, field, filename, content_type, content, **data):
        boundary = 'Alice' + secrets.token_hex(16)
        chunks = []
        for name, value in data.items():
            value = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
            chunks.append(('--' + boundary + '\r\nContent-Disposition: form-data; name="' + name + '"\r\n\r\n' + value + '\r\n').encode())
        chunks.append(('--' + boundary + '\r\nContent-Disposition: form-data; name="' + field + '"; filename="' + filename + '"\r\nContent-Type: ' + content_type + '\r\n\r\n').encode())
        chunks.extend([content, ('\r\n--' + boundary + '--\r\n').encode()])
        return self._request(Request(self.base + method, b''.join(chunks),
                            {'Content-Type': 'multipart/form-data; boundary=' + boundary}))

    def upload_photo(self, content, **data):
        return self.upload_media('sendPhoto', 'photo', 'photo.jpg', 'image/jpeg', content, **data)

    def upload_video(self, content, **data):
        return self.upload_media('sendVideo', 'video', 'video.mp4', 'video/mp4', content, **data)


class Store:
    def __init__(self, path, config):
        self.path, self.config = str(path), config
        with self.db() as db:
            db.executescript('''
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS members (
                    platform TEXT, chat INTEGER, name TEXT, subscribed INTEGER DEFAULT 0,
                    interest TEXT DEFAULT '', state TEXT DEFAULT '', pending TEXT DEFAULT '',
                    referral TEXT UNIQUE, referred_by TEXT DEFAULT '', created TEXT DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY(platform,chat));
                CREATE TABLE IF NOT EXISTS leads (
                    id INTEGER PRIMARY KEY, platform TEXT, chat INTEGER, name TEXT, phone TEXT,
                    interest TEXT, status TEXT DEFAULT 'new', created TEXT DEFAULT CURRENT_TIMESTAMP);
                CREATE TABLE IF NOT EXISTS offsets (platform TEXT PRIMARY KEY, value INTEGER);
                CREATE TABLE IF NOT EXISTS campaigns (
                    id INTEGER PRIMARY KEY, body TEXT, segment TEXT, status TEXT DEFAULT 'draft',
                    created TEXT DEFAULT CURRENT_TIMESTAMP);
                CREATE TABLE IF NOT EXISTS outbox (
                    id INTEGER PRIMARY KEY, platform TEXT, chat INTEGER, body TEXT, markup TEXT,
                    campaign INTEGER, status TEXT DEFAULT 'pending', due REAL DEFAULT 0,
                    attempts INTEGER DEFAULT 0, created TEXT DEFAULT CURRENT_TIMESTAMP);
                CREATE INDEX IF NOT EXISTS outbox_pending ON outbox(platform,status,due);
            ''')

            columns = {r[1] for r in db.execute("PRAGMA table_info(members)")}
            if "news_opt_out" not in columns:
                db.execute("ALTER TABLE members ADD COLUMN news_opt_out INTEGER DEFAULT 0")
                # Legacy inactive records may include explicit opt-outs; preserve them.
                db.execute("UPDATE members SET news_opt_out=1 WHERE subscribed=0")
            broadcast.setup(db)

    @contextlib.contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=20)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def recover(self):
        # Sending may have succeeded before a crash; never automatically duplicate it.
        with self.db() as db:
            db.execute("UPDATE outbox SET status='unknown' WHERE status='sending'")

    def queue(self, db, platform, chat, body, keyboard=MENU, campaign=None):
        miniapp_url = os.environ.get("MINIAPP_URL", "").strip()
        if platform == "telegram" and keyboard is MENU and miniapp_url.startswith("https://"):
            keyboard = [["بدنسازی", "استخر و سونا"], ["نشانی مجموعه"], [{"text": "ورود به مجموعه آلیس 🌿", "web_app": {"url": miniapp_url}}]]
            if chat == broadcast.OWNER:
                keyboard.append(["مدیریت ارسال", "ارسال همگانی"])
        if platform == "bale" and keyboard is MENU:
            keyboard = [list(row) for row in MENU]
            if miniapp_url.startswith("https://"):
                from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
                parts = urlsplit(miniapp_url)
                query = dict(parse_qsl(parts.query)); query["platform"] = "bale"
                bale_url = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))
                keyboard.append([{"text": "ورود به مجموعه آلیس 🌿", "web_app": {"url": bale_url}}])
            if chat == broadcast.OWNERS["bale"]:
                keyboard.append(["مدیریت ارسال", "ارسال همگانی"])
        markup = {"keyboard": keyboard, "resize_keyboard": True} if keyboard else {"remove_keyboard": True}
        db.execute("INSERT INTO outbox(platform,chat,body,markup,campaign) VALUES (?,?,?,?,?)",
                   (platform, chat, body, json.dumps(markup, ensure_ascii=False), campaign))

    def handle(self, platform, update):
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            uid = update["update_id"]
            previous = db.execute("SELECT value FROM offsets WHERE platform=?", (platform,)).fetchone()
            if previous and uid < previous[0]:
                return
            broadcast.observe_group(self, db, platform, update)
            msg = update.get("message", {})
            chat = msg.get("chat", {})
            if broadcast.handle(self, db, platform, msg):
                pass
            elif chat.get("type") == "private" and msg.get("from", {}).get("id") == chat.get("id"):
                self._message(db, platform, msg)
            db.execute("INSERT OR REPLACE INTO offsets VALUES (?,?)", (platform, uid + 1))

    def _message(self, db, platform, msg):
        chat = msg["chat"]["id"]
        text = msg.get("text", "").strip()
        name = msg.get("from", {}).get("first_name", "عضو آلیس")[:100]
        db.execute("INSERT OR IGNORE INTO members(platform,chat,name,referral) VALUES (?,?,?,?)",
                   (platform, chat, name, secrets.token_hex(5)))
        member = db.execute("SELECT * FROM members WHERE platform=? AND chat=?", (platform, chat)).fetchone()

        def say(body, keyboard=MENU):
            self.queue(db, platform, chat, body, keyboard)

        def state(value="", pending=""):
            db.execute("UPDATE members SET state=?,pending=? WHERE platform=? AND chat=?",
                       (value, pending, platform, chat))

        # Clear unfinished flows from the retired contact/referral features.
        if member["state"] in ("phone", "confirm_phone", "referral"):
            state()

        command = text.split(" ", 1)[0].split("@")[0]
        if command == "/myid":
            label = "بله" if platform == "bale" else "تلگرام"
            say("شناسه عددی حساب تو در " + label + ":\n" + str(msg["from"]["id"]) + "\nاین شناسه به‌تنهایی دسترسی مدیریت ایجاد نمی‌کند.")
        elif command == "/start" or text in (BACK, "/cancel", "/menu", "تنظیم خبرها"):
            state()
            if command == "/start" and not member["news_opt_out"]:
                db.execute("UPDATE members SET subscribed=1 WHERE platform=? AND chat=?", (platform, chat))
            active = db.execute("SELECT subscribed FROM members WHERE platform=? AND chat=?", (platform, chat)).fetchone()[0]
            note = "خبرها و پیشنهادهای آلیس همین‌جا می‌آیند. توقف دریافت: /stop" if active else "دریافت خبرها غیرفعال است. برای فعال‌کردن دوباره /subscribe را بفرست."
            say(self.config["welcome"] + "\n" + note)
        elif text in ("لغو خبرها", "توقف خبرها", "/stop"):
            db.execute("UPDATE members SET subscribed=0,news_opt_out=1 WHERE platform=? AND chat=?", (platform, chat))
            state()
            say("دریافت پیام‌های خصوصی خبرها متوقف شد.")
        elif text in ("درخواست تماس", "تأیید درخواست تماس", "معرفی دوستان", "ثبت کد معرف", "خبر بازگشایی"):
            state()
            say("منوی آلیس به‌روز شده است. خدمات موردنظرت را از منوی زیر انتخاب کن.")
        elif text in ("عضویت در خبرها", "/subscribe"):
            state()
            db.execute("UPDATE members SET subscribed=1,news_opt_out=0 WHERE platform=? AND chat=?", (platform, chat))
            say("دریافت خبرهای خصوصی فعال شد. برای توقف دریافت، /stop را بفرست.")
        elif text == "علاقه‌مندی‌ها":
            state("interest")
            say("موضوع مورد علاقه‌ات را انتخاب کن.", [[item] for item in self.config["interests"]] + [[BACK]])
        elif member["state"] == "interest" and text in self.config["interests"]:
            db.execute("UPDATE members SET interest=? WHERE platform=? AND chat=?", (text, platform, chat))
            state()
            say("علاقه‌مندی تو ثبت شد: " + text)
        elif text in ("بدنسازی", "استخر و سونا", "نشانی مجموعه", "نشانی و تماس", "خدمات و تعرفه‌ها", "کلاس‌ها و تعرفه‌ها", "پیشنهاد ویژه"):
            state()
            field = {"بدنسازی": "gym", "استخر و سونا": "pool", "نشانی مجموعه": "address", "نشانی و تماس": "address",
                     "خدمات و تعرفه‌ها": "classes", "کلاس‌ها و تعرفه‌ها": "classes", "پیشنهاد ویژه": "offer"}[text]
            say(self.config[field])
        else:
            state()
            say("به آلیس خوش آمدی. خدمات موردنظرت را از منوی زیر انتخاب کن.")

    def create_campaign(self, body, segment):
        if not body.strip() or len(body) > 3000 or segment not in ["all"] + self.config["interests"]:
            raise ValueError("متن باید بین ۱ تا ۳۰۰۰ نویسه و گروه مخاطب معتبر باشد.")
        with self.db() as db:
            return db.execute("INSERT INTO campaigns(body,segment) VALUES (?,?)", (body.strip(), segment)).lastrowid

    def audience(self, db, segment):
        return db.execute("SELECT * FROM members WHERE subscribed=1 AND (?='all' OR interest=? OR interest='همه خدمات')", (segment, segment)).fetchall()

    def confirm_campaign(self, ident):
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            campaign = db.execute("SELECT * FROM campaigns WHERE id=?", (ident,)).fetchone()
            if not campaign or campaign["status"] != "draft":
                return False
            for member in self.audience(db, campaign["segment"]):
                self.queue(db, member["platform"], member["chat"],
                           campaign["body"] + "\n\nتوقف دریافت خبرها: /stop", campaign=ident)
            db.execute("UPDATE campaigns SET status='queued' WHERE id=?", (ident,))
            return True

    def deliver_one(self, platform, api):
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM outbox WHERE platform=? AND status='pending' AND due<=? ORDER BY campaign IS NOT NULL,id LIMIT 1",
                             (platform, time.time())).fetchone()
            if not row:
                return False
            if row["campaign"]:
                campaign = db.execute("SELECT segment FROM campaigns WHERE id=?", (row["campaign"],)).fetchone()
                member = db.execute("SELECT subscribed,interest FROM members WHERE platform=? AND chat=?", (platform, row["chat"])).fetchone()
                group = db.execute("SELECT active FROM " + broadcast.destination_table(platform) + " WHERE chat=?", (row["chat"],)).fetchone() if row["destination"] else None
                invalid = (not group or not group[0]) if row["destination"] else (not member or not member["subscribed"] or (campaign[0] != "all" and member["interest"] not in (campaign[0], "همه خدمات")))
                if invalid:
                    db.execute("UPDATE outbox SET status='skipped' WHERE id=?", (row["id"],))
                    return True
            db.execute("UPDATE outbox SET status='sending',attempts=attempts+1 WHERE id=?", (row["id"],))
        status, due = "sent", 0
        try:
            payload = json.loads(row["payload"] or "{}")
            if not payload:
                payload = {"text": row["body"]}
            markup = json.loads(row["markup"] or "{}")
            if markup:
                payload["reply_markup"] = markup
            source = payload.pop('_media_source', None) or payload.pop('_photo_source', None)
            if source:
                token = os.environ.get(source.upper() + '_BOT_TOKEN') if source in API.HOSTS else None
                if not token:
                    raise APIError(400)
                # Never share the source token/download URL with the other platform.
                try:
                    if row['method'] == 'sendVideo':
                        media = API(source, token).download_video(payload.pop('video'))
                    else:
                        media = API(source, token).download_photo(payload.pop('photo'))
                except APIError as exc:
                    raise APIError(exc.code, exc.retry_after, uncertain=False) from None
                if row['method'] == 'sendVideo':
                    api.upload_video(media, chat_id=row["chat"], **payload)
                else:
                    api.upload_photo(media, chat_id=row["chat"], **payload)
            else:
                api.call(row["method"] or "sendMessage", chat_id=row["chat"], **payload)
        except APIError as exc:
            if exc.code == 429 and row["attempts"] < 8:
                status, due = "pending", time.time() + max(1, int(exc.retry_after or 30))
            else:
                status = "unknown" if exc.uncertain else "failed"
            if exc.code == 403:
                with self.db() as db:
                    db.execute("UPDATE members SET subscribed=0,news_opt_out=1 WHERE platform=? AND chat=?", (platform, row["chat"]))
        with self.db() as db:
            db.execute("UPDATE outbox SET status=?,due=? WHERE id=?", (status, due, row["id"]))
        return True


def poll(store, platform, api, stop, health):
    while not stop.is_set():
        try:
            with store.db() as db:
                row = db.execute("SELECT value FROM offsets WHERE platform=?", (platform,)).fetchone()
            options = {"allowed_updates": ["message", "my_chat_member"]} if platform == "telegram" else {}
            updates = api.call("getUpdates", offset=row[0] if row else 0, timeout=25, limit=50, **options)
            for update in updates or []:
                store.handle(platform, update)
            health[platform] = "متصل"
        except APIError as exc:
            health[platform] = "خطای ارتباط؛ کد %s" % exc.code
            logging.warning("%s polling failed (code %s)", platform, exc.code)
            stop.wait(max(5, min(60, int(exc.retry_after or 5))))
        except Exception as exc:
            health[platform] = "خطای پردازش؛ نیاز به بررسی"
            logging.error("%s processing failed: %s", platform, type(exc).__name__)
            stop.wait(10)


def sender(store, platform, api, stop):
    while not stop.is_set():
        try:
            worked = store.deliver_one(platform, api)
            stop.wait(3.1 if worked else 0.5)
        except Exception as exc:
            logging.error("%s sender failed: %s", platform, type(exc).__name__)
            stop.wait(5)


def connect(store, platform, api, stop, health):
    """Retry transient startup failures without requiring a manual restart."""
    while not stop.is_set():
        try:
            identity = api.call("getMe")
            if api.call("getWebhookInfo").get("url"):
                health[platform] = "وب‌هوک فعال است؛ پیش از اجرای polling بررسی شود"
                return
            store.config.setdefault("bot_ids", {})[platform] = identity.get("id")
            store.config.setdefault("bot_usernames", {})[platform] = identity.get("username", "")
            if platform == "telegram":
                try:
                    description = store.config.get("telegram_description")
                    short_description = store.config.get("telegram_short_description")
                    if description:
                        api.call("setMyDescription", description=description)
                    if short_description:
                        api.call("setMyShortDescription", short_description=short_description)
                    if description or short_description:
                        logging.info("telegram profile descriptions configured")
                except APIError as exc:
                    logging.warning("telegram profile description update failed (code %s)", exc.code)
            if platform == "telegram" and os.environ.get("MINIAPP_URL", "").startswith("https://"):
                api.call("setChatMenuButton", menu_button={"type": "web_app", "text": "ورود به آلیس", "web_app": {"url": os.environ["MINIAPP_URL"]}})
            health[platform] = "متصل"
            logging.info("%s connected: @%s", platform, identity.get("username", ""))
            threading.Thread(target=sender, args=(store, platform, api, stop), daemon=True).start()
            poll(store, platform, api, stop, health)
            return
        except APIError as exc:
            health[platform] = "تلاش مجدد اتصال؛ کد %s" % exc.code
            logging.warning("%s connection failed (code %s); retrying", platform, exc.code)
            stop.wait(max(5, min(60, int(exc.retry_after or 5))))


STYLE = """
body{font:16px Tahoma,Arial,sans-serif;background:#f3f5ef;color:#173c34;margin:0;line-height:1.9}
main{max-width:1040px;margin:auto;padding:32px 20px}h1{margin-bottom:0}h2{font-size:21px}
.card{background:white;border:1px solid #d9e3d9;border-radius:18px;padding:24px;margin:20px 0}
.muted{color:#586c65}.tag{display:inline-block;background:#e8efdf;padding:4px 12px;border-radius:20px;margin:4px}
textarea,select,input{font:inherit;width:100%;box-sizing:border-box;border:1px solid #a6b9ac;border-radius:9px;padding:10px;background:#fff}
textarea{min-height:170px}button,.button{font:inherit;background:#225b48;color:#fff;padding:9px 20px;border:0;border-radius:10px;cursor:pointer;text-decoration:none}
label{display:block;margin:12px 0 5px}table{width:100%;border-collapse:collapse;font-size:14px}td,th{text-align:right;padding:10px;border-bottom:1px solid #e3e9e3}
.scroll{overflow-x:auto}pre{font:inherit;white-space:pre-wrap;overflow-wrap:anywhere}.note{border-right:4px solid #c3994c;padding:12px;background:#fff8e9}a{color:#225b48}
"""


def panel_handler(store, password, health):
    csrf = secrets.token_urlsafe(32)

    class Panel(BaseHTTPRequestHandler):
        server_version = "Alice"

        def log_message(self, *args):
            pass

        def allowed(self):
            # Loopback + strict Host prevent accidental exposure and DNS rebinding.
            hosts = {"127.0.0.1:%s" % self.server.server_port, "localhost:%s" % self.server.server_port}
            if self.headers.get("Host") not in hosts:
                self.send_error(403)
                return False
            expected = "Basic " + base64.b64encode(("admin:" + password).encode()).decode()
            if not hmac.compare_digest(self.headers.get("Authorization", ""), expected):
                self.send_response(401)
                self.send_header("WWW-Authenticate", 'Basic realm="Alice", charset="UTF-8"')
                self.end_headers()
                return False
            return True

        def page(self, content, status=200):
            body = ('<!doctype html><html lang="fa" dir="rtl"><meta charset="utf-8">'
                    '<meta name="viewport" content="width=device-width,initial-scale=1">'
                    '<title>مدیریت آلیس</title><style>' + STYLE + '</style><main>'
                    '<div class="muted">ALICE · شروعی دوباره</div><h1>مدیریت مجموعه ورزشی آلیس</h1>'
                    '<p class="muted">خبرها، درخواست‌های تماس و کمپین‌های تلگرام و بله</p>' + content + '</main></html>').encode()
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; script-src 'nonce-" + csrf + "'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'")
            self.end_headers()
            self.wfile.write(body)

        def token(self):
            return '<input type="hidden" name="csrf" value="' + csrf + '">'

        def do_GET(self):
            if not self.allowed():
                return
            if self.path == "/miniapp":
                self.page(miniapp_manager.editor(csrf))
                return
            if self.path != "/":
                self.send_error(404)
                return
            esc = lambda x: html.escape(str(x))
            with store.db() as db:
                total = db.execute("SELECT COUNT(*) FROM members").fetchone()[0]
                active = db.execute("SELECT COUNT(*) FROM members WHERE subscribed=1").fetchone()[0]
                referrals = db.execute("SELECT COUNT(*) FROM members WHERE referred_by!=''").fetchone()[0]
                lead_count = db.execute("SELECT COUNT(*) FROM leads WHERE status='new'").fetchone()[0]
                leads = db.execute("SELECT * FROM leads ORDER BY id DESC LIMIT 100").fetchall()
                campaigns = db.execute("SELECT * FROM campaigns ORDER BY id DESC LIMIT 20").fetchall()
                content = '<div class="card"><a class="button" href="/miniapp">ویرایش محتوای مینی‌اپ آلیس</a><p>سانس‌ها، تعرفه‌ها، قوانین و اطلاعیه‌ها</p></div><div class="card">' + ''.join('<span class="tag">%s: %s</span>' % (k, v) for k, v in
                    [("کاربران بات", total), ("عضو خبرها", active), ("درخواست جدید", lead_count), ("معرفی ثبت‌شده", referrals)])
                content += '<p>' + ' · '.join(esc(p) + ': ' + esc(s) for p, s in health.items()) + '</p>'
                content += '<small>آمار بر اساس حساب پیام‌رسان است؛ یک فرد در دو پیام‌رسان دو حساب محسوب می‌شود.</small></div>'
                options = '<option value="all">تمام اعضای خبرها</option>' + ''.join('<option>%s</option>' % esc(x) for x in store.config["interests"])
                content += '<section class="card"><h2>خبر تازه‌ای برای آلیس داری؟</h2><form method="post" action="/preview">' + self.token()
                content += '<label>مخاطبان</label><select name="segment">' + options + '</select><label>متن پیام</label>'
                content += '<textarea name="body" required maxlength="3000">' + esc(store.config["reopening"]) + '</textarea><p><button>دیدن پیش‌نمایش</button></p></form></section>'
                content += '<section class="card"><h2>درخواست‌های تماس · ۱۰۰ درخواست اخیر</h2><div class="scroll"><table><tr><th>نام</th><th>موبایل</th><th>مسیر</th><th>علاقه</th><th>پیگیری</th></tr>'
                for lead in leads:
                    action = 'پیگیری شد' if lead["status"] == "done" else '<form method="post" action="/done">' + self.token() + '<input type="hidden" name="id" value="%s"><button>پیگیری شد</button></form>' % lead["id"]
                    content += '<tr><td>%s</td><td dir="ltr">%s</td><td>%s</td><td>%s</td><td>%s</td></tr>' % (esc(lead["name"]), esc(lead["phone"]), esc(lead["platform"]), esc(lead["interest"]), action)
                content += '</table></div></section><section class="card"><h2>کمپین‌ها · ۲۰ مورد اخیر</h2>'
                labels = {"pending": "در صف", "sent": "تحویل API", "failed": "ناموفق", "unknown": "نتیجه نامشخص", "sending": "در حال ارسال", "skipped": "لغو یا تغییر علاقه"}
                for campaign in campaigns:
                    counts = db.execute("SELECT status,COUNT(*) n FROM outbox WHERE campaign=? GROUP BY status", (campaign["id"],)).fetchall()
                    content += '<p><strong>#%s · %s</strong><br>%s<br><small>%s</small></p>' % (campaign["id"], 'پیش‌نویس' if campaign["status"] == 'draft' else 'ارسال تأیید شده', esc(campaign["body"][:150]), ' · '.join(esc(labels.get(c["status"], c["status"])) + ': ' + str(c["n"]) for c in counts))
                content += '<p class="muted">«تحویل API» به معنی خوانده‌شدن پیام نیست. پیام با نتیجه نامشخص، برای جلوگیری از تکرار خودکار دوباره ارسال نمی‌شود.</p></section>'
            self.page(content)

        def do_POST(self):
            if not self.allowed():
                return
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 200000:
                    self.send_error(413)
                    return
                full_form = parse_qs(self.rfile.read(size).decode(), keep_blank_values=True)
                form = {k: v[0] for k, v in full_form.items()}
                if not hmac.compare_digest(form.get("csrf", ""), csrf):
                    self.send_error(403)
                    return
                if self.path == "/miniapp/save":
                    try:
                        content = miniapp_manager.parse_content(full_form)
                    except ValueError as exc:
                        self.page(miniapp_manager.editor(csrf, message=str(exc)), 400)
                        return
                    miniapp_manager.save_content(content)
                    message = miniapp_manager.publish_content(content)
                    self.page(miniapp_manager.editor(csrf, content, message))
                    return
                if self.path == "/preview":
                    ident = store.create_campaign(form.get("body", ""), form.get("segment", ""))
                    with store.db() as db:
                        count = len(store.audience(db, form["segment"]))
                    self.page('<section class="card"><h2>پیش‌نمایش پیام</h2><pre>' + html.escape(form["body"])
                              + '\n\nتوقف دریافت خبرها: /stop</pre><p>مخاطبان فعلی: %s حساب</p>' % count
                              + '<p class="note">با تأیید، این متن در صف ارسال برای اعضای گروه انتخاب‌شده در هر دو پیام‌رسان قرار می‌گیرد.</p>'
                              + '<form method="post" action="/send">' + self.token()
                              + '<input type="hidden" name="id" value="%s"><button>تأیید و ارسال</button></form><p><a href="/">بازگشت بدون ارسال</a></p></section>' % ident)
                    return
                elif self.path == "/send":
                    store.confirm_campaign(int(form["id"]))
                elif self.path == "/done":
                    with store.db() as db:
                        db.execute("UPDATE leads SET status='done' WHERE id=?", (int(form["id"]),))
                else:
                    self.send_error(404)
                    return
            except (ValueError, KeyError, UnicodeDecodeError):
                self.page('<p>اطلاعات فرم معتبر نیست. <a href="/">بازگشت</a></p>', 400)
                return
            self.send_response(303)
            self.send_header("Location", "/")
            self.end_headers()

    return Panel


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Alice Telegram/Bale bot and local admin panel")
    parser.add_argument("--demo", action="store_true", help="Local panel only; no API traffic")
    args = parser.parse_args()
    load_env()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    data = ROOT / "data"
    data.mkdir(mode=0o700, exist_ok=True)
    os.chmod(str(data), 0o700)
    import fcntl
    lock = (data / ("demo.lock" if args.demo else "alice.lock")).open("w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        parser.error("Another Alice instance is already running.")
    store = Store(data / ("demo.sqlite3" if args.demo else "alice.sqlite3"), config)
    store.recover()
    password = os.environ.get("ADMIN_PASSWORD") or secrets.token_urlsafe(18)
    if not os.environ.get("ADMIN_PASSWORD"):
        print("Temporary panel password: " + password, flush=True)
    port = int(os.environ.get("ADMIN_PORT", "8765"))
    stop = threading.Event()
    health = {"telegram": "توکن تنظیم نشده", "bale": "توکن تنظیم نشده"}
    apis = {}
    config["bot_usernames"] = {}
    if not args.demo:
        for platform in API.HOSTS:
            token = os.environ.get(platform.upper() + "_BOT_TOKEN")
            if token:
                apis[platform] = API(platform, token)
                health[platform] = "در حال اتصال"
    else:
        health = {"telegram": "نمایش محلی؛ بدون اتصال", "bale": "نمایش محلی؛ بدون اتصال"}
    server = ThreadingHTTPServer(("127.0.0.1", port), panel_handler(store, password, health))
    for platform, api in apis.items():
        threading.Thread(target=connect, args=(store, platform, api, stop, health), daemon=True).start()
    print("Alice panel: http://127.0.0.1:%s | username: admin" % port, flush=True)
    print("Demo mode: no messages will be sent." if args.demo else "Configured platforms: " + (", ".join(apis) or "none"), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        server.server_close()


if __name__ == "__main__":
    main()
