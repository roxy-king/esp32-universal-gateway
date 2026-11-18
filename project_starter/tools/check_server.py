"""Public reachability only; no token or MCU control request."""
import argparse,json,urllib.request
p=argparse.ArgumentParser();p.add_argument('url');a=p.parse_args()
url=a.url.rstrip('/')
if not url.startswith(('https://','http://127.0.0.1:','http://localhost:')):raise SystemExit('公网检查请使用HTTPS URL')
try:
    with urllib.request.urlopen(url+'/health',timeout=10) as r:result=json.load(r)
    if result.get('ok') is not True:raise ValueError('health 未通过')
    print('网站/TLS/平台健康检查通过，版本：',result.get('version'))
    print('仍需登录网页确认ESP连接、单片机状态及实际执行结果。')
except Exception as e:raise SystemExit('检查失败：'+str(e))
