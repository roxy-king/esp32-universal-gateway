"""Explicit development simulator. Never connects to a real MCU."""
import asyncio,time
import aiohttp

async def simulate(url,pair,project):
    values={f['key']:f['min'] for f in project['fields']};cache={};start=time.monotonic()
    async with aiohttp.ClientSession() as client:
        async with client.ws_connect(url+'/gateway/ws',headers={'X-Device-Id':'esp-simulator','Authorization':'Bearer '+pair['token']}) as ws:
            async def send_state():
                line='P1,S,'+project['id']+','+';'.join(k+'='+str(v) for k,v in values.items())
                await ws.send_json({'v':1,'type':'rx','encoding':'hex','data':line.encode().hex()})
            async def publish():
                while True:
                    await ws.send_json(dict(v=1,type='status',device_id='esp-simulator',boot_id='simulated-boot',mode='line',remote_write=True,firmware='SIMULATED / no hardware',ssid='模拟网络',rssi=-40,baud=9600,format='8N1',rx=18,tx=17,ending='crlf'))
                    if 'uptime' in values:values['uptime']=int(time.monotonic()-start)%65536
                    if values.get('remaining',0)>0:
                        values['remaining']-=1
                        if not values['remaining']:values['led']=0
                    await send_state();await asyncio.sleep(1)
            task=asyncio.create_task(publish())
            try:
                async for message in ws:
                    if message.type!=aiohttp.WSMsgType.TEXT:continue
                    d=message.json()
                    if d.get('type')!='tx':continue
                    await ws.send_json(dict(v=1,type='ack',id=d['id'],ok=True,result='uart_queued_not_executed'))
                    parts=d['data'].split(',')
                    if len(parts)!=6 or parts[:3]!=['P1','C',project['id']]:continue
                    id,op,arg=parts[3:];value=int(arg)
                    if id not in cache:
                        if op=='LED' and value in (0,1):values.update(led=value,remaining=0);result='OK,applied'
                        elif op=='PULSE' and 1<=value<=60:values.update(led=1,remaining=value);result='OK,applied'
                        elif op=='STOP' and value==0:values.update(led=0,remaining=0);result='OK,applied'
                        else:result='ERR,unknown_command'
                        cache[id]=result
                        if len(cache)>8:cache.pop(next(iter(cache)))
                    line=f'P1,A,{project["id"]},{id},{cache[id]}'
                    await ws.send_json(dict(v=1,type='rx',encoding='hex',data=line.encode().hex()));await send_state()
            finally:
                task.cancel()
                import contextlib
                with contextlib.suppress(asyncio.CancelledError):await task
