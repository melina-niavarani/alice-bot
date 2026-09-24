"""Content editor for Alice Mini App; credentials stay on the bot host."""
import html
import json
import os
from pathlib import Path
import re
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
CONTENT_FILE = ROOT / 'data' / 'miniapp-content.json'
DAYS = ['شنبه','یکشنبه','دوشنبه','سه‌شنبه','چهارشنبه','پنجشنبه','جمعه']

def default_content():
    cfg=json.loads((ROOT/'config.json').read_text())
    blank=lambda description:dict(description=description,singlePrice='',packagePrice='',rules='',sessions=[])
    services=json.loads((ROOT/'schedule.json').read_text(encoding='utf-8'))
    return dict(name=cfg['name'],greeting='سلام، به آلیس خوش آمدی.',address='تهران، تهرانپارس، خیابان شهید ملکی، نبش خیابان ۱۲۰، پلاک ۶',phone='',gym=services['gym'],pool=services['pool'],notices=[])

def read_content():
    return json.loads(CONTENT_FILE.read_text()) if CONTENT_FILE.exists() else default_content()

def parse_content(form):
    def val(k,limit):
        v=form.get(k,[''])[0].strip()
        if len(v)>limit: raise ValueError('متن یکی از بخش‌ها بیش از اندازه طولانی است.')
        return v
    result={k:val(k,n) for k,n in [('name',120),('greeting',300),('address',500),('phone',40)]}
    if not result['name']: raise ValueError('نام مجموعه را وارد کنید.')
    for kind in ['gym','pool']:
        service={k:val(kind+'_'+k,n) for k,n in [('description',2000),('singlePrice',80),('packagePrice',80),('rules',4000)]}
        sessions=[]
        rows=zip(form.get(kind+'_day',[]),form.get(kind+'_start',[]),form.get(kind+'_end',[]),form.get(kind+'_audience',[]))
        for day,start,end,audience in rows:
            if not start and not end: continue
            if day not in DAYS or not re.fullmatch(r'([01]\d|2[0-3]):[0-5]\d',start) or not re.fullmatch(r'([01]\d|2[0-3]):[0-5]\d',end): raise ValueError('روز و ساعت هر سانس را کامل وارد کنید.')
            if len(audience)>40: raise ValueError('عنوان مخاطبان سانس طولانی است.')
            sessions.append(dict(day=day,start=start,end=end,audience=audience.strip()))
        if len(sessions)>100: raise ValueError('حداکثر ۱۰۰ سانس قابل ثبت است.')
        service['sessions']=sessions;result[kind]=service
    notices=[]
    for title,body in zip(form.get('notice_title',[]),form.get('notice_body',[])):
        title,body=title.strip(),body.strip()
        if not title and not body: continue
        if not title or len(title)>160 or len(body)>1600: raise ValueError('عنوان و متن اطلاعیه را بررسی کنید.')
        notices.append(dict(title=title,body=body))
    if len(notices)>30: raise ValueError('حداکثر ۳۰ اطلاعیه قابل ثبت است.')
    result['notices']=notices
    return result

def save_content(content):
    CONTENT_FILE.parent.mkdir(mode=0o700,exist_ok=True)
    tmp=CONTENT_FILE.with_suffix('.tmp');tmp.write_text(json.dumps(content,ensure_ascii=False,indent=2));os.replace(tmp,CONTENT_FILE)

def publish_content(content):
    url=os.environ.get('MINIAPP_URL','').rstrip('/')
    key=os.environ.get('ALICE_CONTENT_KEY','')
    if not url.startswith('https://') or not key:
        return 'اطلاعات روی دستگاه ذخیره شد؛ اتصال انتشار آنلاین هنوز تنظیم نشده است.'
    body=json.dumps(content,ensure_ascii=False).encode()
    req=Request(url+'/api/content',data=body,method='PUT',headers={'Content-Type':'application/json','Authorization':'Bearer '+key})
    try:
        with urlopen(req,timeout=30) as r:
            answer=json.load(r)
            if answer.get('ok') is not True: raise ValueError()
    except Exception:
        return 'اطلاعات روی دستگاه ذخیره شد، اما انتشار آنلاین انجام نشد. پس از بررسی اتصال دوباره «ذخیره و انتشار» را بزنید.'
    return 'اطلاعات ذخیره و در مینی‌اپ منتشر شد.'

def editor(csrf,content=None,message=''):
    c=content or read_content();e=lambda x:html.escape(str(x),quote=True)
    def field(name,label,value,large=False):
        control=('<textarea name="%s">%s</textarea>' if large else '<input name="%s" value="%s">')%(e(name),e(value))
        return '<label>'+e(label)+'</label>'+control
    def session_row(kind,row=None):
        row=row or dict(day='شنبه',start='',end='',audience='')
        options=''.join('<option%s>%s</option>'%(' selected' if x==row['day'] else '',x) for x in DAYS)
        return '<div class="session-row"><label>روز<select name="'+kind+'_day">'+options+'</select></label><label>شروع<input type="time" name="'+kind+'_start" value="'+e(row['start'])+'"></label><label>پایان<input type="time" name="'+kind+'_end" value="'+e(row['end'])+'"></label><label>ویژه<input name="'+kind+'_audience" value="'+e(row['audience'])+'" placeholder="بانوان / آقایان"></label><button type="button" data-remove aria-label="حذف سانس">حذف</button></div>'
    def notice_row(n=None):
        n=n or dict(title='',body='')
        return '<div class="notice-row">'+field('notice_title','عنوان',n['title'])+field('notice_body','متن',n['body'],True)+'<button type="button" data-remove>حذف اطلاعیه</button></div>'
    out='<style>.session-row{display:grid;grid-template-columns:1fr 1fr 1fr 1.3fr auto;gap:8px;align-items:end;border-bottom:1px solid #ddd;padding:12px 0}.session-row label{font-size:14px}.notice-row{border-bottom:1px solid #ddd;padding:12px 0}button[data-remove]{background:#f2e8e8;color:#7c3232;font-size:14px}.editor-actions{position:sticky;bottom:0;background:#f3f5eff0;padding:14px 0}.help{font-size:14px;color:#61736a}@media(max-width:640px){.session-row{grid-template-columns:1fr 1fr}.session-row button{grid-column:2}}</style><p><a href="/">← بازگشت به مدیریت</a></p>'
    if message: out+='<p class="note" role="status">'+e(message)+'</p>'
    out+='<form method="post" action="/miniapp/save"><input type="hidden" name="csrf" value="'+csrf+'"><section class="card"><h2>اطلاعات مجموعه</h2>'
    for name,label in [('name','نام مجموعه'),('greeting','پیام خوشامد'),('address','نشانی'),('phone','شماره تماس')]: out+=field(name,label,c[name])
    out+='</section>'
    for kind,label in [('gym','بدنسازی'),('pool','استخر و سونا')]:
        s=c[kind];out+='<section class="card"><h2>'+label+'</h2>'
        for name,label2 in [('description','توضیح'),('singlePrice','تعرفه تک‌جلسه (با واحد تومان)'),('packagePrice','تعرفه پکیج / اشتراک (با واحد تومان)'),('rules','قوانین')]:out+=field(kind+'_'+name,label2,s[name],name in ['description','rules'])
        out+='<h3>برنامه سانس‌ها</h3><p class="help">ردیف‌های بدون ساعت منتشر نمی‌شوند. برای حذف سانس از دکمه حذف استفاده کنید.</p><div id="'+kind+'-rows">'+''.join(session_row(kind,r) for r in s['sessions'])+'</div><template id="'+kind+'-template">'+session_row(kind)+'</template><p><button type="button" data-add="'+kind+'">+ افزودن سانس</button></p></section>'
    out+='<section class="card"><h2>اطلاعیه‌ها و پیشنهادها</h2><div id="notice-rows">'+''.join(notice_row(n) for n in c['notices'])+'</div><template id="notice-template">'+notice_row()+'</template><p><button type="button" data-add="notice">+ افزودن اطلاعیه</button></p></section><div class="editor-actions"><button>ذخیره و انتشار در مینی‌اپ</button><p class="help">فقط محتوای عمومی مینی‌اپ تغییر می‌کند؛ پیامی برای اعضای بات ارسال نمی‌شود.</p></div></form>'
    out+='<script nonce="'+csrf+'">document.addEventListener("click",function(e){const a=e.target.closest("[data-add]");if(a){const k=a.dataset.add;document.getElementById(k+"-rows").appendChild(document.getElementById(k+"-template").content.cloneNode(true))}const r=e.target.closest("[data-remove]");if(r)r.parentElement.remove()});</script>'
    return out
