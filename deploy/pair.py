"""Configure ESP through its password-protected AP. Python stdlib only."""
import argparse,getpass,json,re,sys,urllib.request,urllib.error
from pathlib import Path

def validate_pair(p):
    if not isinstance(p,dict) or p.get('schema')!='gateway-pairing-v1':raise ValueError('不是Gateway配对文件')
    if not isinstance(p.get('device_id'),str) or not re.fullmatch('[A-Za-z0-9_-]{1,48}',p['device_id']):raise ValueError('设备ID格式错误')
    host=p.get('host','')
    if not isinstance(host,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.-]{0,252}',host):raise ValueError('主机格式错误')
    if type(p.get('port')) is not int or not 1<=p['port']<=65535 or p.get('tls') is not True:raise ValueError('仅接受TLS配对配置')
    if not isinstance(p.get('token'),str) or not re.fullmatch('[A-Za-z0-9_-]{16,256}',p['token']):raise ValueError('设备令牌格式错误')
    if not isinstance(p.get('path'),str) or not re.fullmatch(r'/[A-Za-z0-9_./-]{0,127}',p['path']):raise ValueError('路径格式错误')
    return {k:p[k] for k in ['device_id','host','port','path','tls','token']}
def request(path,body=None,nonce=None):
    headers={'Content-Type':'application/json'}
    if nonce:headers['X-Gateway-Nonce']=nonce
    req=urllib.request.Request('http://192.168.4.1'+path,data=None if body is None else json.dumps(body).encode(),headers=headers)
    # A system proxy must not receive the Wi-Fi password or pairing token.
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(req,timeout=12) as r:return json.load(r)
    except urllib.error.HTTPError as e:
        try:reason=json.load(e).get('error','设备拒绝配置')
        except Exception:reason='设备拒绝配置'
        raise ValueError(reason) from None
def main():
    parser=argparse.ArgumentParser();parser.add_argument('file',nargs='?',default=str(Path(__file__).resolve().parents[1]/'private/pairing.json'));args=parser.parse_args()
    path=Path(args.file)
    if path.stat().st_size>4096:raise ValueError('配对文件过大')
    pair=validate_pair(json.loads(path.read_text(encoding='utf-8-sig')))
    print('先连接 Gateway-Setup 热点（正常启动后按BOOT 3秒开启）。')
    input('确认已连接设备热点后按回车：')
    old=request('/api/config');nonce=old.get('nonce')
    if not isinstance(nonce,str) or not nonce:raise ValueError('设备未返回配置授权码，请确认是通用网关固件')
    print('服务器：',pair['host'],'设备ID：',pair['device_id'])
    print('本机网关：',old.get('device_id','未知'))
    ssid=input('ESP以后要连接的2.4GHz Wi-Fi名称：').strip();password=getpass.getpass('Wi-Fi密码（开放Wi-Fi留空）：')
    if not 1<=len(ssid.encode())<=32 or len(password.encode())>63 or (password and len(password.encode())<8):raise ValueError('Wi-Fi名称或密码长度不正确')
    if input('输入 CONNECT 保存并重启ESP（默认只读）：').strip()!='CONNECT':raise SystemExit('已取消')
    pair.update(ssid=ssid,wifi_password=password,clear_wifi_password=not bool(password),remote_write=False)
    result=request('/api/config',pair,nonce);print(result.get('message','配置已保存'))
    print('请切回正常网络，打开 https://'+pair['host']+' 查看网关状态。首次配对保持只读；确认接线和反馈后再在面板开启远程写入。')
if __name__=='__main__':
    try:main()
    except (OSError,ValueError,urllib.error.URLError) as e:print('配对未完成：'+str(e),file=sys.stderr);sys.exit(1)
