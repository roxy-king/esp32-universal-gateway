import hashlib,importlib.util,json,unittest
from pathlib import Path
from unittest.mock import patch,MagicMock
ROOT=Path(__file__).resolve().parents[1]
def module(name):
    spec=importlib.util.spec_from_file_location(name,ROOT/'deploy'/f'{name}.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
install=module('install');pair=module('pair')
class DeploymentTests(unittest.TestCase):
    def test_installer_accepts_eight_not_seven(self):
        c,p=install.credentials('gateway.example.com','user','eight888','seedling-1')
        self.assertTrue(c['password_hash'])
        with self.assertRaises(ValueError):install.credentials('gateway.example.com','user','seven77','seedling-1')
    def test_generated_pair_matches_server(self):
        c,p=install.credentials('gateway.example.com','用户','long-test-password','seedling-1')
        self.assertEqual(c['devices'][p['device_id']]['token_sha256'],hashlib.sha256(p['token'].encode()).hexdigest())
        self.assertEqual(c['password_hash'],hashlib.pbkdf2_hmac('sha256',b'long-test-password',bytes.fromhex(c['password_salt']),600000).hex())
        self.assertEqual(pair.validate_pair(p)['host'],'gateway.example.com')
        self.assertNotIn('long-test-password',json.dumps(c));self.assertNotIn(p['token'],json.dumps(c))
    def test_domains_cannot_inject_shell_or_nginx(self):
        for d in ['https://a.com','a.com;return 200','a.com\nserver{}','-x.com','example.com/','a.com:443']:
            with self.subTest(d=d),self.assertRaises(ValueError):install.validate_domain(d)
    def test_pair_rejects_insecure_or_header_injection(self):
        _,good=install.credentials('gateway.example.com','u','long-test-password','seedling-1')
        for k,v in [('tls',False),('port',True),('port',0),('token','ok\r\nInjected:yes'),('path','/\r\n'),('host','https://x.com'),('device_id','abc\n')]:
            bad=dict(good);bad[k]=v
            with self.subTest(k=k),self.assertRaises(ValueError):pair.validate_pair(bad)
    def test_ap_request_bypasses_proxy_and_sends_nonce(self):
        response=MagicMock();response.read.return_value=b'{"message":"saved"}';response.__enter__.return_value=response
        opener=MagicMock();opener.open.return_value=response
        with patch.object(pair.urllib.request,'build_opener',return_value=opener) as factory:
            self.assertEqual(pair.request('/api/config',{'token':'test-only'},'nonce-test')['message'],'saved')
            self.assertEqual(factory.call_args.args[0].proxies,{})
            req=opener.open.call_args.args[0]
            self.assertEqual(req.full_url,'http://192.168.4.1/api/config');self.assertEqual(req.get_header('X-gateway-nonce'),'nonce-test')
    def test_pair_invalid_schema(self):
        for data in [[],None,{},dict(schema='other')]:
            with self.assertRaises(ValueError):pair.validate_pair(data)
if __name__=='__main__':unittest.main()
