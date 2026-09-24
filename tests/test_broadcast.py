import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from bot import Store
from broadcast import OWNER

class BroadcastTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.s=Store(Path(self.tmp.name)/'db',json.loads((Path(__file__).resolve().parents[1]/'config.json').read_text()));self.u=0
 def tearDown(self):self.tmp.cleanup()
 def msg(self,text='',user=OWNER,chat=None,kind='private',**extra):
  self.u+=1;self.s.handle('telegram',{'update_id':self.u,'message':dict({'text':text,'from':{'id':user},'chat':{'id':user if chat is None else chat,'type':kind,'title':'Pool'}},**extra)})
 def rows(self,sql):
  with self.s.db() as db:return db.execute(sql).fetchall()
 def compose(self,photo=False):
  self.msg('عضویت در خبرها',user=5);self.msg('/connect',chat=-100,kind='supergroup');self.msg('/broadcast')
  self.msg('Hello' if not photo else '',**({'photo':[{'file_id':'test_photo'}],'caption':'Pool offer'} if photo else {}))
  self.msg('اعضای بات');self.msg('گروه تلگرام · Pool · -100');self.msg('پیش‌نمایش ارسال')
  return self.rows('SELECT nonce FROM broadcast_drafts')[0][0]
 def test_non_owner_and_anonymous_cannot_register_or_broadcast(self):
  self.msg('/broadcast',user=5);self.msg('/connect',user=5,chat=-100,kind='group');self.msg('/connect',chat=-100,kind='group',sender_chat={'id':-100})
  self.assertFalse(self.rows('SELECT * FROM broadcast_drafts'));self.assertFalse(self.rows('SELECT * FROM broadcast_runs'))
  self.assertEqual(len(self.rows('SELECT * FROM destinations')),1)
 def test_confirm_exactly_once_and_private_vs_group(self):
  nonce=self.compose();self.assertFalse(self.rows('SELECT * FROM outbox WHERE campaign IS NOT NULL'))
  self.msg('تأیید ارسال '+nonce,user=5);self.assertFalse(self.rows('SELECT * FROM broadcast_runs'))
  self.msg('تأیید ارسال '+nonce);self.msg('تأیید ارسال '+nonce)
  rows=self.rows('SELECT * FROM outbox WHERE campaign IS NOT NULL');self.assertEqual(len(rows),2);self.assertEqual({r['chat'] for r in rows},{5,-100})
 def test_stop_and_group_disconnect_before_delivery(self):
  nonce=self.compose();self.msg('تأیید ارسال '+nonce);self.msg('/stop',user=5);self.msg('/disconnect',chat=-100,kind='group')
  with self.s.db() as db:db.execute('DELETE FROM outbox WHERE campaign IS NULL')
  class API:
   def call(self,*a,**k):raise AssertionError('must not send')
  self.s.deliver_one('telegram',API());self.s.deliver_one('telegram',API());self.assertEqual({r[0] for r in self.rows('SELECT status FROM outbox')},{'skipped'})
 def test_photo_payload_and_preview(self):
  nonce=self.compose(True);self.msg('تأیید ارسال '+nonce)
  with self.s.db() as db:db.execute('DELETE FROM outbox WHERE campaign IS NULL')
  calls=[]
  class API:
   def call(self,m,**data):calls.append((m,data))
  self.s.deliver_one('telegram',API());self.assertEqual(calls[0][0],'sendPhoto');self.assertEqual(calls[0][1]['photo'],'test_photo');self.assertEqual(calls[0][1]['caption'],'Pool offer')
 def test_cancel_and_stale_confirm(self):
  nonce=self.compose();self.msg('لغو ارسال');self.msg('تأیید ارسال '+nonce);self.assertFalse(self.rows('SELECT * FROM broadcast_runs'))
 def test_toggle_target_off(self):
  self.msg('/broadcast');self.msg('Hello');self.msg('اعضای بات');self.msg('✅ اعضای بات');self.msg('پیش‌نمایش ارسال');self.assertEqual(self.rows('SELECT stage FROM broadcast_drafts')[0][0],'targets')
 def test_direct_owner_message_then_choose_all(self):
  self.msg('خبر تازه',user=123)
  self.assertFalse(self.rows('SELECT * FROM broadcast_drafts'))
  self.msg('/start',user=5)
  self.msg('hello',user=123,chat=-555,kind='group')
  self.msg('خبر تازه')
  self.assertEqual(self.rows('SELECT stage FROM broadcast_drafts')[0][0],'targets')
  self.assertFalse(self.rows('SELECT * FROM broadcast_runs'))
  self.msg('همه اعضا و گروه‌ها')
  targets=json.loads(self.rows('SELECT targets FROM broadcast_drafts')[0][0])
  self.assertEqual(set(targets),{'members','telegram:-555'})
  self.assertEqual(self.rows('SELECT stage FROM broadcast_drafts')[0][0],'confirm')
  self.assertFalse(self.rows('SELECT * FROM outbox WHERE campaign IS NOT NULL'))
  nonce=self.rows('SELECT nonce FROM broadcast_drafts')[0][0]
  self.msg('تأیید ارسال '+nonce)
  self.assertEqual({r[0] for r in self.rows('SELECT chat FROM outbox WHERE campaign IS NOT NULL')},{5,-555})
 def test_no_groups_shows_members_only_hint(self):
  self.msg('/broadcast');self.msg('Hello')
  body=self.rows('SELECT body FROM outbox ORDER BY id DESC LIMIT 1')[0][0]
  self.assertIn('فعلاً هیچ گروهی',body)
 def test_all_targets_without_groups(self):
  self.msg('/broadcast');self.msg('Hello');self.msg('همه اعضا و گروه‌ها')
  self.assertEqual(json.loads(self.rows('SELECT targets FROM broadcast_drafts')[0][0]),['members'])
  self.assertEqual(self.rows('SELECT stage FROM broadcast_drafts')[0][0],'confirm')
  self.assertEqual(len(self.rows("SELECT * FROM outbox WHERE campaign IS NULL AND body=''")),1)
 def test_cancel_clears_preview_outbox(self):
  self.compose();self.assertTrue(self.rows("SELECT * FROM outbox WHERE campaign IS NULL AND body=''"))
  self.msg('لغو ارسال');self.assertFalse(self.rows("SELECT * FROM outbox WHERE campaign IS NULL AND body=''"))
 def test_membership_event_discovers_and_removes_group(self):
  for state,active in [('administrator',1),('left',0)]:
   self.u+=1
   self.s.handle('telegram',{'update_id':self.u,'my_chat_member':{'chat':{'id':-900,'type':'supergroup','title':'Pool'},'new_chat_member':{'status':state}}})
   self.assertEqual(self.rows('SELECT active FROM destinations WHERE chat=-900')[0][0],active)
if __name__=='__main__':unittest.main()
