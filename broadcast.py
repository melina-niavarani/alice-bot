"""Owner-only Telegram/Bale broadcast composer; all changes share Store's transaction."""
import json
import secrets
import time
OWNER = 92655562
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
    if chat.get('type')!='private':
        if owner and chat.get('type') in ('group','supergroup') and command in ('/connect','/disconnect'):
            execute('INSERT INTO destinations(chat,title,active) VALUES (?,?,?) ON CONFLICT(chat) DO UPDATE SET title=excluded.title,active=excluded.active',(ident,chat.get('title','گروه آلیس'),int(command=='/connect')))
            say('این گروه به مقصدهای مجاز آلیس اضافه شد.' if command=='/connect' else 'ارسال به این گروه غیرفعال شد.',None)
        return True
    if not owner or ident != OWNER:return False
    if command=='/admin' or text in ('مدیریت ارسال','مقصدهای ارسال'):
        rows=execute('SELECT * FROM destinations WHERE active=1').fetchall()
        say('مدیریت ارسال آلیس\nپیام یا عکس را مستقیم همین‌جا بفرست؛ سپس انتخاب کن کجا منتشر شود. گروه‌هایی که بات به آن‌ها اضافه شود، خودکار شناسایی می‌شوند.\n\nگروه‌های مجاز:\n'+('\n'.join(r['title'] for r in rows) or 'هنوز گروهی ثبت نشده.'));return True
    if text=='گزارش ارسال' or command=='/report':
        runs=execute('SELECT campaign FROM broadcast_runs WHERE owner=? ORDER BY campaign DESC LIMIT 5',(OWNER,)).fetchall()
        labels={'sent':'تحویل پیام‌رسان','pending':'در صف','sending':'در حال ارسال','failed':'ناموفق','unknown':'نتیجه نامشخص','skipped':'لغوشده'}
        lines=[]
        for run in runs:
            counts=execute('SELECT status,COUNT(*) n FROM outbox WHERE campaign=? GROUP BY status',(run[0],)).fetchall()
            lines.append('#%s: '%run[0]+' · '.join(labels.get(r['status'],r['status'])+': '+str(r['n']) for r in counts))
        say('\n'.join(lines) or 'هنوز ارسال همگانی ثبت نشده.');return True
    if text=='ارسال همگانی' or command=='/broadcast':
        execute('INSERT OR REPLACE INTO broadcast_drafts VALUES (?,?,?,?,?,?)',(OWNER,'content','{}','[]','',time.time()+3600))
        say('متن یا یک عکس همراه کپشن بفرست. آلبوم را به یک عکس تبدیل کن. تا انتخاب مقصد و تأیید نهایی هیچ پیامی منتشر نمی‌شود.',[['لغو ارسال']]);return True
    draft=execute('SELECT * FROM broadcast_drafts WHERE owner=?',(OWNER,)).fetchone()
    if not draft:
        controls = {'بدنسازی','استخر و سونا','نشانی مجموعه','بازگشت','تنظیم خبرها','لغو ارسال','عضویت در خبرها','توقف خبرها','علاقه‌مندی‌ها','پیش‌نمایش ارسال','اعضای بات'}
        controls.update(store.config.get('interests', []))
        if (text and not text.startswith('/') and text not in controls and not text.startswith(('تأیید ارسال ', 'گروه ', '✅ '))) or msg.get('photo'):
            execute('INSERT OR REPLACE INTO broadcast_drafts VALUES (?,?,?,?,?,?)',(OWNER,'content','{}','[]','',time.time()+3600))
            draft=execute('SELECT * FROM broadcast_drafts WHERE owner=?',(OWNER,)).fetchone()
        else:return False
    if text in ('لغو ارسال','بازگشت','/cancel','/start','/menu') or draft['expires']<time.time():
        execute('DELETE FROM broadcast_drafts WHERE owner=?',(OWNER,))
        if text in ('/start','/menu','بازگشت'):return False
        say('پیش‌نویس ارسال لغو شد.');return True
    if draft['stage']=='content':
        if msg.get('media_group_id') or not (msg.get('text') or msg.get('photo')):
            say('یک متن یا یک عکس همراه کپشن بفرست؛ آلبوم پشتیبانی نمی‌شود.',[['لغو ارسال']]);return True
        if msg.get('photo'):
            payload={'method':'sendPhoto','photo':msg['photo'][-1]['file_id'],'caption':msg.get('caption',''),'caption_entities':msg.get('caption_entities',[])}
        else:payload={'method':'sendMessage','text':msg['text'],'entities':msg.get('entities',[])}
        execute("UPDATE broadcast_drafts SET stage='targets',payload=? WHERE owner=?",(json.dumps(payload),OWNER))
    elif draft['stage']=='confirm':
        if text!='تأیید ارسال '+draft['nonce']:
            say('برای ارسال فقط دکمه تأیید همین پیش‌نویس را بزن؛ یا لغو ارسال.',[['تأیید ارسال '+draft['nonce']],['لغو ارسال']]);return True
        targets=json.loads(draft['targets']);payload=json.loads(draft['payload']);recipients=[]
        if 'members' in targets:
            recipients.extend((r[0],0) for r in execute("SELECT chat FROM members WHERE platform=? AND subscribed=1", (platform,)))
        recipients.extend((r[0],1) for r in execute('SELECT chat FROM destinations WHERE active=1') if str(r[0]) in targets)
        if not recipients:say('مخاطب فعالی باقی نمانده؛ ارسال انجام نشد.');return True
        campaign=execute("INSERT INTO campaigns(body,segment,status) VALUES (?,'all','queued')",(payload.get('text',payload.get('caption','[عکس]')),)).lastrowid
        execute('INSERT INTO broadcast_runs VALUES (?,?)',(campaign,OWNER))
        for target,is_group in recipients:
            data={k:v for k,v in payload.items() if k!='method'}
            markup={}
            execute('INSERT INTO outbox(platform,chat,body,markup,campaign,method,payload,destination) VALUES (?,?,?,?,?,?,?,?)',(platform,target,data.get('text',data.get('caption','')),json.dumps(markup),campaign,payload['method'],json.dumps(data),is_group))
        execute('DELETE FROM broadcast_drafts WHERE owner=?',(OWNER,))
        say('ارسال #%s برای %s مقصد در صف قرار گرفت. «گزارش ارسال» نتیجه را نشان می‌دهد؛ تحویل پیام‌رسان به معنای خوانده‌شدن نیست.'%(campaign,len(recipients)));return True
    else:
        targets=json.loads(draft['targets'])
        choices={'اعضای بات':'members'}
        choices.update({'گروه '+str(r['chat'])+' · '+r['title'][:35]:str(r['chat']) for r in execute('SELECT * FROM destinations WHERE active=1')})
        key=text.removeprefix('✅ ') if hasattr(text,'removeprefix') else (text[2:] if text.startswith('✅ ') else text)
        if key == 'همه اعضا و گروه‌ها':
            targets=list(choices.values())
            execute('UPDATE broadcast_drafts SET targets=? WHERE owner=?',(json.dumps(targets),OWNER))
        elif key in choices:
            target=choices[key];targets.remove(target) if target in targets else targets.append(target)
            execute('UPDATE broadcast_drafts SET targets=? WHERE owner=?',(json.dumps(targets),OWNER))
        elif text=='پیش‌نمایش ارسال':
            if not targets:say('حداقل یک مقصد انتخاب کن.',[[x] for x in choices]+[['لغو ارسال']]);return True
            payload=json.loads(draft['payload']);nonce=secrets.token_hex(3)
            execute("UPDATE broadcast_drafts SET stage='confirm',nonce=? WHERE owner=?",(nonce,OWNER))
            execute('INSERT INTO outbox(platform,chat,body,markup,method,payload) VALUES (?,?,?,?,?,?)',(platform,ident,'','{}',payload['method'],json.dumps({k:v for k,v in payload.items() if k!='method'})))
            count=execute("SELECT COUNT(*) FROM members WHERE platform=? AND subscribed=1", (platform,)).fetchone()[0]
            names=[name for name,value in choices.items() if value in targets]
            say('پیش‌نمایش بالا فقط برای توست.\nمقصدها: '+ '، '.join(names)+('\nاعضای فعال خبرها: '+str(count) if 'members' in targets else '')+'\nتأیید، ارسال واقعی را شروع می‌کند.',[['تأیید ارسال '+nonce],['لغو ارسال']]);return True
    draft=execute('SELECT * FROM broadcast_drafts WHERE owner=?',(OWNER,)).fetchone();targets=json.loads(draft['targets'])
    choices=[('اعضای بات','members')]+[('گروه '+str(r['chat'])+' · '+r['title'][:35],str(r['chat'])) for r in execute('SELECT * FROM destinations WHERE active=1')]
    say('این پیام کجا منتشر شود؟ یک یا چند گزینه را بزن و بعد پیش‌نمایش ارسال را انتخاب کن.',[[('✅ ' if value in targets else '')+name] for name,value in choices]+[['همه اعضا و گروه‌ها'],['پیش‌نمایش ارسال'],['لغو ارسال']]);return True
