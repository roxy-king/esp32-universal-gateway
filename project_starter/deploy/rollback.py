"""Rollback application code only, preserving database and credentials."""
import argparse,os,re,subprocess
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('project_id');p.add_argument('--apply',action='store_true');a=p.parse_args()
if not re.fullmatch('[a-z][a-z0-9_]{0,15}',a.project_id):raise SystemExit('无效项目ID')
base=Path('/opt')/('link-project-'+a.project_id)
target=Path((base/'previous-release').read_text()).resolve()
if target.parent!=(base/'releases').resolve() or not (target/'platform/app.py').is_file():raise SystemExit('回退路径无效')
print('将回退代码到',target,'；数据库与账号不回退。')
if a.apply:
    nxt=base/'rollback-next';nxt.symlink_to(target);os.replace(nxt,base/'current')
    subprocess.run(['systemctl','restart','link-project-'+a.project_id],check=True)
