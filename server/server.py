"""Gateway v1 reference server. Bind loopback; put nginx HTTPS in front for WAN."""
import argparse, asyncio, hashlib, hmac, json, math, re, secrets, time
from collections import deque
from pathlib import Path
from aiohttp import web, WSMsgType

ROOT=Path(__file__).parent
ID=re.compile(r'^[A-Za-z0-9_-]{1,48}$')
def digest(value): return hashlib.sha256(value.encode()).hexdigest()
def password_hash(value,salt):return hashlib.pbkdf2_hmac('sha256',value.encode(),bytes.fromhex(salt),600000).hex()

def validate_command(data,mode):
    if not isinstance(data,dict):raise ValueError('命令必须是JSON对象')
    encoding=data.get('encoding');text=data.get('data')
    if not isinstance(text,str) or not text:raise ValueError('请输入命令')
    if encoding=='text' and mode=='line':
        if len(text.encode())>512 or any(ord(c)<32 or ord(c)==127 for c in text):raise ValueError('文本最多512字节，不含换行或控制字符；行尾由网关添加')
    elif encoding=='hex' and mode=='hex':
        if len(text)>1024 or len(text)%2 or not re.fullmatch('[0-9a-fA-F]+',text):raise ValueError('HEX应为1至512字节的连续十六进制字符')
    else:raise ValueError('命令编码与网关传输模式不一致')
    return encoding,text

class GatewayServer:
    def __init__(self,config):
        self.config=config; self.sessions={};self.failures={};self.devices={};self.events=deque(maxlen=200);self.seq=0
        self.pending={};self.last_command={}
    def event(self,device,kind,detail):
        self.seq+=1;self.events.append(dict(seq=self.seq,time=time.time(),device=device,type=kind,detail=detail))
    def user(self,r):
        sid=r.cookies.get('gateway_session','');session=self.sessions.get(sid)
        if not session or session['expires']<time.time():raise web.HTTPUnauthorized(text='请重新登录')
        return session
    def mutation(self,r):
        session=self.user(r)
        if r.headers.get('Origin')!=self.config['origin'] or not hmac.compare_digest(r.headers.get('X-CSRF-Token',''),session['csrf']):raise web.HTTPForbidden(text='请求来源或会话不匹配')
        return session
    async def index(self,r):return web.FileResponse(ROOT/'index.html',headers={'Cache-Control':'no-store'})
    async def login(self,r):
        if r.headers.get('Origin')!=self.config['origin']:raise web.HTTPForbidden(text='请求来源不匹配')
        now=time.time();ip=r.remote or 'unknown'
        # Behind nginx all users may share one bucket; conservative for small installations.
        if len(self.failures)>1024:self.failures={k:v for k,v in self.failures.items() if now-v[-1]<300}
        attempts=[t for t in self.failures.get(ip,[]) if now-t<300]
        if len(attempts)>=10:raise web.HTTPTooManyRequests(text='登录尝试过多，5分钟后再试')
        d=await r.json();username=d.get('username','');password=d.get('password','')
        if not isinstance(username,str) or not isinstance(password,str) or len(password)>256:raise web.HTTPBadRequest(text='登录参数无效')
        self.failures[ip]=attempts+[now]
        computed=await asyncio.to_thread(password_hash,password,self.config['password_salt'])
        if not hmac.compare_digest(username.encode(),self.config['username'].encode()) or not hmac.compare_digest(computed,self.config['password_hash']):raise web.HTTPUnauthorized(text='用户名或密码错误')
        self.failures.pop(ip,None)
        self.sessions={k:v for k,v in self.sessions.items() if v['expires']>now}
        if len(self.sessions)>=64:self.sessions.pop(next(iter(self.sessions)))
        sid=secrets.token_urlsafe(32);session={'csrf':secrets.token_urlsafe(24),'expires':now+43200};self.sessions[sid]=session
        response=web.json_response({'csrf':session['csrf']});response.set_cookie('gateway_session',sid,httponly=True,secure=self.config['origin'].startswith('https:'),samesite='Strict',max_age=43200);return response
    async def logout(self,r):
        self.mutation(r);self.sessions.pop(r.cookies.get('gateway_session'),None);response=web.json_response({'ok':True});response.del_cookie('gateway_session');return response
    async def state(self,r):
        session=self.user(r);now=time.time();devices=[]
        for ident in self.config['devices']:
            d=self.devices.get(ident,{});s=d.get('status',{});connected=bool(d.get('ws') is not None and not d['ws'].closed and now-d.get('seen',0)<20)
            devices.append(dict(id=ident,connected=connected,status=s,last_seen=d.get('seen')))
        return web.json_response({'csrf':session['csrf'],'devices':devices,'events':list(self.events)})
    async def command(self,r):
        self.mutation(r);ident=r.match_info['device'];device=self.devices.get(ident)
        if not device or device['ws'].closed or time.time()-device.get('seen',0)>20:raise web.HTTPConflict(text='网关离线或状态过期，未发送')
        if not device['status'].get('remote_write'):raise web.HTTPConflict(text='网关处于只读模式，请在配置热点开启远程写入')
        if ident in self.pending:raise web.HTTPConflict(text='上一条命令仍在等待网关确认')
        if time.monotonic()-self.last_command.get(ident,0)<0.2:raise web.HTTPTooManyRequests(text='操作过快')
        try:encoding,data=validate_command(await r.json(),device['status'].get('mode'))
        except ValueError as e:raise web.HTTPBadRequest(text=str(e))
        ident_cmd=secrets.token_hex(16);future=asyncio.get_running_loop().create_future()
        self.pending[ident]=(ident_cmd,future);self.last_command[ident]=time.monotonic()
        payload=dict(v=1,type='tx',id=ident_cmd,boot_id=device['status']['boot_id'],encoding=encoding,data=data,expires_at=time.time()+5)
        self.event(ident,'tx',{'id':ident_cmd,'encoding':encoding,'data':data})
        try:
            await device['ws'].send_json(payload)
            result=await asyncio.wait_for(future,6)
            return web.json_response(result)
        except (asyncio.TimeoutError,ConnectionError,RuntimeError):
            self.event(ident,'unknown',{'id':ident_cmd,'result':'未收到网关确认；可能已发送，请查看设备反馈，不会重发'})
            return web.json_response({'ok':False,'result':'结果未知，可能已发送；未自动重发','id':ident_cmd},status=504)
        finally:self.pending.pop(ident,None)
    async def websocket(self,r):
        ident=r.headers.get('X-Device-Id','');expected=self.config['devices'].get(ident)
        token=r.headers.get('Authorization','')
        if not expected or not token.startswith('Bearer ') or not hmac.compare_digest(digest(token[7:]),expected['token_sha256']):raise web.HTTPUnauthorized()
        previous=self.devices.get(ident)
        if previous and not previous['ws'].closed:raise web.HTTPConflict(text='Device already connected')
        ws=web.WebSocketResponse(heartbeat=15,max_msg_size=4096)
        device={'ws':ws,'status':{},'seen':0};self.devices[ident]=device
        try:await ws.prepare(r)
        except Exception:
            if self.devices.get(ident) is device:self.devices.pop(ident,None)
            raise
        self.event(ident,'connection','WebSocket 已连接，等待网关自报')
        count=0;window=time.monotonic()
        try:
            async for msg in ws:
                if msg.type!=WSMsgType.TEXT:break
                if time.monotonic()-window>=1:window=time.monotonic();count=0
                count+=1
                if count>40:await ws.close(code=1008,message=b'rate limit');break
                try:d=json.loads(msg.data)
                except ValueError:break
                if not isinstance(d,dict) or d.get('v')!=1:break
                kind=d.get('type')
                if kind in ('hello','status'):
                    if d.get('device_id')!=ident or not ID.fullmatch(str(d.get('boot_id',''))) or d.get('mode') not in ('line','hex') or not isinstance(d.get('remote_write'),bool):break
                    device['status']=d;device['seen']=time.time()
                elif kind=='rx':
                    data=d.get('data')
                    if d.get('encoding')!='hex' or not isinstance(data,str) or len(data)>1024 or len(data)%2 or not re.fullmatch('[0-9a-fA-F]*',data):break
                    self.event(ident,'rx',{'hex':data,'text':bytes.fromhex(data).decode('utf-8',errors='replace')})
                elif kind=='ack':
                    if not isinstance(d.get('ok'),bool) or not isinstance(d.get('result'),str) or len(d['result'])>160:break
                    pending=self.pending.get(ident)
                    if pending and pending[0]==d.get('id') and not pending[1].done():
                        self.event(ident,'ack',d);pending[1].set_result(d)
        finally:
            await ws.close();self.event(ident,'connection','网关断开；本地设备状态未知')
            pending=self.pending.get(ident)
            if pending and not pending[1].done():pending[1].set_result({'ok':False,'result':'连接中断，执行结果未知，不会重发'})
        return ws
    async def cleanup(self,app):
        for d in self.devices.values():await d['ws'].close(code=1001,message=b'shutdown')

@web.middleware
async def errors(r,handler):
    try:response=await handler(r)
    except web.HTTPException as e:
        response=web.json_response({'error':e.text},status=e.status)
    except (ValueError,TypeError,AttributeError):response=web.json_response({'error':'请求格式无效'},status=400)
    response.headers['Cache-Control']='no-store';response.headers['X-Content-Type-Options']='nosniff';response.headers['X-Frame-Options']='DENY'
    return response

def create_app(config):
    s=GatewayServer(config);app=web.Application(client_max_size=4096,middlewares=[errors]);app['gateway']=s
    app.add_routes([web.get('/',s.index),web.post('/api/login',s.login),web.post('/api/logout',s.logout),web.get('/api/state',s.state),web.post('/api/devices/{device}/tx',s.command),web.get('/gateway/ws',s.websocket)])
    app.on_cleanup.append(s.cleanup);return app

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--config',required=True);parser.add_argument('--host',default='127.0.0.1');parser.add_argument('--port',type=int,default=8766);args=parser.parse_args()
    config=json.loads(Path(args.config).read_text(encoding='utf-8'))
    web.run_app(create_app(config),host=args.host,port=args.port,access_log=None)
