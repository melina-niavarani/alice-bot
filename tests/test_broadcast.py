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
  self.msg('انتخاب گروه‌ها');self.msg('اعضای بات');self.msg('گروه تلگرام · Pool · -100')
 def test_non_owner_and_anonymous_cannot_register_or_broadcast(self):
  self.msg('/broadcast',user=5);self.msg('/connect',user=5,chat=-100,kind='group');self.msg('/connect',chat=-100,kind='group',sender_chat={'id':-100})
  self.assertFalse(self.rows('SELECT * FROM broadcast_drafts'));self.assertFalse(self.rows('SELECT * FROM broadcast_runs'))
  self.assertEqual(len(self.rows('SELECT * FROM destinations')),1)
 def test_send_exactly_once_and_private_vs_group(self):
  self.compose();self.assertFalse(self.rows('SELECT * FROM outbox WHERE campaign IS NOT NULL'))
  self.msg('ارسال به انتخاب‌شده‌ها',user=5);self.assertFalse(self.rows('SELECT * FROM broadcast_runs'))
  self.msg('ارسال به انتخاب‌شده‌ها');self.msg('ارسال به انتخاب‌شده‌ها')
  rows=self.rows('SELECT * FROM outbox WHERE campaign IS NOT NULL');self.assertEqual(len(rows),2);self.assertEqual({r['chat'] for r in rows},{5,-100})
 def test_stop_and_group_disconnect_before_delivery(self):
  self.compose();self.msg('ارسال به انتخاب‌شده‌ها');self.msg('/stop',user=5);self.msg('/disconnect',chat=-100,kind='group')
  with self.s.db() as db:db.execute('DELETE FROM outbox WHERE campaign IS NULL')
  class API:
   def call(self,*a,**k):raise AssertionError('must not send')
  self.s.deliver_one('telegram',API());self.s.deliver_one('telegram',API());self.assertEqual({r[0] for r in self.rows('SELECT status FROM outbox')},{'skipped'})
 def test_photo_payload_without_duplicate_preview(self):
  self.compose(True);self.assertFalse(self.rows("SELECT * FROM outbox WHERE campaign IS NULL AND body=''"))
  self.msg('ارسال به انتخاب‌شده‌ها')
  with self.s.db() as db:db.execute('DELETE FROM outbox WHERE campaign IS NULL')
  calls=[]
  class API:
   def call(self,m,**data):calls.append((m,data))
  self.s.deliver_one('telegram',API());self.assertEqual(calls[0][0],'sendPhoto');self.assertEqual(calls[0][1]['photo'],'test_photo');self.assertEqual(calls[0][1]['caption'],'Pool offer')
 def test_video_is_accepted_and_sent_on_same_platform(self):
  self.msg('/start',user=5)
  self.msg('/broadcast')
  self.msg('',video={'file_id':'test_video','file_size':1024},caption='سانس جدید')
  self.assertEqual(self.rows('SELECT stage FROM broadcast_drafts')[0][0],'targets')
  self.msg('ارسال فقط به اعضای بات')
  with self.s.db() as db:db.execute('DELETE FROM outbox WHERE campaign IS NULL')
  calls=[]
  class API:
   def call(self,m,**data):calls.append((m,data))
  self.s.deliver_one('telegram',API())
  self.assertEqual(calls[0][0],'sendVideo')
  self.assertEqual(calls[0][1]['video'],'test_video')
  self.assertEqual(calls[0][1]['caption'],'سانس جدید')
 def test_oversize_video_stays_in_compose_stage(self):
  self.msg('/broadcast')
  self.msg('',video={'file_id':'large','file_size':20*1024*1024+1})
  self.assertEqual(self.rows('SELECT stage FROM broadcast_drafts')[0][0],'content')
 def test_cancel_and_stale_send_button(self):
  self.compose();self.msg('لغو ارسال');self.msg('ارسال به انتخاب‌شده‌ها');self.assertFalse(self.rows('SELECT * FROM broadcast_runs'))
 def test_toggle_target_off(self):
  self.msg('/broadcast');self.msg('Hello');self.msg('انتخاب گروه‌ها');self.msg('اعضای بات');self.msg('✅ اعضای بات');self.msg('ارسال به انتخاب‌شده‌ها')
  self.assertEqual(self.rows('SELECT stage FROM broadcast_drafts')[0][0],'groups')
  self.assertFalse(self.rows('SELECT * FROM broadcast_runs'))
 def test_direct_owner_message_then_choose_all(self):
  self.msg('خبر تازه',user=123)
  self.assertFalse(self.rows('SELECT * FROM broadcast_drafts'))
  self.msg('/start',user=5)
  self.msg('hello',user=123,chat=-555,kind='group')
  self.msg('خبر تازه')
  self.assertEqual(self.rows('SELECT stage FROM broadcast_drafts')[0][0],'targets')
  self.assertFalse(self.rows('SELECT * FROM broadcast_runs'))
  self.msg('ارسال به همهٔ اعضا و گروه‌ها')
  self.assertFalse(self.rows('SELECT * FROM broadcast_drafts'))
  self.assertFalse(self.rows("SELECT * FROM outbox WHERE campaign IS NULL AND body=''"))
  self.assertEqual({r[0] for r in self.rows('SELECT chat FROM outbox WHERE campaign IS NOT NULL')},{5,-555})
 def test_no_groups_keeps_all_options_visible(self):
  self.msg('/broadcast');self.msg('Hello')
  body=self.rows('SELECT body FROM outbox ORDER BY id DESC LIMIT 1')[0][0]
  self.assertIn('هنوز گروهی ثبت نشده',body)
  markup=json.loads(self.rows('SELECT markup FROM outbox ORDER BY id DESC LIMIT 1')[0][0])
  self.assertIn(['ارسال فقط به اعضای بات'],markup['keyboard'])
  self.assertIn(['ارسال به همهٔ گروه‌ها'],markup['keyboard'])
  self.assertIn(['ارسال به همهٔ اعضا و گروه‌ها'],markup['keyboard'])
  self.assertIn(['انتخاب گروه‌ها'],markup['keyboard'])
 def test_all_targets_without_groups(self):
  self.msg('/start',user=5);self.msg('/broadcast');self.msg('Hello');self.msg('ارسال فقط به اعضای بات')
  self.assertEqual({r[0] for r in self.rows('SELECT chat FROM outbox WHERE campaign IS NOT NULL')},{5})
  self.assertFalse(self.rows("SELECT * FROM outbox WHERE campaign IS NULL AND body=''"))
 def test_no_groups_does_not_silently_send_to_members_from_all_button(self):
  self.msg('/start',user=5);self.msg('/broadcast');self.msg('Hello')
  self.msg('ارسال به همهٔ اعضا و گروه‌ها')
  self.assertFalse(self.rows('SELECT * FROM broadcast_runs'))
  self.assertEqual(self.rows('SELECT stage FROM broadcast_drafts')[0][0],'targets')
  self.msg('ارسال به همهٔ گروه‌ها')
  self.assertFalse(self.rows('SELECT * FROM broadcast_runs'))
 def test_all_groups_excludes_private_members(self):
  self.msg('/start',user=5);self.msg('/connect',chat=-100,kind='supergroup')
  self.msg('/broadcast');self.msg('Hello');self.msg('ارسال به همهٔ گروه‌ها')
  self.assertEqual({r[0] for r in self.rows('SELECT chat FROM outbox WHERE campaign IS NOT NULL')},{-100})
 def test_back_to_audience_and_cancel(self):
  self.compose();self.msg('بازگشت به مقصدها')
  self.assertEqual(self.rows('SELECT stage FROM broadcast_drafts')[0][0],'targets')
  self.msg('لغو ارسال');self.assertFalse(self.rows('SELECT * FROM broadcast_drafts'))
 def test_change_message_does_not_send_old_content(self):
  self.msg('/start',user=5);self.msg('/broadcast');self.msg('Old');self.msg('تغییر پیام')
  self.assertEqual(self.rows('SELECT stage FROM broadcast_drafts')[0][0],'content')
  self.msg('New');self.msg('ارسال فقط به اعضای بات')
  self.assertEqual([r[0] for r in self.rows('SELECT body FROM outbox WHERE campaign IS NOT NULL')],['New'])
 def test_stale_action_button_does_not_create_customer_reply(self):
  self.msg('ارسال به همهٔ اعضا و گروه‌ها')
  self.assertFalse(self.rows('SELECT * FROM outbox'))
 def test_membership_event_discovers_and_removes_group(self):
  for state,active in [('administrator',1),('left',0)]:
   self.u+=1
   self.s.handle('telegram',{'update_id':self.u,'my_chat_member':{'chat':{'id':-900,'type':'supergroup','title':'Pool'},'new_chat_member':{'status':state}}})
   self.assertEqual(self.rows('SELECT active FROM destinations WHERE chat=-900')[0][0],active)
if __name__=='__main__':unittest.main()
