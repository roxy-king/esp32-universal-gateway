"""Browser QA only: loopback server and simulated gateway, no hardware commands."""
import asyncio,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'server'))
from server import create_app,digest,password_hash
from aiohttp import web,ClientSession
async def run():
    cfg=dict(origin='http://127.0.0.1:8878',username='qa',password_salt='12'*16,password_hash=password_hash('qa-only-test-password','12'*16),devices={'seedling-demo':{'token_sha256':digest('qa-only-token')}})
    app=create_app(cfg);runner=web.AppRunner(app);await runner.setup();await web.TCPSite(runner,'127.0.0.1',8878).start()
    async with ClientSession() as s:
        async with s.ws_connect('http://127.0.0.1:8878/gateway/ws',headers={'Authorization':'Bearer qa-only-token','X-Device-Id':'seedling-demo'}) as ws:
            async def publish():
                while True:
                    await ws.send_json(dict(v=1,type='status',device_id='seedling-demo',boot_id='demo-boot',mode='line',remote_write=True,rx_bytes=0,tx_bytes=0,dropped_frames=0,last_rx_ms=-1))
                    await asyncio.sleep(5)
            task=asyncio.create_task(publish())
            try:
                async for m in ws:
                    d=m.json()
                    await ws.send_json(dict(v=1,type='ack',id=d['id'],ok=True,result='uart_queued_not_executed'))
                    await ws.send_json(dict(v=1,type='rx',encoding='hex',data=('SIMULATED ACK: '+d['data']).encode().hex()))
            finally:task.cancel()
    await runner.cleanup()
asyncio.run(run())
