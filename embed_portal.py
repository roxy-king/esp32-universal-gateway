from pathlib import Path
p=Path(__file__).parent
s=(p/'portal.html').read_text(encoding='utf-8')
assert ')GATEWAY"' not in s
(p/'firmware/UniversalGateway/Portal.h').write_text('#pragma once\nstatic const char PORTAL[] PROGMEM = R"GATEWAY('+s+')GATEWAY";\n',encoding='utf-8')
