"""Owner-only Telegram/Bale broadcast composer; all changes share Store's transaction."""
import json
import time
OWNER = 92655562
LABELS = {'telegram':'تلگرام', 'bale':'بله'}
OWNERS = {"telegram": OWNER, "bale": 1984558572}

def destination_table(platform):
    return "bale_destinations" if platform == "bale" else "destinations"
ADMIN = [['ارسال همگانی', 'گزارش ارسال'], ['مقصدهای ارسال', 'بازگشت']]
AUDIENCE = [['ارسال به همهٔ اعضا و گروه‌ها'], ['ارسال فقط به اعضای بات'], ['ارسال به همهٔ گروه‌ها'], ['انتخاب گروه‌ها'], ['تغییر پیام', 'لغو ارسال']]

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
    def publish(targets, payload):
        recipients=[]
        if 'members' in targets:
            recipients.extend((r['platform'],r['chat'],0) for r in db.execute("SELECT platform,chat FROM members WHERE subscribed=1 AND platform IN ('telegram','bale')"))
        for p in OWNERS:
            recipients.extend((p,r[0],1) for r in db.execute('SELECT chat FROM '+destination_table(p)+' WHERE active=1') if p+':'+str(r[0]) in targets)
        if not recipients:
            say('مخاطب فعالی برای این انتخاب پیدا نشد؛ چیزی منتشر نشد.',AUDIENCE)
            return True
        campaign=execute("INSERT INTO campaigns(body,segment,status) VALUES (?,'all','queued')",(payload.get('text',payload.get('caption','[رسانه]')),)).lastrowid
        execute('INSERT INTO broadcast_runs VALUES (?,?)',(campaign,OWNER))
        for target_platform,target,is_group in recipients:
            data={k:v for k,v in payload.items() if k!='method' and not k.startswith('_')}
            if target_platform!=platform:
                for field in ('entities','caption_entities'):
                    if field in data: data[field]=[e for e in data[field] if e.get('type') not in ('text_mention','custom_emoji')]
                if payload['method'] in ('sendPhoto','sendVideo'):data['_media_source']=platform
            execute('INSERT INTO outbox(platform,chat,body,markup,campaign,method,payload,destination) VALUES (?,?,?,?,?,?,?,?)',(target_platform,target,data.get('text',data.get('caption','')),'{}',campaign,payload['method'],json.dumps(data),is_group))
        execute('DELETE FROM broadcast_drafts WHERE owner=?',(OWNER,))
        clear_previews()
        say('ارسال به %s مقصد شروع شد. نتیجه را در «گزارش ارسال» ببین.'%len(recipients))
        return True
    def group_menu(targets, choices):
        buttons=[[('✅ ' if value in targets else '')+name] for name,value in choices]
        buttons.extend([['ارسال به انتخاب‌شده‌ها'],['بازگشت به مقصدها'],['تغییر پیام', 'لغو ارسال']])
        return buttons
    def audience_menu():
        return AUDIENCE
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
        clear_previews()
        say('پیامی را که می‌خواهی منتشر شود بفرست: متن، یک عکس یا یک ویدئوی کوتاه همراه کپشن. ویدئو حداکثر ۲۰ مگابایت باشد.',[['لغو ارسال']]);return True
    draft=execute('SELECT * FROM broadcast_drafts WHERE owner=?',(OWNER,)).fetchone()
    if not draft:
        admin_controls = {'لغو ارسال','پیش‌نمایش ارسال','اعضای بات','همه اعضا و گروه‌ها','ارسال به همهٔ اعضا و گروه‌ها','ارسال فقط به اعضای بات','ارسال به همهٔ گروه‌ها','انتخاب گروه‌ها','ارسال به انتخاب‌شده‌ها','بازگشت به مقصدها','تغییر پیام'}
        if text in admin_controls or text.startswith(('تأیید ارسال ', 'گروه ', '✅ ')):
            return True
        controls = {'بدنسازی','استخر و سونا','نشانی مجموعه','بازگشت','تنظیم خبرها','عضویت در خبرها','توقف خبرها','علاقه‌مندی‌ها'}
        controls.update(store.config.get('interests', []))
        if (text and not text.startswith('/') and text not in controls) or msg.get('photo') or msg.get('video'):
            execute('INSERT OR REPLACE INTO broadcast_drafts VALUES (?,?,?,?,?,?)',(OWNER,'content','{}','[]','',time.time()+3600))
            draft=execute('SELECT * FROM broadcast_drafts WHERE owner=?',(OWNER,)).fetchone()
        else:return False
    if text in ('لغو ارسال','بازگشت','/cancel','/start','/menu') or draft['expires']<time.time():
        execute('DELETE FROM broadcast_drafts WHERE owner=?',(OWNER,));clear_previews()
        if text in ('/start','/menu','بازگشت'):return False
        say('پیش‌نویس ارسال لغو شد.');return True
    if draft['stage'] not in ('content','targets','groups') or (draft['stage']!='content' and json.loads(draft['payload']).get('_version')!=3):
        execute('DELETE FROM broadcast_drafts WHERE owner=?',(OWNER,));clear_previews()
        say('روش ارسال ساده‌تر شده است؛ پیام را دوباره بفرست تا مقصدش را انتخاب کنی.');return True
    if text=='تغییر پیام':
        execute("UPDATE broadcast_drafts SET stage='content',payload='{}',targets='[]' WHERE owner=?",(OWNER,))
        say('پیام تازه را بفرست.',[['لغو ارسال']])
        return True
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
        payload.update({'_version':3,'_source_platform':platform})
        execute("UPDATE broadcast_drafts SET stage='targets',payload=? WHERE owner=?",(json.dumps(payload),OWNER))
        groups=len(target_choices())-1
        prompt=('پیام آماده است. کجا منتشر شود؟\n«همه» یعنی اعضای هر دو بات و %s گروه ثبت‌شده. دکمهٔ ارسال، انتشار را شروع می‌کند.'%groups if groups else 'پیام آماده است. هنوز گروهی ثبت نشده؛ گزینه‌های مربوط به گروه تا ثبت گروه، چیزی منتشر نمی‌کنند.')
        say(prompt,audience_menu())
        return True
    payload=json.loads(draft['payload'])
    if draft['stage']=='targets':
        groups=[value for _,value in target_choices() if value!='members']
        if text=='ارسال به همهٔ اعضا و گروه‌ها':
            if not groups:
                say('هنوز گروهی در مقصدهای ارسال ثبت نشده؛ چیزی منتشر نشد. برای ارسال به اعضای بات، گزینهٔ مخصوص آن را بزن.',audience_menu())
                return True
            return publish(['members']+groups,payload)
        if text=='ارسال فقط به اعضای بات':
            return publish(['members'],payload)
        if text=='ارسال به همهٔ گروه‌ها':
            if not groups:
                say('هنوز گروهی در مقصدهای ارسال ثبت نشده؛ چیزی منتشر نشد.',audience_menu())
                return True
            return publish(groups,payload)
        if text=='انتخاب گروه‌ها':
            execute("UPDATE broadcast_drafts SET stage='groups',targets='[]' WHERE owner=?",(OWNER,))
            choices=target_choices()
            say('مقصدهای دلخواه را انتخاب کن؛ سپس «ارسال به انتخاب‌شده‌ها» را بزن. گزینهٔ «اعضای بات» شامل تلگرام و بله است.',group_menu([],choices))
            return True
        say('یکی از مقصدها را انتخاب کن. تا انتخاب دکمهٔ ارسال، چیزی منتشر نمی‌شود.',audience_menu())
        return True
    choices=target_choices();by_name=dict(choices);targets=json.loads(draft['targets'])
    if text=='بازگشت به مقصدها':
        execute("UPDATE broadcast_drafts SET stage='targets',targets='[]' WHERE owner=?",(OWNER,))
        say('کجا منتشر شود؟',audience_menu())
        return True
    if text=='ارسال به انتخاب‌شده‌ها':
        if not targets:
            say('هنوز مقصدی انتخاب نکرده‌ای.',group_menu(targets,choices))
            return True
        return publish(targets,payload)
    key=text[2:] if text.startswith('✅ ') else text
    if key in by_name:
        target=by_name[key]
        targets.remove(target) if target in targets else targets.append(target)
        execute('UPDATE broadcast_drafts SET targets=? WHERE owner=?',(json.dumps(targets),OWNER))
        say('%s مقصد انتخاب شده. برای انتشار «ارسال به انتخاب‌شده‌ها» را بزن.'%len(targets),group_menu(targets,choices))
        return True
    say('مقصدهای دلخواه را انتخاب کن.',group_menu(targets,choices))
    return True
