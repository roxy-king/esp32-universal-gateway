import asyncio, json, sys, unittest, tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'server'))
from server import create_app,validate_command,digest,password_hash
from aiohttp.test_utils import AioHTTPTestCase

class ProtocolTests(unittest.TestCase):
    def test_text_and_hex(self):
        self.assertEqual(validate_command({'encoding':'text','data':'PUMP ON'},'line'),('text','PUMP ON'))
        self.assertEqual(validate_command({'encoding':'hex','data':'00ff'},'hex'),('hex','00ff'))
    def test_reject_invalid_payloads(self):
        for d,m in [({'encoding':'text','data':'START\nSTOP'},'line'),({'encoding':'text','data':'中'*180},'line'),({'encoding':'hex','data':'001'},'hex'),({'encoding':'hex','data':'gg'},'hex'),({'encoding':'text','data':'ON'},'hex'),([], 'line')]:
            with self.subTest(data=d),self.assertRaises(ValueError):validate_command(d,m)

class ServerTests(AioHTTPTestCase):
    async def get_application(self):
        self.origin='http://localhost';salt='11'*16
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.account_file=Path(self.tmp.name)/'account.json'
        self.original=dict(origin=self.origin,username='student',password_salt=salt,password_hash=password_hash('test-password-123',salt),devices={'seedling':{'token_sha256':digest('test-device-token')}})
        return create_app(self.original,self.account_file)
    async def test_probe_checks_auth_without_device_registration(self):
        r=await self.client.get('/gateway/ws',headers={'X-Gateway-Probe':'1'})
        self.assertEqual(r.status,401)
        r=await self.client.get('/gateway/ws',headers={'X-Gateway-Probe':'1','X-Device-Id':'seedling','Authorization':'Bearer test-device-token'})
        self.assertEqual(r.status,204)
        self.assertEqual(self.app['gateway'].devices,{})
    async def test_account_eight_chars_persist_and_revoke(self):
        from server import GatewayServer
        headers=await self.login()
        r=await self.client.post('/api/account',json=dict(username='新账号',current_password='test-password-123',new_password='newpass8',confirm_password='newpass8'),headers=headers)
        self.assertEqual(r.status,200);self.assertEqual((await self.client.get('/api/state')).status,401)
        self.assertNotIn('newpass8',self.account_file.read_text())
        restored=GatewayServer(self.original,self.account_file);self.assertEqual(restored.config['username'],'新账号');self.assertEqual(restored.config['devices'],self.original['devices'])
        self.assertEqual(password_hash('newpass8',restored.config['password_salt']),restored.config['password_hash'])
        r=await self.client.post('/api/login',json=dict(username='新账号',password='newpass8'),headers={'Origin':self.origin});self.assertEqual(r.status,200)
        r=await self.client.post('/api/login',json=dict(username='student',password='test-password-123'),headers={'Origin':self.origin});self.assertEqual(r.status,401)
    async def test_account_invalid_old_short_mismatch_csrf(self):
        headers=await self.login()
        good=dict(username='student',current_password='test-password-123',new_password='newpass8',confirm_password='newpass8')
        self.assertEqual((await self.client.post('/api/account',json=good)).status,403)
        for changes,status in [({'current_password':'wrong'},403),({'new_password':'short'},400),({'confirm_password':'mismatch'},400)]:
            r=await self.client.post('/api/account',json=dict(good,**changes),headers=headers);self.assertEqual(r.status,status)
        self.assertFalse(self.account_file.exists());self.assertEqual((await self.client.get('/api/state')).status,200)
    async def test_account_storage_failure_retains_original(self):
        headers=await self.login();self.app['gateway'].account_file=Path(self.tmp.name)/'missing'/'account.json'
        r=await self.client.post('/api/account',json=dict(username='changed',current_password='test-password-123',new_password='newpass8',confirm_password='newpass8'),headers=headers)
        self.assertEqual(r.status,503);self.assertEqual(self.app['gateway'].config['username'],'student');self.assertEqual((await self.client.get('/api/state')).status,200)
    async def login(self):
        r=await self.client.post('/api/login',json={'username':'student','password':'test-password-123'},headers={'Origin':self.origin});self.assertEqual(r.status,200)
        return {'Origin':self.origin,'X-CSRF-Token':(await r.json())['csrf']}
    async def connect(self,write=True):
        ws=await self.client.ws_connect('/gateway/ws',headers={'X-Device-Id':'seedling','Authorization':'Bearer test-device-token'})
        await ws.send_json(dict(v=1,type='hello',device_id='seedling',boot_id='boot-test',mode='line',remote_write=write));await asyncio.sleep(.02);return ws
    async def test_auth_required(self):
        self.assertEqual((await self.client.get('/api/state')).status,401)
        self.assertEqual((await self.client.get('/gateway/ws')).status,401)
    async def test_login_wrong_origin_and_password(self):
        self.assertEqual((await self.client.post('/api/login',json={})).status,403)
        r=await self.client.post('/api/login',json={'username':'student','password':'wrong'},headers={'Origin':self.origin});self.assertEqual(r.status,401)
    async def test_offline_and_csrf(self):
        headers=await self.login()
        self.assertEqual((await self.client.post('/api/devices/seedling/tx',json={})).status,403)
        self.assertEqual((await self.client.post('/api/devices/seedling/tx',json={},headers=headers)).status,409)
    async def test_read_only(self):
        headers=await self.login();ws=await self.connect(False)
        self.assertEqual((await self.client.post('/api/devices/seedling/tx',json={'encoding':'text','data':'PUMP ON'},headers=headers)).status,409);await ws.close()
    async def test_send_ack_and_rx(self):
        headers=await self.login();ws=await self.connect()
        task=asyncio.create_task(self.client.post('/api/devices/seedling/tx',json={'encoding':'text','data':'PUMP ON'},headers=headers))
        tx=await ws.receive_json();self.assertEqual(tx['boot_id'],'boot-test');self.assertEqual(tx['data'],'PUMP ON')
        await ws.send_json(dict(v=1,type='ack',id=tx['id'],ok=True,result='uart_queued_not_executed'))
        r=await task;self.assertEqual(r.status,200);self.assertTrue((await r.json())['ok'])
        await ws.send_json(dict(v=1,type='rx',encoding='hex',data=b'TEMP,25.5'.hex()));await asyncio.sleep(.02)
        r=await self.client.get('/api/state');d=await r.json();self.assertTrue(d['devices'][0]['connected']);self.assertEqual(d['events'][-1]['detail']['text'],'TEMP,25.5');await ws.close()
    async def test_disconnect_unknown_no_retry(self):
        headers=await self.login();ws=await self.connect()
        task=asyncio.create_task(self.client.post('/api/devices/seedling/tx',json={'encoding':'text','data':'PUMP ON'},headers=headers))
        await ws.receive_json();await ws.close();r=await task;self.assertFalse((await r.json())['ok'])
        self.assertFalse(self.app['gateway'].pending)
    async def test_timeout_unknown(self):
        headers=await self.login();ws=await self.connect()
        task=asyncio.create_task(self.client.post('/api/devices/seedling/tx',json={'encoding':'text','data':'PUMP ON'},headers=headers))
        await ws.receive_json();r=await task;self.assertEqual(r.status,504);await ws.close()
    async def test_malformed_ws_is_closed(self):
        await self.login();ws=await self.connect();await ws.send_str('[]');msg=await ws.receive();self.assertIn(msg.type.value,[8,257]);await ws.close()
    async def test_probe_keeps_active_session(self):
        ws=await self.connect()
        r=await self.client.get('/gateway/ws',headers={'X-Gateway-Probe':'1','X-Device-Id':'seedling','Authorization':'Bearer test-device-token'})
        self.assertEqual(r.status,204)
        self.assertFalse(ws.closed)
        self.assertIn('seedling',self.app['gateway'].devices)
        await ws.close()
    async def test_device_can_reconnect_after_disconnect(self):
        ws=await self.connect();await ws.close();await asyncio.sleep(.05)
        ws=await self.connect();self.assertFalse(ws.closed);await ws.close()
    async def test_single_device_session(self):
        from aiohttp import WSServerHandshakeError
        ws=await self.connect()
        with self.assertRaises(WSServerHandshakeError):await self.connect()
        await ws.close()
    async def test_logout(self):
        headers=await self.login();self.assertEqual((await self.client.post('/api/logout',json={},headers=headers)).status,200)
        self.assertEqual((await self.client.get('/api/state')).status,401)
if __name__=='__main__':unittest.main()
