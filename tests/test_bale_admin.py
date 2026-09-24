import json
import tempfile
import unittest
from pathlib import Path
from bot import Store
from broadcast import OWNERS

class BaleAdminTests(unittest.TestCase):
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
