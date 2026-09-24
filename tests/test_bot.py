import base64
from io import BytesIO
import json
from pathlib import Path
import re
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bot import APIError, Store, panel_handler, phone_number


class FakeAPI:
    def __init__(self, error=None):
        self.calls, self.error = [], error

    def call(self, method, **data):
        self.calls.append((method, data))
        if self.error:
            raise self.error
        return {"message_id": 1}


class BotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        config = json.loads((Path(__file__).resolve().parents[1] / "config.json").read_text())
        self.store = Store(Path(self.temp.name) / "test.sqlite3", config)
        self.uid = 0

    def tearDown(self):
        self.temp.cleanup()

    def message(self, text, chat=1, platform="telegram", kind="private", uid=None):
        self.uid += 1
        self.store.handle(platform, {"update_id": self.uid if uid is None else uid,
                                   "message": {"chat": {"id": chat, "type": kind}, "from": {"id": chat, "first_name": "آزمایش"}, "text": text}})

    def query(self, sql, params=()):
        with self.store.db() as db:
            return db.execute(sql, params).fetchall()

    def clear_replies(self):
        with self.store.db() as db:
            db.execute("DELETE FROM outbox WHERE campaign IS NULL")

    def test_telegram_miniapp_replaces_menu_only_when_configured(self):
        with patch.dict('os.environ', {'MINIAPP_URL':'https://example.org/alice'}):
            self.message('/start')
            markup=json.loads(self.query('SELECT markup FROM outbox ORDER BY id DESC LIMIT 1')[0][0])
            self.assertEqual(len(markup['keyboard']), 3)
            self.assertEqual(markup['keyboard'][2][0]['web_app']['url'],'https://example.org/alice')
            self.message('/start', platform='bale')
            markup=json.loads(self.query('SELECT markup FROM outbox ORDER BY id DESC LIMIT 1')[0][0])
            self.assertEqual(markup['keyboard'][0],['بدنسازی','استخر و سونا'])

    def test_start_subscribes_and_stop_persists(self):
        self.message("/start")
        self.assertEqual(self.query("SELECT subscribed FROM members")[0][0], 1)
        self.message("عضویت در خبرها")
        self.assertEqual(self.query("SELECT subscribed FROM members")[0][0], 1)
        self.message("/stop")
        self.message("/start")
        self.assertEqual(self.query("SELECT subscribed FROM members")[0][0], 0)
        self.message("/subscribe")
        self.assertEqual(self.query("SELECT subscribed FROM members")[0][0], 1)

    def test_duplicate_updates_are_atomic(self):
        self.message("/start", uid=100)
        self.message("/start", uid=100)
        self.assertEqual(len(self.query("SELECT * FROM outbox")), 1)
        self.assertEqual(self.query("SELECT value FROM offsets")[0][0], 101)

    def test_group_cannot_create_member_or_request(self):
        self.message("عضویت در خبرها", kind="group")
        self.assertEqual(len(self.query("SELECT * FROM members")), 0)

    def test_platform_ids_are_separate(self):
        self.message("عضویت در خبرها", platform="telegram")
        self.message("/start", platform="bale")
        self.assertEqual(len(self.query("SELECT * FROM members")), 2)
        self.assertEqual(self.query("SELECT subscribed FROM members WHERE platform='bale'")[0][0], 1)
        self.message("/stop", platform="bale")
        self.message("/start", platform="bale")
        self.assertEqual(self.query("SELECT subscribed FROM members WHERE platform='bale'")[0][0], 0)
        self.assertEqual(self.query("SELECT subscribed FROM members WHERE platform='telegram'")[0][0], 1)

    def test_phone_normalization(self):
        for value in ("۰۹۱۲۱۲۳۴۵۶۷", "+98 912 123 4567", "00989121234567", "٩٨٩١٢١٢٣٤٥٦٧"):
            self.assertEqual(phone_number(value), "09121234567")
        for value in ("1234", "09121234567<script>", "+12025551234"):
            self.assertIsNone(phone_number(value))

    def test_removed_features_cannot_collect_contact_or_referral(self):
        self.message("/start")
        with self.store.db() as db:
            db.execute("UPDATE members SET state='confirm_phone',pending='09121234567'")
        for text in ("تأیید درخواست تماس", "درخواست تماس", "09121234567", "ثبت کد معرف", "معرفی دوستان", "خبر بازگشایی"):
            self.message(text)
        self.assertEqual(len(self.query("SELECT * FROM leads")), 0)
        self.assertEqual(self.query("SELECT pending FROM members")[0][0], "")
        self.assertEqual(self.query("SELECT referred_by FROM members")[0][0], "")

    def test_compact_menu_and_service_pages(self):
        self.message("/start")
        markup = json.loads(self.query("SELECT markup FROM outbox ORDER BY id DESC LIMIT 1")[0][0])
        self.assertEqual(markup["keyboard"], [["بدنسازی", "استخر و سونا"], ["نشانی مجموعه"]])
        for label, field in (("بدنسازی", "gym"), ("استخر و سونا", "pool"), ("نشانی مجموعه", "address")):
            self.message(label)
            body = self.query("SELECT body FROM outbox ORDER BY id DESC LIMIT 1")[0][0]
            self.assertEqual(body, self.store.config[field])
            self.assertNotIn("درخواست تماس", body)

    def test_campaign_confirmation_segmentation_and_cancel(self):
        self.message("عضویت در خبرها")
        self.message("علاقه‌مندی‌ها")
        self.message("بدنسازی")
        self.message("/start", chat=2)
        self.message("/stop", chat=2)
        self.message("عضویت در خبرها", chat=3, platform="bale")
        self.message("علاقه‌مندی‌ها", chat=3, platform="bale")
        self.message("همه خدمات", chat=3, platform="bale")
        ident = self.store.create_campaign("خبر تست", "بدنسازی")
        self.assertEqual(len(self.query("SELECT * FROM outbox WHERE campaign IS NOT NULL")), 0)
        self.assertTrue(self.store.confirm_campaign(ident))
        self.assertFalse(self.store.confirm_campaign(ident))
        self.assertEqual(len(self.query("SELECT * FROM outbox WHERE campaign IS NOT NULL")), 2)
        self.message("/stop")
        self.clear_replies()
        api = FakeAPI()
        self.store.deliver_one("telegram", api)
        self.assertEqual(len(api.calls), 0)
        self.store.deliver_one("bale", api)
        self.assertEqual(len(api.calls), 1)
        self.assertIn("/stop", api.calls[0][1]["text"])

    def test_rate_limit_requeues_but_uncertain_delivery_does_not(self):
        self.message("/start")
        self.store.deliver_one("telegram", FakeAPI(APIError(429, 10)))
        self.assertEqual(self.query("SELECT status FROM outbox")[0][0], "pending")
        with self.store.db() as db:
            db.execute("UPDATE outbox SET due=0")
        self.store.deliver_one("telegram", FakeAPI(APIError(uncertain=True)))
        self.assertEqual(self.query("SELECT status FROM outbox")[0][0], "unknown")
        self.assertFalse(self.store.deliver_one("telegram", FakeAPI()))

    def test_blocked_user_unsubscribes(self):
        self.message("عضویت در خبرها")
        self.store.deliver_one("telegram", FakeAPI(APIError(403)))
        self.assertEqual(self.query("SELECT subscribed FROM members")[0][0], 0)

    def test_old_referral_links_no_longer_attribute_members(self):
        self.message("/start")
        code = self.query("SELECT referral FROM members")[0][0]
        self.message("/start r_" + code)
        self.assertEqual(self.query("SELECT referred_by FROM members")[0][0], "")
        self.message("/start r_" + code, chat=2)
        self.message("/start r_invalid", chat=2)
        self.assertEqual(self.query("SELECT referred_by FROM members WHERE chat=2")[0][0], "")

    def test_recovery_does_not_duplicate_uncertain_sends(self):
        self.message("/start")
        with self.store.db() as db:
            db.execute("UPDATE outbox SET status='sending'")
        self.store.recover()
        self.assertEqual(self.query("SELECT status FROM outbox")[0][0], "unknown")

    def test_panel_auth_csrf_preview_escape_and_confirmation(self):
        # Exercise real HTTP parsing without binding a port in a restricted sandbox.
        handler = panel_handler(self.store, "test-only", {})
        server = SimpleNamespace(server_port=8765)
        auth = "Basic " + base64.b64encode(b"admin:test-only").decode()

        def request(method="GET", path="/", data=None, authorized=True, host="127.0.0.1:8765"):
            body = urlencode(data or {}).encode()
            headers = "%s %s HTTP/1.1\r\nHost: %s\r\nContent-Length: %s\r\n" % (method, path, host, len(body))
            if authorized:
                headers += "Authorization: %s\r\n" % auth
            raw = headers.encode() + b"\r\n" + body
            class Connection:
                def __init__(self):
                    self.output = bytearray()
                def makefile(self, *args):
                    return BytesIO(raw)
                def sendall(self, data):
                    self.output.extend(data)
            conn = Connection()
            handler(conn, ("127.0.0.1", 1234), server)
            return conn.output.decode()

        self.assertIn("401 Unauthorized", request(authorized=False))
        self.assertIn("403 Forbidden", request(host="untrusted.example"))
        page = request()
        self.assertIn("200 OK", page)
        token = re.search(r'name="csrf" value="([^"]+)"', page)[1]
        self.assertIn("403 Forbidden", request("POST", "/send", {"id": 1, "csrf": "wrong"}))
        self.message("عضویت در خبرها")
        preview = request("POST", "/preview", {"csrf": token, "body": "<script>alert(1)</script>", "segment": "all"})
        self.assertIn("&lt;script&gt;", preview)
        self.assertNotIn("<script>", preview)
        self.assertEqual(len(self.query("SELECT * FROM outbox WHERE campaign IS NOT NULL")), 0)
        self.assertIn("303 See Other", request("POST", "/send", {"csrf": token, "id": 1}))
        request("POST", "/send", {"csrf": token, "id": 1})
        self.assertEqual(len(self.query("SELECT * FROM outbox WHERE campaign=1")), 1)


if __name__ == "__main__":
    unittest.main()
