"""Install a separate project site. Never overwrites the existing gateway service."""
import argparse, getpass, json, os, re, shutil, subprocess, sys, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from project import check,configure

def run(*args):subprocess.run(args,check=True)
def main():
    p=argparse.ArgumentParser();p.add_argument('--domain',required=True);p.add_argument('--email',required=True);p.add_argument('--port',type=int,default=8767);p.add_argument('--username',default='admin');p.add_argument('--dry-run',action='store_true');a=p.parse_args()
    project=check(ROOT)
    if not re.fullmatch(r'[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?',a.domain) or '.' not in a.domain or '..' in a.domain:raise SystemExit('域名格式无效')
    if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',a.email) or not 1024<=a.port<=65535:raise SystemExit('邮箱或端口无效')
    name='link-project-'+project['id'];base=Path('/opt')/name;etc=Path('/etc')/name;data=Path('/var/lib')/name;nginx=Path('/etc/nginx/sites-available')/name
    if a.dry_run:
        print(json.dumps({'service':name,'directory':str(base),'data':str(data),'domain':a.domain,'port':a.port},indent=2));return
    if os.name!='posix' or os.geteuid()!=0:raise SystemExit('请在 Debian/Ubuntu 服务器使用 root 运行')
    if not Path('/etc/debian_version').exists():raise SystemExit('当前安装器支持 Debian/Ubuntu')
    marker=base/'managed-v1'
    deployment=base/'deployment.json'
    if base.exists() and not marker.exists():raise SystemExit('目标目录不是本安装器管理，拒绝覆盖')
    if nginx.exists() and not nginx.read_text().startswith('# '+name):raise SystemExit('已有不属于本项目的 nginx 配置，拒绝覆盖')
    if deployment.exists():
        previous=json.loads(deployment.read_text())
        if previous!={'domain':a.domain,'port':a.port}:raise SystemExit('本项目已固定域名和端口。迁移须人工更新，或使用新项目ID')
    for site in Path('/etc/nginx/sites-enabled').glob('*'):
        if site.name==name or not site.is_file():continue
        for names in re.findall(r'server_name\s+([^;]+);',site.read_text(errors='replace')):
            if a.domain in names.split():raise SystemExit('域名已被其他 nginx 站点使用，拒绝覆盖')
    # Refuse another service listening on the requested loopback port on first install.
    if not marker.exists():
        import socket
        with socket.socket() as sock:
            try:sock.bind(('127.0.0.1',a.port))
            except OSError:raise SystemExit('端口已被占用，请选择其他 --port')
    run('apt-get','update');run('apt-get','install','-y','python3-venv','nginx','certbot','python3-certbot-nginx')
    if subprocess.run(['id','-u',name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode:run('useradd','--system','--no-create-home','--shell','/usr/sbin/nologin',name)
    base.mkdir(exist_ok=True);etc.mkdir(exist_ok=True);data.mkdir(exist_ok=True);marker.touch()
    run('chown',name+':'+name,str(data));os.chmod(data,0o700)
    release=base/'releases'/str(time.time_ns());release.parent.mkdir(exist_ok=True)
    shutil.copytree(ROOT,release,ignore=shutil.ignore_patterns('private','.venv','__pycache__','.git','output','build','ui-review','*.zip'))
    run('python3','-m','venv',str(release/'.venv'));run(str(release/'.venv/bin/pip'),'install','-r',str(release/'requirements.txt'))
    config=etc/'server.json'
    if not config.exists():
        password=getpass.getpass('网页管理员密码（至少8位）：')
        configure(release,'https://'+a.domain,a.username,password)
        shutil.move(str(release/'private/server.json'),config);shutil.move(str(release/'private/pairing.json'),etc/'pairing.json');(release/'private').rmdir()
        os.chmod(etc/'pairing.json',0o600)
    else:
        cfg=json.loads(config.read_text())
        if cfg.get('origin')!='https://'+a.domain:raise SystemExit('现有项目域名不同，请使用独立项目 ID，或人工迁移配置')
    run('chown','root:'+name,str(config));os.chmod(config,0o640)
    current=base/'current';old=current.resolve() if current.exists() else None
    unit=Path('/etc/systemd/system')/(name+'.service')
    unit.write_text(f'''[Unit]
Description=Link Project {project['id']}
After=network.target
[Service]
User={name}
Group={name}
WorkingDirectory={current}
ExecStart={current}/.venv/bin/python {current}/platform/app.py --config {config} --data {data} --project {current}/project.json --host 127.0.0.1 --port {a.port}
Restart=on-failure
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true
ReadWritePaths={data}
UMask=0077
[Install]
WantedBy=multi-user.target
''')
    temp=base/'next';temp.symlink_to(release);os.replace(temp,current)
    try:
        run('systemctl','daemon-reload');run('systemctl','enable','--now',name);run('systemctl','restart',name)
        import urllib.request
        for attempt in range(10):
            try:
                with urllib.request.urlopen(f'http://127.0.0.1:{a.port}/health',timeout=2) as r:assert r.status==200
                break
            except Exception:
                if attempt==9:raise
                time.sleep(1)
        if not nginx.exists():
            nginx.write_text(f'''# {name}
server {{
 listen 80;
 server_name {a.domain};
 location / {{
  proxy_pass http://127.0.0.1:{a.port};
  proxy_http_version 1.1;
  proxy_set_header Host $host;
  proxy_set_header Upgrade $http_upgrade;
  proxy_set_header Connection "upgrade";
  proxy_read_timeout 90s;
 }}
}}
''')
            (Path('/etc/nginx/sites-enabled')/name).symlink_to(nginx)
        run('nginx','-t');run('systemctl','reload','nginx')
        run('certbot','--nginx','--non-interactive','--agree-tos','--redirect','-m',a.email,'-d',a.domain)
    except Exception:
        if old:
            temp.symlink_to(old);os.replace(temp,current);run('systemctl','restart',name)
        raise
    if old:(base/'previous-release').write_text(str(old))
    deployment.write_text(json.dumps({'domain':a.domain,'port':a.port}))
    print('已部署 https://'+a.domain+'；配对文件 '+str(etc/'pairing.json')+'；数据 '+str(data))
    print('让 ESP 连接此域名和本项目令牌。一个 ESP 同时只连接一个服务，不要与原网关并行争用。')
if __name__=='__main__':main()
