"""Local mock of ESP configuration APIs for browser checks; never deployed."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'server'))
from aiohttp import web
P=Path(__file__).resolve().parents[1]
config=dict(name='通用通信网关',device_id='esp-demo',ssid='',host='',port=443,path='/gateway/ws',tls=True,token_set=False,ca='',baud=9600,rx=18,tx=17,format='8N1',mode='line',ending='crlf',idle_ms=20,ntp='pool.ntp.org',remote_write=False,nonce='test-nonce')
async def index(r):return web.FileResponse(P/'portal.html')
async def conf(r):return web.json_response(config)
async def scan(r):return web.json_response(dict(running=False,networks=[dict(ssid='Demo Wi-Fi',rssi=-42,open=False),dict(ssid='Guest',rssi=-68,open=True)]))
async def wifi(r):
 d=await r.json()
 assert d['ssid'] and ('password' in d)
 config['ssid']=d['ssid']
 return web.json_response(dict(message='已保存，正在连接'))
async def status(r):return web.json_response(dict(firmware='UniversalGateway 1.0.0 · 预览',wifi=False,ip='0.0.0.0',rssi=0,clock=False,cloud=False,rx_bytes=0,tx_bytes=0,dropped_frames=0,last_rx_ms=-1,uptime_s=0,free_heap=0,remote_write=False,logs=['预览环境：未连接实物设备']))
app=web.Application();app.add_routes([web.get('/',index),web.get('/api/config',conf),web.get('/api/status',status),web.get('/api/scan',scan),web.post('/api/scan',scan),web.post('/api/wifi',wifi)]);web.run_app(app,host='127.0.0.1',port=8877,access_log=None)
