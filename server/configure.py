import getpass,json,secrets,hashlib,os
from pathlib import Path
from urllib.parse import urlparse
from server import password_hash,ID,digest
if __name__=='__main__':
    target=Path(__file__).parent/'private'
    if target.exists():raise SystemExit('private 已存在，拒绝覆盖。新增设备请按手册操作。')
    origin=input('控制台完整地址（如 https://gateway.example.com；本机测试 http://127.0.0.1:8766）：').strip().rstrip('/')
    u=urlparse(origin)
    if u.scheme not in ('http','https') or not u.hostname or u.path or u.query or u.fragment or u.username:raise SystemExit('地址格式不正确')
    name=input('登录用户名：').strip();password=getpass.getpass('登录密码（至少8位）：')
    if not name or len(password)<8 or len(password)>256:raise SystemExit('用户名或密码长度不正确')
    if password!=getpass.getpass('再次输入密码：'):raise SystemExit('密码不一致')
    device=input('控制台登记 ID（自定，ESP 无需相同）：').strip()
    if not ID.fullmatch(device):raise SystemExit('设备 ID 格式错误')
    salt=secrets.token_hex(16);token=secrets.token_urlsafe(32)
    config=dict(origin=origin,username=name,password_salt=salt,password_hash=password_hash(password,salt),devices={device:{'token_sha256':digest(token)}})
    target.mkdir(mode=0o700)
    p=target/'server.json';p.write_text(json.dumps(config,indent=2),encoding='utf-8');os.chmod(p,0o600)
    p=target/'device-token.txt';p.write_text(token,encoding='utf-8');os.chmod(p,0o600)
    print('配置已生成。将 private/device-token.txt 内令牌填入 ESP32 面板。勿上传令牌文件到网站静态目录。')
