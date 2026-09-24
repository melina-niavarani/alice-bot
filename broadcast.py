"""Owner-only Telegram/Bale broadcast composer; all changes share Store's transaction."""
import json
import secrets
import time
OWNER = 92655562
LABELS = {'telegram':'تلگرام', 'bale':'بله'}
OWNERS = {"telegram": OWNER, "bale": 1984558572}

def destination_table(platform):
    return "bale_destinations" if platform == "bale" else "destinations"
ADMIN = [['ارسال همگانی', 'گزارش ارسال'], ['مقصدهای ارسال', 'بازگشت']]

def setup(db):
    db.executescript('''
    CREATE TABLE IF NOT EXISTS destinations(chat INTEGER PRIMARY KEY,title TEXT,active INTEGER DEFAULT 1);
    CREATE TABLE IF NOT EXISTS broadcast_drafts(owner INTEGER PRIMARY KEY,stage TEXT,payload TEXT,targets TEXT,nonce TEXT,expires REAL);
    CREATE TABLE IF NOT EXISTS broadcast_runs(campaign INTEGER PRIMARY KEY,owner INTEGER);
    ''')
    db.executescript("""
    CREATE TABLE IF NOT EXISTS bale_destinations(chat INTEGER PRIMARY KEY,title TEXT,active INTEGER DEFAULT 1);
    CREATE TABLE IF NOT EXISTS bale_broadcast_drafts(owner INTEGER PRIMARY KEY,stage TEXT,payload TEXT,targets TEXT,nonce TEXT,expires REAL);
    CREATE TABLE IF NOT EXISTS bale_broadcast_runs(campaign INTEGER PRIMARY KEY,owner INTEGER);
    """)
    columns={r[1] for r in db.execute('PRAGMA table_info(outbox)')}
    for name,definition in [('method',"TEXT DEFAULT 'sendMessage'"),('payload',"TEXT DEFAULT '{}'"),('destination',"INTEGER DEFAULT 0")]:
        if name not in columns: db.execute('ALTER TABLE outbox ADD COLUMN '+name+' '+definition)

def observe_group(store, db, platform, update):
    event = update.get('my_chat_member', {})
    msg = update.get('message', {})
    chat = event.get('chat') or msg.get('chat', {})
    if chat.get('type') not in ('group', 'supergroup'): return
    ident = chat.get('id')
    if not isinstance(ident, int): return
    table = destination_table(platform)
    if event:
        member = event.get('new_chat_member', {})
        status = member.get('status')
        active = status in ('member', 'administrator', 'creator') or (status == 'restricted' and member.get('is_member', False))
        db.execute('INSERT INTO '+table+'(chat,title,active) VALUES (?,?,?) ON CONFLICT(chat) DO UPDATE SET title=excluded.title,active=excluded.active', (ident,chat.get('title','گروه'),int(active)))
    else:
        bot_id = store.config.get('bot_ids', {}).get(platform)
        left = msg.get('left_chat_member', {}).get('id')
        if bot_id and left == bot_id:
            db.execute('UPDATE '+table+' SET active=0 WHERE chat=?',(ident,))
            return
        joined = any(m.get('id') == bot_id for m in msg.get('new_chat_members', [])) if bot_id else False
        suffix = ',active=1' if joined else ''
        db.execute('INSERT INTO '+table+'(chat,title,active) VALUES (?,?,1) ON CONFLICT(chat) DO UPDATE SET title=excluded.title'+suffix, (ident,chat.get('title','گروه')))

def handle(store,db,platform,msg):
    if platform not in OWNERS:return False
    OWNER = OWNERS[platform]
    # Fixed table mapping preserves existing Telegram data and isolates Bale drafts/groups.
    def execute(sql, params=()):
        if platform == 'bale':
            for table in ('destinations', 'broadcast_drafts', 'broadcast_runs'):
                sql = sql.replace(table, 'bale_' + table)
        return db.execute(sql, params)
    text=msg.get('text','').strip(); command=text.split(' ',1)[0].split('@')[0]
    chat=msg.get('chat',{}); ident=chat.get('id'); owner=msg.get('from',{}).get('id')==OWNER and not msg.get('sender_chat')
    def say(body,keyboard=ADMIN):store.queue(db,platform,ident,body,keyboard)
    def target_choices():
        return [('اعضای بات','members')]+[('گروه '+LABELS[p]+' · '+r['title'][:35]+' · '+str(r['chat']),p+':'+str(r['chat'])) for p in OWNERS for r in db.execute('SELECT * FROM '+destination_table(p)+' WHERE active=1')]
    def clear_previews():
        execute("DELETE FROM outbox WHERE platform=? AND chat=? AND campaign IS NULL AND body=''",(platform,ident))
    if chat.get('type')!='private':
        if owner and chat.get('type') in ('group','supergroup') and command in ('/connect','/disconnect'):
            execute('INSERT INTO destinations(chat,title,active) VALUES (?,?,?) ON CONFLICT(chat) DO UPDATE SET title=excluded.title,active=excluded.active',(ident,chat.get('title','گروه آلیس'),int(command=='/connect')))
            say('این گروه به مقصدهای مجاز آلیس اضافه شد.' if command=='/connect' else 'ارسال به این گروه غیرفعال شد.',None)
        return True
    if not owner or ident != OWNER:return False
    if command=='/admin' or text in ('مدیریت ارسال','مقصدهای ارسال'):
        rows=target_choices()[1:]
        say('مدیریت ارسال آلیس\nپیام، عکس یا ویدئوی کوتاه را مستقیم همین‌جا بفرست؛ سپس انتخاب کن کجا منتشر شود. گروه‌هایی که بات به آن‌ها اضافه شود، خودکار شناسایی می‌شوند.\n\nگروه‌های مجاز:\n'+('\n'.join(name for name,key in rows) or 'هنوز گروهی ثبت نشده.'));return True
    if text=='گزارش ارسال' or command=='/report':
        runs=db.execute('SELECT campaign FROM broadcast_runs UNION SELECT campaign FROM bale_broadcast_runs ORDER BY campaign DESC LIMIT 5').fetchall()
        labels={'sent':'تحویل پیام‌رسان','pending':'در صف','sending':'در حال ارسال','failed':'ناموفق','unknown':'نتیجه نامشخص','skipped':'لغوشده'}
        lines=[]
        for run in runs:
            counts=execute('SELECT platform,status,COUNT(*) n FROM outbox WHERE campaign=? GROUP BY platform,status',(run[0],)).fetchall()
            lines.append('#%s: '%run[0]+' · '.join(LABELS[r['platform']]+' — '+labels.get(r['status'],r['status'])+': '+str(r['n']) for r in counts))
        say('\n'.join(lines) or 'هنوز ارسال همگانی ثبت نشده.');return True
    if text=='ارسال همگانی' or command=='/broadcast':
        execute('INSERT OR REPLACE INTO broadcast_drafts VALUES (?,?,?,?,?,?)',(OWNER,'content','{}','[]','',time.time()+3600))
        say('متن، یک عکس یا یک ویدئوی کوتاه همراه کپشن بفرست. حجم ویدئو حداکثر ۲۰ مگابایت باشد. آلبوم پشتیبانی نمی‌شود. تا انتخاب مقصد و تأیید نهایی هیچ پیامی منتشر نمی‌شود.',[['لغو ارسال']]);return True
    draft=execute('SELECT * FROM broadcast_drafts WHERE owner=?',(OWNER,)).fetchone()
    if not draft:
        controls = {'بدنسازی','استخر و سونا','نشانی مجموعه','بازگشت','تنظیم خبرها','لغو ارسال','عضویت در خبرها','توقف خبرها','علاقه‌مندی‌ها','پیش‌نمایش ارسال','اعضای بات','همه اعضا و گروه‌ها'}
        controls.update(store.config.get('interests', []))
        if (text and not text.startswith('/') and text not in controls and not text.startswith(('تأیید ارسال ', 'گروه ', '✅ '))) or msg.get('photo') or msg.get('video'):
            execute('INSERT OR REPLACE INTO broadcast_drafts VALUES (?,?,?,?,?,?)',(OWNER,'content','{}','[]','',time.time()+3600))
            draft=execute('SELECT * FROM broadcast_drafts WHERE owner=?',(OWNER,)).fetchone()
        else:return False
    if text in ('لغو ارسال','بازگشت','/cancel','/start','/menu') or draft['expires']<time.time():
        execute('DELETE FROM broadcast_drafts WHERE owner=?',(OWNER,));clear_previews()
        if text in ('/start','/menu','بازگشت'):return False
        say('پیش‌نویس ارسال لغو شد.');return True
    if draft['stage']!='content' and json.loads(draft['payload']).get('_version')!=2:
        execute('DELETE FROM broadcast_drafts WHERE owner=?',(OWNER,));clear_previews()
        say('ارسال مشترک تلگرام و بله فعال شده؛ برای انتخاب دقیق مخاطبان، پیام را دوباره بفرست.');return True
    if draft['stage']=='content':
        if msg.get('media_group_id') or not (msg.get('text') or msg.get('photo') or msg.get('video')):
            say('متن، یک عکس یا یک ویدئوی کوتاه همراه کپشن بفرست؛ آلبوم پشتیبانی نمی‌شود.',[['لغو ارسال']]);return True
        if msg.get('photo'):
            payload={'method':'sendPhoto','photo':msg['photo'][-1]['file_id'],'caption':msg.get('caption',''),'caption_entities':msg.get('caption_entities',[])}
        elif msg.get('video'):
            video=msg['video']
            if video.get('file_size',0)>20*1024*1024:
                say('حجم ویدئو باید حداکثر ۲۰ مگابایت باشد تا در تلگرام و بله فرستاده شود.',[['لغو ارسال']]);return True
            payload={'method':'sendVideo','video':video['file_id'],'caption':msg.get('caption',''),'caption_entities':msg.get('caption_entities',[])}
        else:payload={'method':'sendMessage','text':msg['text'],'entities':msg.get('entities',[])}
        if len(payload.get('text',payload.get('caption','')).encode('utf-16-le'))//2 > (4096 if payload['method']=='sendMessage' else 1024):
            say('متن باید حداکثر ۴۰۹۶ و کپشن عکس یا ویدئو حداکثر ۱۰۲۴ نویسه باشد.',[['لغو ارسال']]);return True
        payload.update({'_version':2,'_source_platform':platform})
        execute("UPDATE broadcast_drafts SET stage='targets',payload=? WHERE owner=?",(json.dumps(payload),OWNER))
    elif draft['stage']=='confirm':
        if text!='تأیید ارسال '+draft['nonce']:
            say('برای ارسال فقط دکمه تأیید همین پیش‌نویس را بزن؛ یا لغو ارسال.',[['تأیید ارسال '+draft['nonce']],['لغو ارسال']]);return True
        targets=json.loads(draft['targets']);payload=json.loads(draft['payload']);recipients=[]
        if 'members' in targets:
            recipients.extend((r['platform'],r['chat'],0) for r in db.execute("SELECT platform,chat FROM members WHERE subscribed=1 AND platform IN ('telegram','bale')"))
        for p in OWNERS:
            recipients.extend((p,r[0],1) for r in db.execute('SELECT chat FROM '+destination_table(p)+' WHERE active=1') if p+':'+str(r[0]) in targets)
        if not recipients:say('مخاطب فعالی باقی نمانده؛ ارسال انجام نشد.');return True
        campaign=execute("INSERT INTO campaigns(body,segment,status) VALUES (?,'all','queued')",(payload.get('text',payload.get('caption','[رسانه]')),)).lastrowid
        execute('INSERT INTO broadcast_runs VALUES (?,?)',(campaign,OWNER))
        for target_platform,target,is_group in recipients:
            data={k:v for k,v in payload.items() if k!='method' and not k.startswith('_')}
            if target_platform!=platform:
                for field in ('entities','caption_entities'):
                    if field in data: data[field]=[e for e in data[field] if e.get('type') not in ('text_mention','custom_emoji')]
                if payload['method'] in ('sendPhoto','sendVideo'):data['_media_source']=platform
            markup={}
            execute('INSERT INTO outbox(platform,chat,body,markup,campaign,method,payload,destination) VALUES (?,?,?,?,?,?,?,?)',(target_platform,target,data.get('text',data.get('caption','')),json.dumps(markup),campaign,payload['method'],json.dumps(data),is_group))
        execute('DELETE FROM broadcast_drafts WHERE owner=?',(OWNER,));clear_previews()
        say('ارسال #%s برای %s مقصد در صف قرار گرفت. «گزارش ارسال» نتیجه را نشان می‌دهد؛ تحویل پیام‌رسان به معنای خوانده‌شدن نیست.'%(campaign,len(recipients)));return True
    else:
        targets=json.loads(draft['targets']);choices=target_choices();by_name=dict(choices)
        key=text.removeprefix('✅ ') if hasattr(text,'removeprefix') else (text[2:] if text.startswith('✅ ') else text)
        if key == 'همه اعضا و گروه‌ها':
            targets=[value for name,value in choices]
            execute('UPDATE broadcast_drafts SET targets=? WHERE owner=?',(json.dumps(targets),OWNER))
        elif key in by_name:
            target=by_name[key];targets.remove(target) if target in targets else targets.append(target)
            execute('UPDATE broadcast_drafts SET targets=? WHERE owner=?',(json.dumps(targets),OWNER))
        if text=='پیش‌نمایش ارسال' or key=='همه اعضا و گروه‌ها':
            if not targets:say('حداقل یک مقصد انتخاب کن.',[[name] for name,_ in choices]+[['لغو ارسال']]);return True
            payload=json.loads(draft['payload']);nonce=secrets.token_hex(3)
            execute("UPDATE broadcast_drafts SET stage='confirm',nonce=? WHERE owner=?",(nonce,OWNER))
            clear_previews()
            execute('INSERT INTO outbox(platform,chat,body,markup,method,payload) VALUES (?,?,?,?,?,?)',(platform,ident,'','{}',payload['method'],json.dumps({k:v for k,v in payload.items() if k!='method' and not k.startswith('_')})))
            count='، '.join(LABELS[p]+': '+str(db.execute('SELECT COUNT(*) FROM members WHERE platform=? AND subscribed=1',(p,)).fetchone()[0]) for p in OWNERS)
            names=[('اعضای هر دو بات تلگرام و بله' if value=='members' else name) for name,value in choices if value in targets]
            say('پیش‌نمایش بالا فقط برای توست.\nمقصدها: '+ '، '.join(names)+('\nاعضای فعال خبرها: '+str(count) if 'members' in targets else '')+'\nتأیید، ارسال واقعی را شروع می‌کند.',[['تأیید ارسال '+nonce],['لغو ارسال']]);return True
    draft=execute('SELECT * FROM broadcast_drafts WHERE owner=?',(OWNER,)).fetchone();targets=json.loads(draft['targets']);choices=target_choices()
    selected=[name for name,value in choices if value in targets]
    if selected:
        prompt='انتخاب ثبت شد: '+ '، '.join(selected)+'\nبرای رفتن به مرحله تأیید، «پیش‌نمایش ارسال» را بزن. برای تغییر انتخاب می‌توانی گزینه‌های دیگر را هم بزنی.'
    else:
        prompt='اعضای بات یعنی اعضای تلگرام و بله.\nاین پیام کجا منتشر شود؟ «همه اعضا و گروه‌ها» مستقیم پیش‌نمایش را باز می‌کند؛ یا مخاطبان دلخواه را انتخاب کن و «پیش‌نمایش ارسال» را بزن.'
    if len(choices)==1:
        prompt+='\nفعلاً هیچ گروهی در این سرور شناسایی نشده؛ ارسال فقط به اعضای بات خواهد بود.'
    say(prompt,[[('✅ ' if value in targets else '')+name] for name,value in choices]+[['همه اعضا و گروه‌ها'],['پیش‌نمایش ارسال'],['لغو ارسال']]);return True
