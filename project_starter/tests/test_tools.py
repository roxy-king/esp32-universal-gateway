import importlib.util,json,subprocess,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('project_cli',ROOT/'tools/project.py')
cli=importlib.util.module_from_spec(spec);spec.loader.exec_module(cli)

class ToolTests(unittest.TestCase):
    def test_init_isolated_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest=Path(tmp)/'nursery'
            cli.initialize(dest,'育苗箱','nursery')
            self.assertEqual(cli.check(dest)['id'],'nursery')
            self.assertFalse((dest/'private').exists())
            self.assertFalse((dest/'firmware/prebuilt').exists())
            self.assertFalse((dest/'firmware/output').exists())
            with self.assertRaises(ValueError):cli.initialize(dest,'其他','other')
            self.assertEqual(json.loads((dest/'project.json').read_text(encoding='utf-8'))['id'],'nursery')
    def test_reject_nested_destination(self):
        with self.assertRaises(ValueError):cli.initialize(ROOT/'nested-test-project','测试','nested')
    def test_credentials_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest=Path(tmp)
            with self.assertRaises(ValueError):cli.configure(dest,'http://example.com','admin','test1234')
            with self.assertRaises(ValueError):cli.configure(dest,'https://example.com','admin','short')
            cli.configure(dest,'https://example.com','admin','test1234')
            config=(dest/'private/server.json').read_text();pair=json.loads((dest/'private/pairing.json').read_text())
            self.assertNotIn('test1234',config);self.assertNotIn(pair['token'],config)
            with self.assertRaises(ValueError):cli.configure(dest,'https://example.com','admin','different123')
            self.assertEqual((dest/'private/server.json').read_text(),config)
    def test_deploy_plan_without_mutation(self):
        r=subprocess.run([sys.executable,str(ROOT/'deploy/install.py'),'--domain','demo.example.com','--email','user@example.com','--dry-run'],capture_output=True,text=True)
        self.assertEqual(r.returncode,0,r.stderr);self.assertIn('link-project-bench',r.stdout)
