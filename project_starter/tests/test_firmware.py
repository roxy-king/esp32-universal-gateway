"""Execute actual C parser and business logic on host; Keil validates target syntax separately."""
import os,re,shutil,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class FirmwareTests(unittest.TestCase):
    def test_parser_and_local_timer(self):
        with tempfile.TemporaryDirectory() as directory:
            build=Path(directory);source=(ROOT/'firmware/main.c').read_text()
            source=source.replace('#include <REG52.H>','').replace('void main(void)','void firmware_main(void)')
            source=re.sub(r'^sfr (\w+)=.*?;',r'unsigned char \1;',source,flags=re.M)
            source=re.sub(r'\bxdata\b','',source);source=re.sub(r'\bbit\b','unsigned char',source);source=re.sub(r' interrupt \d+ using \d+','',source)
            source=re.sub(r'static void tx_byte\(unsigned char v\) \{[^\n]+\}',r'static void tx_byte(unsigned char v) { if(out_at<4095)output[out_at++]=v;output[out_at]=0; }',source)
            unit=build/'test.c';unit.write_text('''#include <assert.h>
#include <stdio.h>
unsigned char P0,P2,P3,EA,TMOD,TH0,TL0,ET0,TR0,SCON,TI,ES,SBUF,RI;
char output[4096];int out_at;
'''+source+'''
static void inject(char *s){strcpy(line,s);out_at=0;command();}
int main(void){
 project_init();inject("P1,C,bench,1234abcd,PULSE,3");assert(project_led==1&&project_remaining==3);assert(strstr(output,",OK,applied"));
 project_tick();assert(project_remaining==2);
 inject("P1,C,bench,1234abcd,PULSE,3");assert(project_remaining==2);
 inject("P1,C,bench,1234abcd,PULSE,8");assert(project_remaining==2);assert(strstr(output,"id_conflict"));
 inject("P1,C,bench,1234abce,PULSE,61");assert(project_remaining==2);assert(strstr(output,"out_of_range"));
 project_tick();project_tick();assert(project_led==0&&project_remaining==0);
 inject("P1,C,other,1234abcf,LED,1");assert(project_led==0);
 inject("P1,C,bench,1234abcf,LED,1");assert(project_led==1);
 inject("P1,C,bench,1234abc0,STOP,0");assert(project_led==0);
 inject("P1,C,bench,1234abc1,LED,65536");assert(project_led==0);
 inject("P1,C,bench,1234abc2,LED,-1");assert(project_led==0);
 inject("P1,C,bench,1234abc3,LED,1,extra");assert(project_led==0);
 for(out_at=0;out_at<100;out_at++){RI=1;SBUF='x';uart_isr();}RI=1;SBUF='\\n';uart_isr();assert(!rx_ready&&rx_len==0);
 RI=1;SBUF='A';uart_isr();RI=1;SBUF='\\n';uart_isr();assert(rx_ready&&rx_len==1);
 puts("PASS: real C command parser, duplicate protection, range guards, project isolation, local countdown and overflow recovery");return 0;
}
''',encoding='utf-8')
            exe=build/('test.exe' if os.name=='nt' else 'test')
            if os.name=='nt':
                base=Path(os.environ.get('ProgramFiles(x86)','C:/Program Files (x86)'));candidates=sorted((base/'Microsoft Visual Studio').glob('*/BuildTools/VC/Tools/MSVC/*/bin/Hostx64/x64/cl.exe'))
                if not candidates:self.skipTest('Host C compiler not installed')
                cl=candidates[-1];vc=cl.parents[3];sdk=base/'Windows Kits/10';version=sorted((sdk/'Include').iterdir())[-1].name
                args=[str(cl),'/nologo','/D_CRT_SECURE_NO_WARNINGS',str(unit),str(ROOT/'firmware/logic.c'),f'/I{ROOT / "firmware"}',f'/I{vc / "include"}',f'/Fe{exe}']
                args += [f'/I{sdk / "Include" / version / part}' for part in ('ucrt','shared','um')]
                args += ['/link',f'/LIBPATH:{vc / "lib/x64"}']+[f'/LIBPATH:{sdk / "Lib" / version / part / "x64"}' for part in ('ucrt','um')]
            else:
                cc=os.environ.get('CC') or shutil.which('cc')
                if not cc:self.skipTest('Host C compiler not installed')
                args=[cc,'-std=c99',str(unit),str(ROOT/'firmware/logic.c'),'-I',str(ROOT/'firmware'),'-o',str(exe)]
            r=subprocess.run(args,cwd=build,capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
            r=subprocess.run([str(exe)],capture_output=True,text=True,timeout=10);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
