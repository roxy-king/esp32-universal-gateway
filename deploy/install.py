"""Interactive Debian installer, stdlib only. Never edits another site's files."""
import getpass,hashlib,json,os,re,secrets,shutil,socket,subprocess,sys,time,urllib.request
from pathlib import Path

DOMAIN=re.compile(r'(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$')
ROOT=Path(__file__).resolve().parents[1]
CONFIG=Path('/etc/esp-gateway');DEST=Path('/opt/esp-gateway');MARK=CONFIG/'installer-v1'
SITE=Path('/etc/nginx/sites-available/esp-gateway');LINK=Path('/etc/nginx/sites-enabled/esp-gateway')
def run(*args):subprocess.run(args,check=True)
def validate_domain(domain):
    domain=domain.strip().lower()
    if not DOMAIN.fullmatch(domain):raise ValueError('请输入完整域名，不含协议、端口或路径')
    return domain
def credentials(domain,user,password,device):
    if not user.strip() or len(user)>100 or not 8<=len(password)<=256:raise ValueError('用户名必填，密码8至256位')
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,48}',device):raise ValueError('设备ID格式错误')
    token=secrets.token_urlsafe(32);salt=secrets.token_hex(16)
    c=dict(origin='https://'+validate_domain(domain),username=user.strip(),password_salt=salt,password_hash=hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(salt),600000).hex(),devices={device:{'token_sha256':hashlib.sha256(token.encode()).hexdigest()}})
    p=dict(schema='gateway-pairing-v1',device_id=device,host=domain,port=443,path='/gateway/ws',tls=True,token=token)
    return c,p
def http_site(domain):
    return f'''server {{
 listen 80;
 server_name {domain};
 location /.well-known/acme-challenge/ {{ root /var/www/gateway-acme; }}
 location / {{ return 200 "Gateway setup"; }}
}}
'''
def write_json(p,value,mode=0o600):
    temp=p.with_suffix('.tmp');temp.write_text(json.dumps(value,indent=2),encoding='utf-8');os.chmod(temp,mode);temp.replace(p)
def main():
    if not hasattr(os,'geteuid') or os.geteuid()!=0:raise SystemExit('请在Debian服务器以root运行')
    import grp
    os.umask(0o077)
    if not Path('/etc/debian_version').exists():raise SystemExit('此向导支持Debian/Ubuntu系统')
    if not MARK.exists() and any(p.exists() for p in [CONFIG,DEST,SITE,LINK,Path('/etc/systemd/system/esp-gateway.service')]):raise SystemExit('发现已有同名部署，拒绝覆盖。请先核查 /opt/esp-gateway 与 /etc/esp-gateway。')
    if (CONFIG/'server.json').exists():
        c=json.loads((CONFIG/'server.json').read_text());domain=validate_domain(c['origin'].removeprefix('https://'))
        print('继续现有向导部署，保留账号和令牌：',domain)
        if not (CONFIG/'pairing.json').exists():raise SystemExit('缺少配对文件，不会擅自更换令牌。请恢复备份。')
    else:
        domain=validate_domain(input('已解析到本服务器的独立域名：'))
        user=input('网页登录用户名：').strip();password=getpass.getpass('网页登录密码（至少8位）：')
        if password!=getpass.getpass('再次输入密码：'):raise SystemExit('密码不一致')
        device='gateway-'+secrets.token_hex(4)
        c,p=credentials(domain,user,password,device)
        print(f'将安装到 /opt/esp-gateway，域名 {domain}，设备ID {device}。')
        print('不会改动其他Nginx站点。需要DNS已生效、80/443可从公网访问。')
        if input('输入 INSTALL 开始：').strip()!='INSTALL':raise SystemExit('已取消')
        CONFIG.mkdir(parents=True,exist_ok=True);MARK.write_text('esp-gateway-installer-v1\n');write_json(CONFIG/'pairing.json',p);write_json(CONFIG/'server.json',c)
    email=input('证书续期联系邮箱：').strip()
    if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email) or email.startswith('-'):raise SystemExit('邮箱格式不正确')
    # Resolve early; Certbot will check actual public routing later.
    socket.getaddrinfo(domain,443)
    if subprocess.run(['systemctl','is-active','--quiet','esp-gateway']).returncode:
        with socket.socket() as probe:
            try:probe.bind(('127.0.0.1',8766))
            except OSError:raise SystemExit('本机8766端口被其他服务占用，拒绝覆盖。')
    for f in Path('/etc/nginx/sites-enabled').glob('*'):
        if f.resolve()==SITE.resolve() or not f.is_file():continue
        text=f.read_text(errors='replace')
        if any(domain in names.split() for names in re.findall(r'\bserver_name\s+([^;]+);',text)):raise SystemExit('其他Nginx站点已使用这个域名：'+str(f))
    print('[1/5] 安装系统依赖')
    run('apt-get','update');run('apt-get','install','-y','python3-venv','python3-pip','nginx','certbot')
    if subprocess.run(['id','esp-gateway'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode:run('useradd','--system','--home',str(DEST),'--shell','/usr/sbin/nologin','esp-gateway')
    DEST.mkdir(exist_ok=True);os.chmod(DEST,0o755);(DEST/'server').mkdir(exist_ok=True);os.chmod(DEST/'server',0o755)
    for name in ['server.py','index.html','requirements.txt']:
        shutil.copy2(ROOT/'server'/name,DEST/'server'/name);os.chmod(DEST/'server'/name,0o644)
    print('[2/5] 安装Python服务')
    run('python3','-m','venv',str(DEST/'venv'));run(str(DEST/'venv/bin/pip'),'install','-r',str(DEST/'server/requirements.txt'))
    # venv was created under private umask; grant service user read/execute, never write.
    run('chmod','-R','a+rX',str(DEST/'venv'))
    gid=grp.getgrnam('esp-gateway').gr_gid;os.chown(CONFIG,0,gid);os.chmod(CONFIG,0o750);os.chown(CONFIG/'server.json',0,gid);os.chmod(CONFIG/'server.json',0o640)
    service=Path('/etc/systemd/system/esp-gateway.service');shutil.copy2(ROOT/'server/gateway.service',service);os.chmod(service,0o644)
    run('systemctl','daemon-reload');run('systemctl','enable','esp-gateway');run('systemctl','restart','esp-gateway');run('systemctl','is-active','--quiet','esp-gateway')
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for attempt in range(10):
        try:
            with opener.open('http://127.0.0.1:8766/',timeout=3) as r:
                if r.status==200:break
        except OSError:
            if attempt==9:raise SystemExit('服务未通过本机HTTP检查，请查看 journalctl -u esp-gateway')
            time.sleep(1)
    print('[3/5] 配置域名和证书')
    Path('/var/www/gateway-acme').mkdir(parents=True,exist_ok=True);os.chmod('/var/www/gateway-acme',0o755)
    cert=Path('/etc/letsencrypt/live')/domain/'fullchain.pem'
    if not cert.exists():
        SITE.write_text(http_site(domain));os.chmod(SITE,0o644)
        if not LINK.exists():LINK.symlink_to(SITE)
        run('nginx','-t');run('systemctl','enable','--now','nginx');run('systemctl','reload','nginx')
        # ACME webroot and generated challenge descendants must be readable by nginx.
        old=os.umask(0o022)
        try:run('certbot','certonly','--webroot','-w','/var/www/gateway-acme','-d',domain,'--email',email,'--agree-tos','--non-interactive','--key-type','rsa')
        finally:os.umask(old)
    print('[4/5] 开启HTTPS及自动续期')
    SITE.write_text((ROOT/'server/nginx.conf.example').read_text().replace('gateway.example.com',domain));os.chmod(SITE,0o644)
    if not LINK.exists():LINK.symlink_to(SITE)
    run('nginx','-t');run('systemctl','enable','--now','nginx');run('systemctl','reload','nginx')
    hook=Path('/etc/letsencrypt/renewal-hooks/deploy/esp-gateway-nginx.sh');hook.parent.mkdir(parents=True,exist_ok=True);hook.write_text('#!/bin/sh\nnginx -t && systemctl reload nginx\n');os.chmod(hook,0o755);run('systemctl','enable','--now','certbot.timer')
    print('[5/5] 配对文件已准备')
    print('控制台：https://'+domain)
    print('配对文件：/etc/esp-gateway/pairing.json（含设备令牌，请勿上传GitHub或公开分享）')
    print('下载该文件到电脑，连接ESP热点，再运行 connect.cmd。')
    print('若使用 setup.cmd，向导会继续自动下载配对文件。')
if __name__=='__main__':
    try:main()
    except (ValueError,OSError,subprocess.CalledProcessError) as e:
        print('部署未完成：'+str(e),file=sys.stderr);print('修复DNS/网络/依赖后可重跑此向导；已生成的账号和令牌会保留。',file=sys.stderr);sys.exit(1)
