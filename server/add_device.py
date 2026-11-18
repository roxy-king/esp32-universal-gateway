"""Add independent device credentials offline; restart the service afterwards."""
import argparse,json,secrets,os
from pathlib import Path
from server import ID,digest
p=argparse.ArgumentParser();p.add_argument('--config',type=Path,required=True);p.add_argument('--device',required=True);p.add_argument('--token-out',type=Path,required=True);a=p.parse_args()
if not ID.fullmatch(a.device):raise SystemExit('Invalid device ID')
c=json.loads(a.config.read_text(encoding='utf-8'))
if a.device in c['devices'] or a.token_out.exists():raise SystemExit('Device or token file already exists')
token=secrets.token_urlsafe(32);c['devices'][a.device]={'token_sha256':digest(token)}
with a.token_out.open('x',encoding='utf-8') as f:f.write(token)
os.chmod(a.token_out,0o600)
# Write in place to preserve the existing Linux service group permissions.
a.config.write_text(json.dumps(c,indent=2),encoding='utf-8')
print('Device added. Restart server and put this device token into ESP32 settings.')
