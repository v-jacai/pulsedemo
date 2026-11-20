"""Pulse local prototype. Python standard library only."""
import argparse
import email
import email.policy
import json
import mimetypes
import os
import re
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager, closing
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

ROOT = Path(__file__).resolve().parent
MAX_FILE = 10 * 1024 * 1024
USERS = [
    ('am23456', 'Alex Morgan', 'Trade Capture Technology'),
    ('sc12345', 'Sarah Chen', 'Markets Risk Technology'),
    ('dl34567', 'Daniel Lee', 'Application Support'),
    ('mb45678', 'Michael Brown', 'Infrastructure Technology'),
    ('jp56789', 'Jamie Patel', 'Market Data Support'),
    ('lw67890', 'Lisa Wong', 'Operations Control'),
]
SEVERITIES = ('Critical', 'High', 'Medium', 'Low', 'Info')
EXTENSIONS = {'.eml', '.msg', '.pdf', '.png', '.jpg', '.jpeg', '.txt', '.log', '.csv', '.xlsx', '.json'}


def now():
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds')


class APIError(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message


class Store:
    def __init__(self, path):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.changed = threading.Condition()
        with closing(sqlite3.connect(self.path)) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY, name TEXT NOT NULL, team TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS alerts(id TEXT PRIMARY KEY, title TEXT NOT NULL, description TEXT NOT NULL,
                    severity TEXT NOT NULL, application TEXT NOT NULL, environment TEXT NOT NULL,
                    status TEXT NOT NULL, owner TEXT REFERENCES users(id), created TEXT NOT NULL,
                    resolved TEXT, resolution TEXT, creator TEXT REFERENCES users(id));
                CREATE TABLE IF NOT EXISTS members(alert_id TEXT REFERENCES alerts(id), user_id TEXT REFERENCES users(id),
                    PRIMARY KEY(alert_id,user_id));
                CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY AUTOINCREMENT, alert_id TEXT REFERENCES alerts(id),
                    author TEXT REFERENCES users(id), body TEXT NOT NULL, created TEXT NOT NULL, mentions TEXT NOT NULL DEFAULT '[]');
                CREATE TABLE IF NOT EXISTS attachments(id TEXT PRIMARY KEY, message_id INTEGER REFERENCES messages(id),
                    name TEXT NOT NULL, mime TEXT NOT NULL, size INTEGER NOT NULL, data BLOB NOT NULL, preview TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS activity(id INTEGER PRIMARY KEY AUTOINCREMENT, alert_id TEXT REFERENCES alerts(id),
                    actor TEXT REFERENCES users(id), action TEXT NOT NULL, detail TEXT NOT NULL, created TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT REFERENCES users(id),
                    alert_id TEXT REFERENCES alerts(id), kind TEXT NOT NULL, actor TEXT REFERENCES users(id),
                    payload TEXT NOT NULL, created TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS events_user_id ON events(user_id,id);
                CREATE INDEX IF NOT EXISTS messages_alert ON messages(alert_id,id);
                CREATE INDEX IF NOT EXISTS activity_alert ON activity(alert_id,id);
                CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
            ''')
            db.executemany('INSERT OR IGNORE INTO users VALUES(?,?,?)', USERS)
            if not db.execute("SELECT 1 FROM meta WHERE key='seeded'").fetchone():
                t=now()
                db.execute('INSERT INTO alerts VALUES(?,?,?,?,?,?,?,?,?,?,?,?)', ('ALT-0001','Pricing API latency exceeded','Pricing response time exceeded the 500 ms threshold.','High','Pricing Service','Production','Resolved','sc12345',t,t,'Restarted the affected pricing worker and verified normal latency.','am23456'))
                db.executemany('INSERT INTO members VALUES(?,?)', [('ALT-0001',u[0]) for u in USERS[:3]])
                self.activity(db,'ALT-0001','am23456','Created','Monitoring rule triggered.'); self.activity(db,'ALT-0001','sc12345','Claimed','Sarah Chen took ownership.'); self.activity(db,'ALT-0001','sc12345','Resolved','Restarted the affected worker and verified normal latency.')
                db.execute('INSERT INTO messages(alert_id,author,body,created) VALUES(?,?,?,?)',('ALT-0001','sc12345','Pricing latency is back within the expected range.',t))
                db.execute("INSERT INTO meta VALUES('seeded','1')")

    @contextmanager
    def connect(self, write=False):
        db=sqlite3.connect(self.path, timeout=10, isolation_level=None)
        db.row_factory=sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('PRAGMA busy_timeout=10000')
        try:
            db.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
            yield db
            db.commit()
        except Exception:
            db.rollback(); raise
        finally:
            db.close()

    def user(self, db, user):
        row=db.execute('SELECT * FROM users WHERE id=?',(user,)).fetchone()
        if not row: raise APIError(400,'Choose a valid demo user.')
        return dict(row)

    def require(self, db, user, aid):
        self.user(db,user)
        row=db.execute('SELECT a.* FROM alerts a JOIN members m ON a.id=m.alert_id WHERE a.id=? AND m.user_id=?',(aid,user)).fetchone()
        if not row: raise APIError(404,'Alert not found for this user.')
        return dict(row)

    def activity(self, db, aid, actor, action, detail):
        db.execute('INSERT INTO activity(alert_id,actor,action,detail,created) VALUES(?,?,?,?,?)',(aid,actor,action,detail,now()))

    def emit(self, db, aid, kind, actor, payload=None, targets=None):
        if targets is None: targets=[r[0] for r in db.execute('SELECT user_id FROM members WHERE alert_id=?',(aid,))]
        db.executemany('INSERT INTO events(user_id,alert_id,kind,actor,payload,created) VALUES(?,?,?,?,?,?)', [(u,aid,kind,actor,json.dumps(payload or {}),now()) for u in dict.fromkeys(targets)])

    def wake(self):
        with self.changed: self.changed.notify_all()

    def directory(self):
        with self.connect() as db: return [dict(r) for r in db.execute('SELECT * FROM users ORDER BY name')]

    def snapshot(self,user):
        with self.connect() as db:
            me=self.user(db,user)
            cursor=db.execute('SELECT COALESCE(MAX(id),0) FROM events WHERE user_id=?',(user,)).fetchone()[0]
            alerts=[dict(r) for r in db.execute('''SELECT a.*,u.name AS owner_name,
                (SELECT COUNT(*) FROM messages WHERE alert_id=a.id) AS message_count,
                (SELECT COUNT(*) FROM members WHERE alert_id=a.id) AS member_count
                FROM alerts a JOIN members m ON a.id=m.alert_id LEFT JOIN users u ON u.id=a.owner
                WHERE m.user_id=? ORDER BY a.created DESC,a.id DESC''',(user,))]
            return {'user':me,'cursor':cursor,'alerts':alerts}

    def detail(self,user,aid):
        with self.connect() as db:
            a=self.require(db,user,aid)
            a['owner_name']=self.user(db,a['owner'])['name'] if a['owner'] else None
            a['members']=[dict(r) for r in db.execute('SELECT u.* FROM users u JOIN members m ON u.id=m.user_id WHERE m.alert_id=? ORDER BY u.name',(aid,))]
            a['messages']=[]
            for r in db.execute('SELECT m.*,u.name AS author_name FROM messages m JOIN users u ON u.id=m.author WHERE alert_id=? ORDER BY m.id',(aid,)):
                msg=dict(r); msg['mentions']=json.loads(msg['mentions']); msg['attachments']=[dict(x) for x in db.execute('SELECT id,name,mime,size,preview FROM attachments WHERE message_id=?',(msg['id'],))]; a['messages'].append(msg)
            a['activity']=[dict(r) for r in db.execute('SELECT l.*,u.name AS actor_name FROM activity l LEFT JOIN users u ON u.id=l.actor WHERE alert_id=? ORDER BY l.id',(aid,))]
            return a

    def events(self,user,after):
        with self.connect() as db:
            self.user(db,user)
            rows=[dict(r) for r in db.execute('SELECT * FROM events WHERE user_id=? AND id>? ORDER BY id LIMIT 200',(user,after))]
            for r in rows: r['payload']=json.loads(r['payload'])
            return rows

    def create(self,user,data):
        def field(key,default,maxlen):
            val=data.get(key,default)
            if not isinstance(val,str) or not val.strip() or len(val)>maxlen: raise APIError(400,f'Invalid {key}.')
            return val.strip()
        title=field('title','',160); description=field('description','',4000); severity=field('severity','High',20)
        app=field('application','Trade Capture',100); env=field('environment','Production',60)
        if severity not in SEVERITIES: raise APIError(400,'Invalid severity.')
        recipients=data.get('recipients',[])
        if not isinstance(recipients,list) or not recipients or any(not isinstance(u,str) for u in recipients): raise APIError(400,'Select at least one subscriber.')
        recipients=list(dict.fromkeys(recipients))
        with self.connect(True) as db:
            self.user(db,user)
            for u in recipients: self.user(db,u)
            aid='ALT-'+uuid.uuid4().hex[:10].upper()
            db.execute('INSERT INTO alerts VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(aid,title,description,severity,app,env,'Unassigned',None,now(),None,None,user))
            db.executemany('INSERT INTO members VALUES(?,?)',[(aid,u) for u in recipients])
            self.activity(db,aid,user,'Created',f'Monitoring rule triggered; {len(recipients)} subscriber(s) notified.')
            self.emit(db,aid,'alert_created',user,{'title':title,'severity':severity},recipients)
        self.wake(); return {'id':aid,'recipients':recipients}

    def action(self,user,aid,data):
        action=data.get('action')
        with self.connect(True) as db:
            a=self.require(db,user,aid); me=self.user(db,user)
            if action=='claim':
                if a['status']!='Unassigned': raise APIError(409,'This alert is no longer unassigned. Refreshing the current owner.')
                db.execute("UPDATE alerts SET status='In progress',owner=? WHERE id=?",(user,aid))
                self.activity(db,aid,user,'Claimed',f"{me['name']} took ownership.")
            elif action=='resolve':
                if a['status']!='In progress' or a['owner']!=user: raise APIError(409,'Only the current owner can resolve an active alert.')
                note=data.get('resolution','')
                if not isinstance(note,str) or not note.strip() or len(note)>4000: raise APIError(400,'A resolution summary is required (max 4000 characters).')
                db.execute("UPDATE alerts SET status='Resolved',resolved=?,resolution=? WHERE id=?",(now(),note.strip(),aid))
                self.activity(db,aid,user,'Resolved',note.strip())
            elif action=='release':
                if a['status']!='In progress' or a['owner']!=user: raise APIError(409,'Only the current owner can release this alert.')
                db.execute("UPDATE alerts SET status='Unassigned',owner=NULL WHERE id=?",(aid,))
                self.activity(db,aid,user,'Released',f"{me['name']} released ownership.")
            else: raise APIError(400,'Unknown action.')
            self.emit(db,aid,'state',user,{'action':action})
        self.wake(); return self.detail(user,aid)

    def add_people(self,user,aid,data):
        targets=data.get('users')
        if not isinstance(targets,list) or not targets or any(not isinstance(u,str) for u in targets): raise APIError(400,'Select at least one colleague.')
        with self.connect(True) as db:
            self.require(db,user,aid); me=self.user(db,user); added=[]
            for target in dict.fromkeys(targets):
                p=self.user(db,target)
                if db.execute('INSERT OR IGNORE INTO members VALUES(?,?)',(aid,target)).rowcount:
                    added.append(target); self.activity(db,aid,user,'Invited',f"{me['name']} invited {p['name']} ({target}).")
            if added:
                self.emit(db,aid,'update',user)
                self.emit(db,aid,'invited',user,{'sender':me['name'],'text':'You have been invited to this alert discussion.'},added)
        self.wake(); return {'added':added}

    def message(self,user,aid,data):
        body=data.get('body','')
        if not isinstance(body,str) or not body.strip() or len(body)>8000: raise APIError(400,'Enter a message (max 8000 characters).')
        body=body.strip()
        with self.connect(True) as db:
            self.require(db,user,aid); me=self.user(db,user)
            candidates=list(dict.fromkeys(re.findall(r'(?<![\w@])@([a-zA-Z0-9_]+)\b',body.lower())))
            mentions=[p for p in candidates if p!=user and db.execute('SELECT 1 FROM users WHERE id=?',(p,)).fetchone()]
            mid=db.execute('INSERT INTO messages(alert_id,author,body,created,mentions) VALUES(?,?,?,?,?)',(aid,user,body,now(),json.dumps(mentions))).lastrowid
            for target in mentions:
                if db.execute('INSERT OR IGNORE INTO members VALUES(?,?)',(aid,target)).rowcount:
                    self.activity(db,aid,user,'Invited',f"{me['name']} added {self.user(db,target)['name']} via @mention.")
            self.emit(db,aid,'update',user)
            if mentions: self.emit(db,aid,'mention',user,{'sender':me['name'],'text':body,'message_id':mid},mentions)
        self.wake(); return {'id':mid,'mentions':mentions}

    def upload(self,user,aid,name,data):
        name=Path(name.replace('\\','/')).name
        ext=Path(name).suffix.lower()
        if not name or len(name)>200 or ext not in EXTENSIONS or any(ord(c)<32 for c in name): raise APIError(400,'Unsupported file type or invalid filename.')
        if not data or len(data)>MAX_FILE: raise APIError(400,'File must be between 1 byte and 10 MB.')
        preview={}
        if ext=='.eml':
            try:
                msg=email.message_from_bytes(data,policy=email.policy.default)
                preview={k:str(msg.get(k,''))[:500] for k in ('Subject','From','To','Date')}
                part=msg.get_body(preferencelist=('plain',)) if msg.is_multipart() else msg
                if part and part.get_content_type()=='text/plain': preview['Body']=str(part.get_content())[:1200]
            except Exception: preview={'Note':'Email preview unavailable; download the original.'}
        elif ext=='.msg': preview={'Note':'Outlook .msg original retained. Download and open in Outlook; preview is not implemented.'}
        fid=uuid.uuid4().hex
        with self.connect(True) as db:
            self.require(db,user,aid); mid=db.execute('INSERT INTO messages(alert_id,author,body,created) VALUES(?,?,?,?)',(aid,user,'',now())).lastrowid
            db.execute('INSERT INTO attachments VALUES(?,?,?,?,?,?,?)',(fid,mid,name,mimetypes.guess_type(name)[0] or 'application/octet-stream',len(data),data,json.dumps(preview)))
            self.activity(db,aid,user,'Attachment added',name); self.emit(db,aid,'update',user)
        self.wake(); return {'id':fid,'message_id':mid}

    def download(self,user,fid):
        with self.connect() as db:
            self.user(db,user)
            r=db.execute('SELECT f.* FROM attachments f JOIN messages m ON m.id=f.message_id JOIN members a ON a.alert_id=m.alert_id WHERE f.id=? AND a.user_id=?',(fid,user)).fetchone()
            if not r: raise APIError(404,'Attachment not found.')
            return dict(r)


class Handler(BaseHTTPRequestHandler):
    protocol_version='HTTP/1.1'
    def log_message(self, fmt, *args):
        if getattr(self.server,'verbose',False): super().log_message(fmt,*args)
    @property
    def store(self): return self.server.store
    def reply(self,status,data,ctype='application/json; charset=utf-8',headers=None):
        if not isinstance(data,bytes): data=json.dumps(data,ensure_ascii=False).encode()
        self.send_response(status); self.send_header('Content-Type',ctype); self.send_header('Content-Length',str(len(data)))
        self.send_header('Cache-Control','no-store'); self.send_header('X-Content-Type-Options','nosniff')
        for k,v in (headers or {}).items(): self.send_header(k,v)
        self.end_headers(); self.wfile.write(data)
    def read_json(self):
        raw=self.read_body(64*1024)
        try: data=json.loads(raw)
        except Exception: raise APIError(400,'Invalid JSON.')
        if not isinstance(data,dict): raise APIError(400,'JSON object required.')
        return data
    def read_body(self,limit):
        try: n=int(self.headers.get('Content-Length','0'))
        except ValueError: raise APIError(400,'Invalid content length.')
        if n<0 or n>limit:
            self.close_connection=True; raise APIError(413,'Request too large.')
        return self.rfile.read(n)
    def dispatch(self,method):
        url=urlparse(self.path); q=parse_qs(url.query); user=q.get('user',[''])[0]; path=url.path
        if method=='GET' and path in ('/','/mock','/alert-popup.html','/listener.html','/static/app.js','/static/style.css','/static/adapters/desktop.js','/static/listener.js'):
            name='index.html' if path=='/' else 'mock.html' if path=='/mock' else path.removeprefix('/static/').lstrip('/')
            types={'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8'}
            return self.reply(200,(ROOT/'static'/name).read_bytes(),types[Path(name).suffix])
        if method=='GET' and path=='/api/users': return self.reply(200,self.store.directory())
        if method=='GET' and path=='/api/snapshot': return self.reply(200,self.store.snapshot(user))
        if method=='GET' and path in ('/api/events','/api/stream'):
            try: after=max(0,int(self.headers.get('Last-Event-ID') or q.get('after',['0'])[0]))
            except ValueError: raise APIError(400,'Invalid event cursor.')
            if path=='/api/events': return self.reply(200,self.store.events(user,after))
            self.store.events(user,after)  # validate before sending headers
            self.send_response(200); self.send_header('Content-Type','text/event-stream'); self.send_header('Cache-Control','no-cache'); self.send_header('Connection','close'); self.end_headers(); self.close_connection=True
            try:
                self.wfile.write(b': connected\n\n'); self.wfile.flush()
                heartbeat=time.monotonic()
                while not self.server.stopping.is_set():
                    events=self.store.events(user,after)
                    for e in events:
                        self.wfile.write(f"id: {e['id']}\ndata: {json.dumps(e)}\n\n".encode()); after=e['id']
                    if events: self.wfile.flush(); heartbeat=time.monotonic()
                    elif time.monotonic()-heartbeat>=10:
                        self.wfile.write(b': heartbeat\n\n'); self.wfile.flush(); heartbeat=time.monotonic()
                    with self.store.changed: self.store.changed.wait(.35)
            except (BrokenPipeError,ConnectionResetError,OSError): pass
            return
        if method=='POST' and path=='/api/alerts': return self.reply(201,self.store.create(user,self.read_json()))
        m=re.fullmatch(r'/api/alerts/([A-Za-z0-9-]+)(?:/(actions|messages|invite|attachments))?',path)
        if m:
            aid,op=m.groups()
            if method=='GET' and op is None: return self.reply(200,self.store.detail(user,aid))
            if method=='POST' and op=='actions': return self.reply(200,self.store.action(user,aid,self.read_json()))
            if method=='POST' and op=='messages': return self.reply(201,self.store.message(user,aid,self.read_json()))
            if method=='POST' and op=='invite': return self.reply(200,self.store.add_people(user,aid,self.read_json()))
            if method=='POST' and op=='attachments': return self.reply(201,self.store.upload(user,aid,q.get('name',[''])[0],self.read_body(MAX_FILE)))
        m=re.fullmatch(r'/api/attachments/([a-f0-9]+)',path)
        if m and method=='GET':
            f=self.store.download(user,m[1]); return self.reply(200,f['data'],'application/octet-stream',{'Content-Disposition':"attachment; filename*=UTF-8''"+quote(f['name'],safe='')})
        raise APIError(404,'Not found.')
    def handle_request(self,method):
        try: self.dispatch(method)
        except APIError as e: self.reply(e.status,{'error':e.message})
        except (BrokenPipeError,ConnectionResetError): pass
        except Exception as e:
            import traceback; traceback.print_exc()
            try: self.reply(500,{'error':'Internal server error.'})
            except OSError: pass
    def do_GET(self): self.handle_request('GET')
    def do_POST(self): self.handle_request('POST')


def make_server(db_path,host='127.0.0.1',port=8765):
    server=ThreadingHTTPServer((host,port),Handler); server.daemon_threads=True; server.store=Store(db_path); server.stopping=threading.Event(); return server


def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--port',type=int,default=8765); p.add_argument('--db',default=str(ROOT/'data'/'pulse.sqlite3')); p.add_argument('--verbose',action='store_true'); args=p.parse_args()
    server=make_server(args.db,port=args.port); server.verbose=args.verbose
    print(f'Pulse running at http://127.0.0.1:{server.server_port} — Ctrl+C to stop.',flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.stopping.set(); server.store.wake(); server.server_close()

if __name__=='__main__': main()
