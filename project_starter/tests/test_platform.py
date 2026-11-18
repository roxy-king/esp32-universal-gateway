import asyncio, contextlib, json, sys, tempfile, time, unittest
from datetime import datetime,timedelta
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'platform'))
from app import create_app, due_time, GMT8
from gateway import digest,password_hash
from definition import load_project,command_spec,parse_frame
from assistant import endpoint,interpret
from store import Store
from aiohttp.test_utils import AioHTTPTestCase

class ContractTests(unittest.TestCase):
    def setUp(self):self.p=load_project(ROOT/'project.json')
    def test_ranges_and_unknown_commands(self):
        for key,v in [('pulse',0),('pulse',61),('pulse',True),('shell',1),('led','1')]:
            with self.assertRaises(ValueError):command_spec(self.p,key,v)
    def test_wire_frames(self):
        self.assertEqual(parse_frame(self.p,'P1,S,bench,led=1;remaining=4;uptime=10')[1]['remaining'],4)
        for frame in ['STATUS,1,0','P1,S,other,led=1;remaining=4;uptime=10','P1,S,bench,led=2;remaining=4;uptime=10','P1,S,bench,led=0;led=1','P1,A,bench,abc,OK,applied']:
            self.assertIsNone(parse_frame(self.p,frame))
    def test_duplicate_definition_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=dict(self.p);p['commands']=self.p['commands']*2;f=Path(d)/'p.json';f.write_text(json.dumps(p))
            with self.assertRaises(ValueError):load_project(f)
    def test_gmt8(self):
        at=(datetime.now(GMT8)+timedelta(minutes=5)).replace(microsecond=0)
        self.assertAlmostEqual(due_time(at.replace(tzinfo=None).isoformat()),at.timestamp())
        with self.assertRaises(ValueError):due_time(at.replace(tzinfo=None).isoformat()+'+00:00')
        with self.assertRaises(ValueError):due_time('2000-01-01T10:00')
    def test_ai_url_and_reply(self):
        for url in ['http://example.com','https://localhost','https://127.0.0.1','https://169.254.169.254','https://user:secret@example.com','https://example.com?key=secret']:
            with self.assertRaises(ValueError):endpoint(url)
        self.assertEqual(endpoint('https://example.com/v1/'),'https://example.com/v1/chat/completions')
        self.assertEqual(interpret('普通回复'),('普通回复',None))
        self.assertEqual(interpret('```json\n{"reply":"好","proposal":{"command":"led","value":1}}\n```')[0],'好')
    def test_restart_does_not_replay(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'db';s=Store(path)
            s.run('INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?)',('deadbeef','device','led',1,'sent','',time.time(),time.time()))
            s.run('INSERT INTO schedules VALUES(?,?,?,?,?,?,?)',('x','device','led',1,time.time(),'running',''));s.close();s=Store(path)
            self.assertEqual(s.rows('SELECT status FROM jobs')[0]['status'],'unknown');self.assertEqual(s.rows('SELECT status FROM schedules')[0]['status'],'unknown');s.close()

class PlatformTests(AioHTTPTestCase):
    async def get_application(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);salt='22'*16
        self.config={'origin':'http://localhost','username':'admin','password_salt':salt,'password_hash':password_hash('testpass8',salt),'devices':{'dev':{'token_sha256':digest('test-token-12345')}}}
        return create_app(self.config,self.temp.name,ROOT/'project.json')
    async def asyncSetUp(self):
        await super().asyncSetUp();self.s=self.app['platform'];self.s.scheduler_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):await self.s.scheduler_task
        r=await self.client.post('/api/login',json={'username':'admin','password':'testpass8'},headers={'Origin':'http://localhost'})
        self.assertEqual(r.status,200);self.headers={'Origin':'http://localhost','X-CSRF-Token':(await r.json())['csrf']}
    async def connect(self,project='bench',write=True):
        ws=await self.client.ws_connect('/gateway/ws',headers={'X-Device-Id':'auto-id','Authorization':'Bearer test-token-12345'})
        await ws.send_json(dict(v=1,type='hello',device_id='auto-id',boot_id='boot1',mode='line',remote_write=write))
        await self.rx(ws,f'P1,S,{project},led=0;remaining=0;uptime=1');return ws
    async def rx(self,ws,line):
        await ws.send_json(dict(v=1,type='rx',encoding='hex',data=line.encode().hex()));await asyncio.sleep(.015)
    async def ticket(self,**kwargs):
        r=await self.client.post('/api/action/prepare',json={'device':'dev','command':'pulse','value':3,**kwargs},headers=self.headers)
        self.assertEqual(r.status,200,await r.text());return await r.json()
    async def start_action(self,t):return await self.client.post('/api/action',json={'ticket':t['ticket']},headers=self.headers)
    async def test_auth_and_csrf(self):
        self.assertEqual((await self.client.post('/api/site',json={'title':'bad'})).status,403)
        await self.client.post('/api/logout',json={},headers=self.headers)
        self.assertEqual((await self.client.get('/api/overview')).status,401)
    async def test_readonly_and_wrong_project(self):
        ws=await self.connect(project='other')
        r=await self.client.post('/api/action/prepare',json={'device':'dev','command':'led','value':1},headers=self.headers);self.assertEqual(r.status,400)
        await self.rx(ws,'P1,S,bench,led=0;remaining=0;uptime=2');self.s.devices['dev']['status']['remote_write']=False
        r=await self.client.post('/api/action/prepare',json={'device':'dev','command':'led','value':1},headers=self.headers);self.assertEqual(r.status,400);await ws.close()
    async def test_execution_requires_mcu_ack(self):
        ws=await self.connect();t=await self.ticket();self.assertTrue(t['confirm']);task=asyncio.create_task(self.start_action(t));tx=await ws.receive_json();id=tx['data'].split(',')[3]
        await ws.send_json(dict(v=1,type='ack',id=tx['id'],ok=True,result='uart_queued_not_executed'));await asyncio.sleep(.02);self.assertFalse(task.done())
        await self.rx(ws,f'P1,A,bench,{id},OK,applied');r=await task;self.assertEqual((await r.json())['status'],'succeeded')
        self.assertEqual((await self.start_action(t)).status,409);await ws.close()
    async def test_timeout_then_late_ack(self):
        ws=await self.connect();self.s.command_timeout=.1;t=await self.ticket();task=asyncio.create_task(self.start_action(t));tx=await ws.receive_json();id=tx['data'].split(',')[3]
        result=await (await task).json();self.assertEqual(result['status'],'unknown')
        await self.rx(ws,f'P1,A,bench,{id},OK,applied');self.assertEqual(self.s.store.rows('SELECT status FROM jobs')[0]['status'],'succeeded');await ws.close()
    async def test_rejection_and_duplicate_pending(self):
        ws=await self.connect();t=await self.ticket();t2=await self.ticket();task=asyncio.create_task(self.start_action(t));tx=await ws.receive_json()
        self.assertEqual((await self.start_action(t2)).status,409)
        await self.rx(ws,f'P1,A,bench,{tx["data"].split(",")[3]},ERR,out_of_range');self.assertEqual((await (await task).json())['status'],'failed');await ws.close()
    async def test_ticket_expiry_and_session_binding(self):
        ws=await self.connect();t=await self.ticket();self.s.tickets[t['ticket']]['expires']=0
        self.assertEqual((await self.start_action(t)).status,409)
        t=await self.ticket();self.s.tickets[t['ticket']]['csrf']='other';self.assertEqual((await self.start_action(t)).status,409);await ws.close()
    async def test_stale_telemetry_blocks(self):
        ws=await self.connect();t=await self.ticket();self.s.telemetry['dev']['received']-=20
        self.assertEqual((await self.start_action(t)).status,409);await ws.close()
    async def test_schedule_once_and_cancel(self):
        t=await self.ticket(at=(datetime.now(GMT8)+timedelta(minutes=5)).isoformat());r=await self.start_action(t);s=await r.json();self.assertEqual(s['status'],'scheduled')
        r=await self.client.post('/api/schedules/cancel',json={'id':s['id']},headers=self.headers);self.assertEqual(r.status,200)
        t=await self.ticket(at=(datetime.now(GMT8)+timedelta(minutes=5)).isoformat());sid=(await (await self.start_action(t)).json())['id'];self.s.store.run('UPDATE schedules SET due=? WHERE id=?',(time.time()-1,sid))
        await self.s.scheduler_once();await self.s.scheduler_once();row=self.s.store.rows('SELECT * FROM schedules WHERE id=?',(sid,))[0];self.assertEqual(row['status'],'failed');self.assertIn('离线',row['result']);self.assertFalse(self.s.store.rows('SELECT * FROM jobs'))
    async def test_schedule_limit_rechecked_at_confirmation(self):
        t=await self.ticket(at=(datetime.now(GMT8)+timedelta(minutes=5)).isoformat())
        for n in range(100):self.s.store.run('INSERT INTO schedules VALUES(?,?,?,?,?,?,?)',(str(n),'dev','led',1,time.time()+300,'pending',''))
        self.assertEqual((await self.start_action(t)).status,409)
        self.assertEqual(len(self.s.store.rows('SELECT id FROM schedules')),100)
    async def test_schedule_success_and_missed(self):
        ws=await self.connect();self.s.store.run('INSERT INTO schedules VALUES(?,?,?,?,?,?,?)',('due','dev','led',1,time.time()-1,'pending',''))
        task=asyncio.create_task(self.s.scheduler_once());tx=await ws.receive_json();await self.rx(ws,f'P1,A,bench,{tx["data"].split(",")[3]},OK,applied');await task
        self.assertEqual(self.s.store.rows('SELECT status FROM schedules')[0]['status'],'succeeded')
        self.s.store.run('INSERT INTO schedules VALUES(?,?,?,?,?,?,?)',('late','dev','led',1,time.time()-120,'pending',''));await self.s.scheduler_once();self.assertEqual(self.s.store.rows("SELECT status FROM schedules WHERE id='late'")[0]['status'],'missed');await ws.close()
    async def test_presets_site_and_title_render(self):
        for data in [{'name':'方案','command':'pulse','value':3},{'name':'bad','command':'pulse','value':999}]:
            r=await self.client.post('/api/presets',json=data,headers=self.headers);self.assertEqual(r.status,200 if data['name']=='方案' else 400)
        await self.client.post('/api/site',json={'title':'新项目 <测试>'},headers=self.headers)
        text=await (await self.client.get('/')).text();self.assertIn('新项目 &lt;测试&gt;',text);self.assertNotIn('__TITLE__',text)
    async def test_ai_proposes_only_and_preserves_history(self):
        ws=await self.connect()
        r=await self.client.post('/api/ai/settings',json={'base_url':'https://example.com/v1','model':'test','key':'test-api-key'},headers=self.headers);self.assertEqual(r.status,200)
        settings=await (await self.client.get('/api/ai/settings')).json();self.assertNotIn('key',settings);self.assertTrue(settings['key_set'])
        thread=(await (await self.client.post('/api/ai/threads',json={},headers=self.headers)).json())['id']
        async def mock(c,m):return json.dumps({'reply':'请确认限时点亮','proposal':{'command':'pulse','value':3}})
        self.app['model_caller']=mock
        r=await self.client.post('/api/ai/chat',json={'thread':thread,'device':'dev','text':'亮三秒'},headers=self.headers);data=await r.json();self.assertIn('proposal',data);self.assertFalse(self.s.store.rows('SELECT * FROM jobs'))
        history=await (await self.client.get('/api/ai/threads?id='+thread)).json();self.assertEqual(len(history),2)
        async def invalid(c,m):return json.dumps({'reply':'建议','proposal':{'command':'shell','value':1}})
        self.app['model_caller']=invalid;r=await self.client.post('/api/ai/chat',json={'thread':thread,'device':'dev','text':'修改'},headers=self.headers);data=await r.json();self.assertIsNone(data['proposal']);self.assertIn('未生成',data['reply']);await ws.close()
    async def test_ai_no_key_or_bad_endpoint(self):
        r=await self.client.post('/api/ai/chat',json={},headers=self.headers);self.assertEqual(r.status,409)
        r=await self.client.post('/api/ai/settings',json={'base_url':'http://127.0.0.1','model':'x','key':'test-key'},headers=self.headers);self.assertEqual(r.status,400)
    async def test_persistence(self):
        await self.client.post('/api/site',json={'title':'保存标题'},headers=self.headers)
        other=Store(Path(self.temp.name)/'platform.db');self.assertEqual(other.setting('site')['title'],'保存标题');other.close()

if __name__=='__main__':unittest.main()
