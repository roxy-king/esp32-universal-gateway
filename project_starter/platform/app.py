"""Project platform over the unchanged Gateway v1 transport."""
import argparse, asyncio, contextlib, html, json, secrets, time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from aiohttp import web
from gateway import GatewayServer, errors
from definition import load_project, command_spec, parse_frame
from store import Store

ROOT=Path(__file__).resolve().parent.parent
GMT8=timezone(timedelta(hours=8))

def due_time(value):
    if not isinstance(value,str):raise ValueError('请输入 GMT+8 预约时间')
    d=datetime.fromisoformat(value)
    if d.tzinfo is None:d=d.replace(tzinfo=GMT8)
    if d.utcoffset()!=timedelta(hours=8):raise ValueError('预约使用 GMT+8')
    stamp=d.timestamp()
    if not time.time()+2<=stamp<=time.time()+366*86400:raise ValueError('预约须在2秒后至一年内')
    return stamp

class ProjectPlatform(GatewayServer):
    command_timeout=10
    def __init__(self,config,data_dir,project):
        data_dir=Path(data_dir);data_dir.mkdir(parents=True,exist_ok=True)
        super().__init__(config,data_dir/'account.json')
        self.project=project;self.store=Store(data_dir/'platform.db');self.data_dir=data_dir
        self.telemetry={};self.app_pending={};self.active_devices=set();self.tickets={};self.tasks=set();self.last_sample={}
        self.ai_busy=False

    def event(self,device,kind,detail):
        super().event(device,kind,detail)
        if kind!='rx':return
        frame=parse_frame(self.project,detail.get('text',''))
        if frame is None:return
        now=time.time()
        if frame[0]=='state':
            self.telemetry[device]={'values':frame[1],'received':now,'boot_id':self.devices.get(device,{}).get('status',{}).get('boot_id')}
            if now-self.last_sample.get(device,0)>=5:
                self.store.run('INSERT INTO samples(device,stamp,data) VALUES(?,?,?)',(device,now,json.dumps(frame[1])))
                self.last_sample[device]=now
        else:
            a=frame[1];pending=self.app_pending.get(a['id'])
            if pending and pending[0]==device and not pending[1].done():pending[1].set_result(a)
            # Preserve late evidence without resending the original operation.
            old=self.store.rows('SELECT status FROM jobs WHERE id=? AND device=?',(a['id'],device))
            if old and old[0]['status']=='unknown':self.store.finish(a['id'],'succeeded' if a['ok'] else 'failed','迟到的单片机回执：'+a['message'])

    def current(self,device):
        d=self.devices.get(device,{});s=d.get('status',{});t=self.telemetry.get(device,{})
        connected=bool(d.get('ws') is not None and not d['ws'].closed and time.time()-d.get('seen',0)<20)
        fresh=connected and time.time()-t.get('received',0)<=self.project.get('telemetry_timeout',10) and t.get('boot_id')==s.get('boot_id')
        return {'connected':connected,'fresh':fresh,'values':t.get('values',{}),'received':t.get('received'),'remote_write':s.get('remote_write',False),'gateway':s}

    def check_action(self,device,key,value,require_online=True):
        if device not in self.config['devices']:raise ValueError('设备未注册')
        c=command_spec(self.project,key,value)
        if require_online:
            state=self.current(device)
            if not state['connected']:raise ValueError('ESP 离线，未发送')
            if not state['fresh']:raise ValueError('未收到本项目的有效单片机状态，未发送。请核对固件、接线与协议')
            if not state['remote_write']:raise ValueError('ESP 为只读模式，请在 ESP 配置页开启远程写入')
            if state['gateway'].get('mode')!='line':raise ValueError('本模板需要 ESP 使用文本行模式')
        return c

    async def index(self,r):
        title=self.store.setting('site',{}).get('title',self.project['name'])
        content=(ROOT/'platform/index.html').read_text(encoding='utf-8').replace('__TITLE__',html.escape(title))
        return web.Response(text=content,content_type='text/html')

    async def health(self,r):
        self.store.rows('SELECT 1')
        return web.json_response({'ok':True,'version':'1.0.0'})

    async def overview(self,r):
        self.user(r)
        base=json.loads((await super().state(r)).text)
        for d in base['devices']:d['project_state']=self.current(d['id'])
        base.update(project=self.project,demo=bool(self.config.get('demo')),site=self.store.setting('site',{}),jobs=self.store.rows('SELECT * FROM jobs ORDER BY created DESC LIMIT 100'),schedules=self.store.rows('SELECT * FROM schedules ORDER BY due DESC LIMIT 100'),presets=self.store.rows('SELECT * FROM presets ORDER BY id DESC'),threads=self.store.rows('SELECT * FROM threads ORDER BY created DESC LIMIT 50'))
        return web.json_response(base)

    def prepare_ticket(self,session,data,ai=False):
        device,key,value=data.get('device'),data.get('command'),data.get('value')
        schedule=data.get('at');c=self.check_action(device,key,value,require_online=not bool(schedule))
        if ai and not c['ai']:raise ValueError('AI 不允许使用该操作')
        due=None
        if schedule:
            if not self.project.get('features',{}).get('schedules') or not c['schedulable']:raise ValueError('该操作不支持预约')
            due=due_time(schedule)
            if len(self.store.rows("SELECT id FROM schedules WHERE status='pending'"))>=100:raise ValueError('预约最多100条，请先取消不需要的任务')
        now=time.time();self.tickets={k:v for k,v in self.tickets.items() if v['expires']>now}
        if len(self.tickets)>=200:raise ValueError('待确认操作过多，请稍后重试')
        token=secrets.token_urlsafe(24)
        self.tickets[token]={'csrf':session['csrf'],'device':device,'command':key,'value':value,'due':due,'expires':now+120}
        display=c.get('choices',{}).get(str(value),str(value)+c.get('unit',''))
        settings=self.device_settings.get(device,{})
        device_name=settings.get('name') or settings.get('display_id') or device
        return {'ticket':token,'device':device,'label':c['label'],'value':value,'summary':device_name+' / '+c['label']+'：'+display,'confirm':c['confirm'] or ai or due is not None,'at':datetime.fromtimestamp(due,GMT8).isoformat() if due else None,'expires_in':120}

    async def prepare(self,r):
        session=self.mutation(r)
        try:result=self.prepare_ticket(session,await r.json())
        except ValueError as e:raise web.HTTPBadRequest(text=str(e))
        return web.json_response(result)

    async def execute(self,device,key,value,source='网页'):
        if device in self.active_devices:raise ValueError('上一条操作尚未完成，请稍后再试')
        c=self.check_action(device,key,value)
        self.active_devices.add(device)
        id=secrets.token_hex(4)
        while self.store.rows('SELECT id FROM jobs WHERE id=?',(id,)):id=secrets.token_hex(4)
        now=time.time();self.store.run('INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?)',(id,device,key,value,'queued',source,now,now))
        future=asyncio.get_running_loop().create_future();ack=asyncio.get_running_loop().create_future()
        transport_id=secrets.token_hex(16);self.app_pending[id]=(device,future);self.pending[device]=(transport_id,ack)
        payload={'v':1,'type':'tx','id':transport_id,'boot_id':self.devices[device]['status']['boot_id'],'encoding':'text','data':f'P1,C,{self.project["id"]},{id},{c["wire"]},{value}','expires_at':time.time()+5}
        try:
            self.store.finish(id,'sent','等待单片机回执')
            await self.devices[device]['ws'].send_json(payload)
            self.event(device,'tx',{'id':id,'data':payload['data']})
            deadline=time.monotonic()+self.command_timeout
            while not future.done():
                remaining=deadline-time.monotonic()
                if remaining<=0:raise asyncio.TimeoutError()
                watch={future} if ack.done() else {future,ack}
                done,_=await asyncio.wait(watch,timeout=remaining,return_when=asyncio.FIRST_COMPLETED)
                if not done:raise asyncio.TimeoutError()
                if ack.done() and not future.done() and not ack.result().get('ok'):
                    reason=ack.result().get('result','网关未确认')
                    self.store.finish(id,'unknown','网关未确认：'+reason);break
            if future.done():
                a=future.result();self.store.finish(id,'succeeded' if a['ok'] else 'failed','单片机回执：'+a['message'])
        except (asyncio.TimeoutError,ConnectionError,RuntimeError):self.store.finish(id,'unknown','未收到单片机执行回执，结果未知，不会重发')
        except asyncio.CancelledError:
            self.store.finish(id,'unknown','服务停止，结果未知，不会重发');raise
        finally:
            self.pending.pop(device,None);self.app_pending.pop(id,None);self.active_devices.discard(device)
            for f in (future,ack):
                if not f.done():f.cancel()
        return self.store.rows('SELECT * FROM jobs WHERE id=?',(id,))[0]

    async def action(self,r):
        session=self.mutation(r);d=await r.json();ticket=self.tickets.get(d.get('ticket',''))
        if not ticket or ticket['expires']<time.time() or ticket['csrf']!=session['csrf']:raise web.HTTPConflict(text='确认已过期或已使用，请重新准备操作')
        self.tickets.pop(d['ticket'])
        if ticket['due'] is not None:
            if ticket['due']<=time.time():raise web.HTTPConflict(text='预约时间已过，请重新设置')
            if len(self.store.rows("SELECT id FROM schedules WHERE status='pending'"))>=100:raise web.HTTPConflict(text='预约最多100条，请先取消不需要的任务')
            id=secrets.token_hex(8);self.store.run('INSERT INTO schedules VALUES(?,?,?,?,?,?,?)',(id,ticket['device'],ticket['command'],ticket['value'],ticket['due'],'pending','等待预约时间'))
            return web.json_response({'status':'scheduled','result':'已预约，使用 GMT+8','id':id})
        try:result=await self.execute(ticket['device'],ticket['command'],ticket['value'])
        except ValueError as e:raise web.HTTPConflict(text=str(e))
        return web.json_response(result)

    async def scheduler_once(self):
        now=time.time()
        for s in self.store.rows("SELECT * FROM schedules WHERE status='pending' AND due<=? ORDER BY due",(now,)):
            if time.time()-s['due']>60:
                self.store.run("UPDATE schedules SET status='missed',result='超过预约宽限时间，不补发' WHERE id=?",(s['id'],));continue
            claimed=self.store.run("UPDATE schedules SET status='running' WHERE id=? AND status='pending'",(s['id'],)).rowcount
            if not claimed:continue
            try:
                result=await self.execute(s['device'],s['command'],s['value'],'预约');status=result['status'];message=result['result']
            except ValueError as e:status='failed';message=str(e)
            self.store.run('UPDATE schedules SET status=?,result=? WHERE id=?',(status,message,s['id']))

    async def worker(self):
        count=0
        while True:
            await self.scheduler_once();count+=1
            if count%60==0:self.store.trim()
            await asyncio.sleep(1)
    async def cancel_schedule(self,r):
        self.mutation(r);d=await r.json()
        n=self.store.run("UPDATE schedules SET status='cancelled',result='用户取消' WHERE id=? AND status='pending'",(d.get('id'),)).rowcount
        if not n:raise web.HTTPConflict(text='任务不存在或已开始，无法取消')
        return web.json_response({'ok':True})

    async def preset(self,r):
        self.mutation(r);d=await r.json()
        if 'delete' in d:self.store.run('DELETE FROM presets WHERE id=?',(d['delete'],))
        else:
            if not self.project.get('features',{}).get('presets'):raise web.HTTPForbidden(text='项目未启用常用方案')
            command_spec(self.project,d.get('command'),d.get('value'))
            name=d.get('name','')
            if not isinstance(name,str) or not 1<=len(name.strip())<=48:raise web.HTTPBadRequest(text='请输入1至48字方案名称')
            if len(self.store.rows('SELECT id FROM presets'))>=30:raise web.HTTPConflict(text='最多保存30个方案')
            self.store.run('INSERT INTO presets(name,command,value) VALUES(?,?,?)',(name.strip(),d['command'],d['value']))
        return web.json_response({'ok':True})

    async def history(self,r):
        self.user(r);device=r.query.get('device','')
        return web.json_response(self.store.rows('SELECT stamp,data FROM samples WHERE device=? ORDER BY stamp DESC LIMIT 120',(device,)))
    async def site(self,r):
        self.mutation(r);d=await r.json();title=d.get('title')
        if not isinstance(title,str) or not 1<=len(title.strip())<=48:raise web.HTTPBadRequest(text='网站标题须为1至48字')
        self.store.save_setting('site',{'title':title.strip()});return web.json_response({'ok':True})

    async def start(self,app):self.scheduler_task=asyncio.create_task(self.worker())
    async def cleanup(self,app):
        self.scheduler_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):await self.scheduler_task
        await super().cleanup(app);self.store.close()

def create_app(config,data_dir,project_path):
    from assistant import add_assistant_routes
    s=ProjectPlatform(config,data_dir,load_project(project_path));app=web.Application(client_max_size=16384,middlewares=[errors]);app['platform']=s
    app.add_routes([web.get('/',s.index),web.get('/health',s.health),web.post('/api/login',s.login),web.post('/api/logout',s.logout),web.post('/api/account',s.account),web.get('/api/overview',s.overview),web.get('/api/state',s.state),web.post('/api/devices/{device}/settings',s.device_settings_update),web.get('/gateway/ws',s.websocket),web.post('/api/action/prepare',s.prepare),web.post('/api/action',s.action),web.post('/api/schedules/cancel',s.cancel_schedule),web.post('/api/presets',s.preset),web.get('/api/history',s.history),web.post('/api/site',s.site)])
    add_assistant_routes(app,s)
    app.on_startup.append(s.start);app.on_cleanup.append(s.cleanup);return app

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--config',required=True);p.add_argument('--data',default=str(ROOT/'private/data'));p.add_argument('--project',default=str(ROOT/'project.json'));p.add_argument('--host',default='127.0.0.1');p.add_argument('--port',type=int,default=8767);a=p.parse_args()
    web.run_app(create_app(json.loads(Path(a.config).read_text(encoding='utf-8')),a.data,a.project),host=a.host,port=a.port,access_log=None)
