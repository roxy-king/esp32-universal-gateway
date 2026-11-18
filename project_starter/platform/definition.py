"""Validated project contract. No executable expressions or arbitrary wire templates."""
import json, re, math
from pathlib import Path

KEY = re.compile(r'^[a-z][a-z0-9_]{0,15}$')
WIRE = re.compile(r'^[A-Z][A-Z0-9_]{0,15}$')

def load_project(path):
    p=json.loads(Path(path).read_text(encoding='utf-8'))
    if p.get('schema')!=1 or not KEY.fullmatch(str(p.get('id',''))):raise ValueError('项目版本或 ID 无效')
    if not isinstance(p.get('name'),str) or not 1<=len(p['name'])<=48:raise ValueError('项目名称须为1至48字')
    if not 2<=p.get('telemetry_timeout',10)<=60:raise ValueError('状态超时须为2至60秒')
    for group in ('fields','commands'):
        items=p.get(group)
        if not isinstance(items,list) or not 1<=len(items)<=16:raise ValueError(group+'须有1至16项')
        seen=set();wires=set()
        for item in items:
            k=item.get('key')
            if not isinstance(k,str) or not KEY.fullmatch(k) or k in seen:raise ValueError('字段或命令 key 无效/重复')
            seen.add(k)
            if not isinstance(item.get('label'),str) or not 1<=len(item['label'])<=48:raise ValueError('标签无效')
            lo,hi=item.get('min'),item.get('max')
            if any(type(v)!=int for v in (lo,hi)) or not 0<=lo<=hi<=65535:raise ValueError('基础协议仅支持0至65535整数，需缩放小数')
            if group=='commands':
                w=item.get('wire')
                if not isinstance(w,str) or not WIRE.fullmatch(w) or w in wires:raise ValueError('wire无效/重复')
                wires.add(w)
                if type(item.get('default'))!=int or not lo<=item['default']<=hi:raise ValueError('默认值无效')
                for flag in ('confirm','schedulable','ai'):
                    if type(item.get(flag))!=bool:raise ValueError(flag+'须为布尔值')
    if any(type(v)!=bool for v in p.get('features',{}).values()):raise ValueError('功能开关无效')
    return p

def command_spec(project,key,value):
    c=next((x for x in project['commands'] if x['key']==key),None)
    if c is None or type(value)!=int or not c['min']<=value<=c['max']:raise ValueError('未知命令或参数超出允许范围')
    if c.get('choices') and str(value) not in c['choices']:raise ValueError('不支持的选项')
    return c

def parse_frame(project,text):
    if len(text)>512:return None
    parts=text.split(',')
    if len(parts)<4 or parts[0]!='P1' or parts[2]!=project['id']:return None
    if parts[1]=='S' and len(parts)==4:
        values={};allowed={x['key']:x for x in project['fields']}
        for pair in parts[3].split(';'):
            kv=pair.split('=')
            if len(kv)!=2 or kv[0] not in allowed or kv[0] in values or not re.fullmatch(r'\d{1,5}',kv[1]):return None
            v=int(kv[1]);f=allowed[kv[0]]
            if not f['min']<=v<=f['max']:return None
            values[kv[0]]=v
        if set(values)!=set(allowed):return None
        return ('state',values)
    if parts[1]=='A' and len(parts)==6 and re.fullmatch('[0-9a-f]{8}',parts[3]) and parts[4] in ('OK','ERR') and re.fullmatch('[a-z0-9_]{1,32}',parts[5]):
        return ('ack',{'id':parts[3],'ok':parts[4]=='OK','message':parts[5]})
    return None
