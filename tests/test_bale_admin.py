import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from bot import Store
from broadcast import OWNERS

class BaleAdminTests(unittest.TestCase):
 def test_existing_destination_tables_gain_kind_column(self):
  with tempfile.TemporaryDirectory() as folder:
   path=Path(folder)/'db'
   with sqlite3.connect(path) as db:
    for table in ('destinations','bale_destinations'):
     db.execute('CREATE TABLE '+table+'(chat INTEGER PRIMARY KEY,title TEXT,active INTEGER DEFAULT 1)')
     db.execute('INSERT INTO '+table+'(chat,title,active) VALUES (-100,?,1)',('Old group',))
   s=Store(path,json.loads((Path(__file__).resolve().parents[1]/'config.json').read_text()))
   with s.db() as db:
    for table in ('destinations','bale_destinations'):
     self.assertEqual(db.execute('SELECT kind FROM '+table+' WHERE chat=-100').fetchone()[0],'group')
 def test_platform_admin_and_campaign_isolation(self):
  with tempfile.TemporaryDirectory() as folder:
   s=Store(Path(folder)/'db',json.loads((Path(__file__).resolve().parents[1]/'config.json').read_text()))
   sequence=0
   def send(platform,user,text,chat=None):
    nonlocal sequence
    sequence+=1
    s.handle(platform,{'update_id':sequence,'message':{'from':{'id':user},'text':text,'chat':{'id':user if chat is None else chat,'type':'private' if chat is None else 'group','title':'Test'}}})
   for platform in ('telegram','bale'):send(platform,12,'/start')
   send('bale',OWNERS['telegram'],'/broadcast')
   with s.db() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM bale_broadcast_drafts').fetchone()[0],0)
   send('bale',OWNERS['bale'],'/start')
   with s.db() as db:
    markup=json.loads(db.execute('SELECT markup FROM outbox ORDER BY id DESC LIMIT 1').fetchone()[0]);self.assertIn(['مدیریت ارسال','ارسال همگانی'],markup['keyboard'])
   for platform in ('telegram','bale'):send(platform,OWNERS[platform],'/connect',-100)
   send('bale',OWNERS['bale'],'/broadcast');send('bale',OWNERS['bale'],'Test notice');send('bale',OWNERS['bale'],'انتخاب گروه‌ها');send('bale',OWNERS['bale'],'اعضای بات');send('bale',OWNERS['bale'],'گروه بله · Test · -100')
   send('bale',OWNERS['bale'],'ارسال به انتخاب‌شده‌ها')
   with s.db() as db:
    self.assertEqual({r[0] for r in db.execute('SELECT platform FROM outbox WHERE campaign IS NOT NULL')},{'telegram','bale'})
    self.assertEqual(db.execute('SELECT COUNT(*) FROM broadcast_runs').fetchone()[0],0)
    self.assertEqual(db.execute('SELECT COUNT(*) FROM bale_broadcast_runs').fetchone()[0],1)
    db.execute('DELETE FROM outbox WHERE campaign IS NULL OR destination=0')
   send('telegram',OWNERS['telegram'],'/disconnect',-100)
   with s.db() as db:db.execute('DELETE FROM outbox WHERE campaign IS NULL')
   calls=[]
   class API:
    def call(self,method,**data):calls.append(data)
   s.deliver_one('bale',API());self.assertEqual(calls[0]['chat_id'],-100)
 def test_bale_channel_post_registers_channel_and_receives_group_broadcast(self):
  with tempfile.TemporaryDirectory() as folder:
   s=Store(Path(folder)/'db',json.loads((Path(__file__).resolve().parents[1]/'config.json').read_text()))
   channel={'id':-200,'type':'channel','title':'اخبار آلیس'}
   s.handle('bale',{'update_id':1,'channel_post':{'text':'خبر عادی','chat':channel}})
   with s.db() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM bale_destinations').fetchone()[0],0)
   s.handle('bale',{'update_id':2,'channel_post':{'text':'/connect','chat':channel}})
   with s.db() as db:
    row=db.execute('SELECT title,active,kind FROM bale_destinations WHERE chat=-200').fetchone()
    self.assertEqual(tuple(row),('اخبار آلیس',1,'channel'))
    self.assertEqual(db.execute('SELECT COUNT(*) FROM outbox WHERE chat=-200').fetchone()[0],0)
    self.assertIn('کانال',db.execute('SELECT body FROM outbox WHERE chat=? ORDER BY id DESC LIMIT 1',(OWNERS['bale'],)).fetchone()[0])
   s.handle('telegram',{'update_id':1,'message':{'text':'/admin','from':{'id':OWNERS['telegram']},'chat':{'id':OWNERS['telegram'],'type':'private'}}})
   with s.db() as db:
    self.assertIn('کانال بله',db.execute('SELECT body FROM outbox WHERE chat=? ORDER BY id DESC LIMIT 1',(OWNERS['telegram'],)).fetchone()[0])
   s.handle('telegram',{'update_id':2,'message':{'text':'/broadcast','from':{'id':OWNERS['telegram']},'chat':{'id':OWNERS['telegram'],'type':'private'}}})
   s.handle('telegram',{'update_id':3,'message':{'text':'خبر آلیس','from':{'id':OWNERS['telegram']},'chat':{'id':OWNERS['telegram'],'type':'private'}}})
   s.handle('telegram',{'update_id':4,'message':{'text':'ارسال به همهٔ گروه‌ها و کانال‌ها','from':{'id':OWNERS['telegram']},'chat':{'id':OWNERS['telegram'],'type':'private'}}})
   with s.db() as db:
    row=db.execute('SELECT platform,chat FROM outbox WHERE campaign IS NOT NULL').fetchone()
    self.assertEqual(tuple(row),('bale',-200))
   s.handle('bale',{'update_id':3,'channel_post':{'text':'/disconnect','chat':channel}})
   with s.db() as db:self.assertEqual(db.execute('SELECT active FROM bale_destinations WHERE chat=-200').fetchone()[0],0)
 def test_bale_channel_message_shape_and_removal_event(self):
  with tempfile.TemporaryDirectory() as folder:
   s=Store(Path(folder)/'db',json.loads((Path(__file__).resolve().parents[1]/'config.json').read_text()))
   channel={'id':-201,'type':'channel','title':'اطلاعیه‌های آلیس'}
   s.handle('bale',{'update_id':1,'message':{'text':'/connect','chat':channel}})
   with s.db() as db:self.assertEqual(db.execute('SELECT active FROM bale_destinations WHERE chat=-201').fetchone()[0],1)
   s.handle('bale',{'update_id':2,'my_chat_member':{'chat':channel,'new_chat_member':{'status':'left'}}})
   with s.db() as db:self.assertEqual(db.execute('SELECT active FROM bale_destinations WHERE chat=-201').fetchone()[0],0)
