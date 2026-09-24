import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from bot import Store, API, APIError
from broadcast import OWNERS, destination_table

class SharedBroadcastTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory()
  self.store=Store(Path(self.tmp.name)/'db',json.loads((Path(__file__).resolve().parents[1]/'config.json').read_text()))
  self.uid=0
  for p in OWNERS:
   self.msg(p,'/start',42)
   self.msg(p,'/start',43)
   self.msg(p,'/stop',43)
   with self.store.db() as db:db.execute('INSERT INTO '+destination_table(p)+' VALUES (-100,?,1)',('Same name',))
 def tearDown(self):self.tmp.cleanup()
 def msg(self,p,text,user=None,**extra):
  self.uid+=1;user=OWNERS[p] if user is None else user
  self.store.handle(p,{'update_id':self.uid,'message':dict({'text':text,'from':{'id':user},'chat':{'type':'private','id':user}},**extra)})
 def rows(self,sql):
  with self.store.db() as db:return db.execute(sql).fetchall()
 def draft(self,p):
  return self.rows('SELECT * FROM '+('bale_' if p=='bale' else '')+'broadcast_drafts')[0]
 def test_all_from_either_admin_routes_each_destination_once(self):
  for source in OWNERS:
   self.msg(source,'News')
   self.assertEqual(self.draft(source)['stage'],'targets')
   before=len(self.rows('SELECT * FROM outbox WHERE campaign IS NOT NULL'))
   self.msg(source,'ارسال به همهٔ اعضا و گروه‌ها',99)
   self.assertEqual(len(self.rows('SELECT * FROM outbox WHERE campaign IS NOT NULL')),before)
   self.msg(source,'ارسال به همهٔ اعضا و گروه‌ها');self.msg(source,'ارسال به همهٔ اعضا و گروه‌ها')
   rows=self.rows('SELECT platform,chat FROM outbox WHERE campaign=(SELECT MAX(id) FROM campaigns)')
   self.assertEqual(len(rows),4)
   self.assertEqual({tuple(r) for r in rows},{('telegram',42),('bale',42),('telegram',-100),('bale',-100)})
   other='bale' if source=='telegram' else 'telegram'
   self.msg(other,'گزارش ارسال')
   report=self.rows('SELECT body FROM outbox ORDER BY id DESC LIMIT 1')[0][0]
   self.assertIn('تلگرام',report);self.assertIn('بله',report)
 def test_members_means_both_without_groups(self):
  self.msg('bale','News');self.msg('bale','ارسال فقط به اعضای بات')
  self.assertEqual({tuple(r) for r in self.rows('SELECT platform,chat FROM outbox WHERE campaign IS NOT NULL')},{('telegram',42),('bale',42)})
 def test_selected_group_id_does_not_cross_platform(self):
  self.msg('telegram','News');self.msg('telegram','انتخاب گروه‌ها');self.msg('telegram','گروه بله · Same name · -100')
  self.msg('telegram','ارسال به انتخاب‌شده‌ها')
  self.assertEqual([tuple(r) for r in self.rows('SELECT platform,chat FROM outbox WHERE campaign IS NOT NULL')],[('bale',-100)])
 def test_legacy_confirmation_cannot_expand_audience(self):
  with self.store.db() as db:
   db.execute('INSERT INTO broadcast_drafts VALUES (?,\'confirm\',?,?,?,9999999999)',(OWNERS['telegram'],json.dumps({'text':'old','method':'sendMessage'}),'["members"]','abc'))
  self.msg('telegram','تأیید ارسال abc')
  self.assertFalse(self.rows('SELECT * FROM campaigns'))
 def test_photo_is_uploaded_as_bytes_in_both_directions(self):
  for source in OWNERS:
   target='bale' if source=='telegram' else 'telegram'
   self.msg(source,'',photo=[{'file_id':'source-file'}],caption='Offer')
   self.msg(source,'ارسال به همهٔ اعضا و گروه‌ها')
   with self.store.db() as db:db.execute('DELETE FROM outbox WHERE campaign IS NULL OR platform!=?',(target,))
   calls=[]
   class Fake:
    def call(self,*a,**k):raise AssertionError('foreign file id must not be sent')
    def upload_photo(self,content,**data):calls.append((content,data))
   with patch.dict(os.environ,{source.upper()+'_BOT_TOKEN':'test-secret'}),patch.object(API,'download_photo',return_value=b'image') as download:
    self.store.deliver_one(target,Fake())
    download.assert_called_once_with('source-file')
   self.assertEqual(calls[0][0],b'image');self.assertEqual(calls[0][1]['caption'],'Offer')
   self.assertNotIn('photo',calls[0][1]);self.assertNotIn('_photo_source',calls[0][1])
   with self.store.db() as db:db.execute('DELETE FROM outbox')
 def test_upload_encodes_caption_and_has_no_source_credentials(self):
  api=API('bale','destination-secret')
  with patch.object(api,'_request',return_value={}) as request:
   api.upload_photo(b'picture',chat_id=42,caption='سلام',caption_entities=[])
  req=request.call_args[0][0]
  self.assertIn(b'name="photo"',req.data);self.assertIn('سلام'.encode(),req.data)
  self.assertNotIn(b'destination-secret',req.data)
 def test_video_is_uploaded_as_bytes_in_both_directions(self):
  for source in OWNERS:
   target='bale' if source=='telegram' else 'telegram'
   self.msg(source,'',video={'file_id':'source-video','file_size':1234},caption='آلیس')
   self.msg(source,'ارسال به همهٔ اعضا و گروه‌ها')
   with self.store.db() as db:db.execute('DELETE FROM outbox WHERE campaign IS NULL OR platform!=?',(target,))
   calls=[]
   class Fake:
    def call(self,*a,**k):raise AssertionError('foreign file id must not be sent')
    def upload_video(self,content,**data):calls.append((content,data))
   with patch.dict(os.environ,{source.upper()+'_BOT_TOKEN':'test-secret'}),patch.object(API,'download_video',return_value=b'mp4') as download:
    self.store.deliver_one(target,Fake())
    download.assert_called_once_with('source-video')
   self.assertEqual(calls[0][0],b'mp4')
   self.assertEqual(calls[0][1]['caption'],'آلیس')
   self.assertNotIn('video',calls[0][1])
   self.assertNotIn('_media_source',calls[0][1])
   with self.store.db() as db:db.execute('DELETE FROM outbox')
 def test_upload_video_uses_multipart_video_field(self):
  api=API('bale','destination-secret')
  with patch.object(api,'_request',return_value={}) as request:
   api.upload_video(b'mp4',chat_id=42,caption='سلام')
  req=request.call_args[0][0]
  self.assertIn(b'name="video"',req.data)
  self.assertIn(b'video/mp4',req.data)
  self.assertIn('سلام'.encode(),req.data)
  self.assertNotIn(b'destination-secret',req.data)
