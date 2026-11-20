import concurrent.futures, json, tempfile, threading, unittest
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from urllib.parse import urlencode
from server import make_server, Store

class APITest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(); cls.db=Path(cls.temp.name)/'test.sqlite3'; cls.server=make_server(cls.db,port=0); cls.base=f'http://127.0.0.1:{cls.server.server_port}'; cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True); cls.thread.start()
    @classmethod
    def tearDownClass(cls):
        cls.server.stopping.set(); cls.server.store.wake(); cls.server.shutdown(); cls.server.server_close(); cls.temp.cleanup()
    def call(self,path,user='am23456',body=None,raw=None,params=None,code=200):
        url=self.base+path+'?'+urlencode({'user':user,**(params or {})}); data=raw if raw is not None else json.dumps(body).encode() if body is not None else None
        req=Request(url,data=data,headers={'Content-Type':'application/octet-stream' if raw is not None else 'application/json'})
        try:
            with urlopen(req,timeout=5) as r:
                self.assertEqual(r.status,code); return json.load(r) if 'json' in r.headers['Content-Type'] else r.read()
        except HTTPError as e:
            self.assertEqual(e.code,code); return json.load(e)
    def create(self,recipients=None):
        return self.call('/api/alerts',body={'title':'Test failure','description':'Worker unavailable','severity':'Critical','recipients':recipients or ['am23456','sc12345']},code=201)['id']
    def detail(self,aid,user='am23456',code=200): return self.call('/api/alerts/'+aid,user,code=code)
    def action(self,aid,user='am23456',action='claim',code=200,**extra): return self.call('/api/alerts/'+aid+'/actions',user,body={'action':action,**extra},code=code)
    def test_01_directory_and_mock(self):
        self.assertEqual(len(self.call('/api/users')),6); aid=self.create(); self.assertEqual(self.detail(aid)['status'],'Unassigned'); self.detail(aid,'dl34567',404); self.assertTrue(any(e['alert_id']==aid and e['kind']=='alert_created' for e in self.call('/api/events','sc12345')))
    def test_02_concurrent_claim(self):
        aid=self.create(); barrier=threading.Barrier(2)
        def claim(user):
            barrier.wait(); req=Request(self.base+'/api/alerts/'+aid+'/actions?'+urlencode({'user':user}),data=b'{"action":"claim"}',headers={'Content-Type':'application/json'})
            try:
                with urlopen(req,timeout=5) as r: return r.status,user
            except HTTPError as e: return e.code,user
        with concurrent.futures.ThreadPoolExecutor(2) as pool: result=list(pool.map(claim,['am23456','sc12345']))
        self.assertEqual(sorted(x[0] for x in result),[200,409]); winner=next(u for c,u in result if c==200); self.assertEqual(self.detail(aid)['owner'],winner)
    def test_03_message_mention_invite_and_permissions(self):
        aid=self.create(); self.call('/api/alerts/'+aid+'/messages',body={'body':'@dl34567 Please investigate.'},code=201); self.assertEqual(self.detail(aid,'dl34567')['messages'][0]['body'],'@dl34567 Please investigate.'); self.assertTrue(any(e['kind']=='mention' and e['alert_id']==aid for e in self.call('/api/events','dl34567'))); self.call('/api/alerts/'+aid+'/invite',body={'users':['mb45678']}); self.assertTrue(any(e['kind']=='invited' and e['alert_id']==aid for e in self.call('/api/events','mb45678'))); self.detail(aid,'jp56789',404); self.call('/api/alerts/'+aid+'/messages','jp56789',body={'body':'Not allowed'},code=404)
    def test_04_email_preview_and_download(self):
        aid=self.create(); raw=b'Subject: Support update\r\nFrom: demo@example.com\r\nTo: ops@example.com\r\n\r\nFixed.\r\n'; result=self.call('/api/alerts/'+aid+'/attachments',raw=raw,params={'name':'support.eml'},code=201); f=self.detail(aid,'sc12345')['messages'][0]['attachments'][0]; self.assertEqual(json.loads(f['preview'])['Subject'],'Support update'); self.assertEqual(self.call('/api/attachments/'+result['id'],'sc12345'),raw); self.call('/api/attachments/'+result['id'],'dl34567',code=404); self.call('/api/alerts/'+aid+'/attachments',raw=b'Outlook binary mock',params={'name':'outlook.msg'},code=201); self.call('/api/alerts/'+aid+'/attachments',raw=b'bad',params={'name':'test.exe'},code=400)
    def test_05_resolve_and_restart_persistence(self):
        aid=self.create(); self.action(aid); self.action(aid,'sc12345','resolve',409,resolution='Not owner'); self.action(aid,action='resolve',code=400); self.action(aid,action='resolve',resolution='Restored service and verified.'); self.assertEqual(self.detail(aid,'sc12345')['status'],'Resolved'); reopened=Store(self.db); self.assertEqual(reopened.detail('sc12345',aid)['resolution'],'Restored service and verified.'); self.assertEqual([a['action'] for a in reopened.detail('sc12345',aid)['activity']],['Created','Claimed','Resolved'])
    def test_06_release_and_reassign(self):
        aid=self.create(); self.action(aid); self.action(aid,action='release'); self.action(aid,'sc12345'); self.assertEqual(self.detail(aid)['owner'],'sc12345')
    def test_07_sse_and_replay_cursor(self):
        cursor=self.call('/api/snapshot')['cursor']; r=urlopen(self.base+'/api/stream?'+urlencode({'user':'am23456','after':cursor}),timeout=5)
        try:
            self.assertTrue(r.readline().startswith(b': connected')); r.readline(); aid=self.create(); event_id=int(r.readline().decode().split(': ')[1]); data=json.loads(r.readline().decode()[6:]); self.assertEqual(data['alert_id'],aid); self.assertEqual(data['kind'],'alert_created'); self.assertEqual(data['id'],event_id); self.assertFalse(any(e['id']<=event_id for e in self.call('/api/events',params={'after':event_id})))
        finally: r.close()
    def test_09_static_pages(self):
        for path,marker in [('/',b'Alert inbox'),('/mock',b'Alert simulator'),('/static/app.js',b'initWorkspace'),('/static/style.css',b'.popup-host'),('/alert-popup.html',b'ALERT &amp; COLLABORATION'),('/listener.html',b'Background alert listener'),('/static/adapters/desktop.js',b'FinsembleAdapter'),('/static/listener.js',b'EventSource')]:
            self.assertIn(marker,self.call(path))
    def test_08_invalid_input(self):
        self.call('/api/alerts',body={'title':'','description':'x','recipients':['am23456']},code=400); self.call('/api/alerts',body={'title':'a','description':'x','recipients':[]},code=400); self.call('/api/snapshot','invalid',code=400)

if __name__=='__main__': unittest.main(verbosity=2)
