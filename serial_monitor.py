"""Read ESP32 USB diagnostic port without deliberately resetting it."""
import argparse,serial
p=argparse.ArgumentParser();p.add_argument('port');a=p.parse_args()
s=serial.Serial();s.port=a.port;s.baudrate=115200;s.timeout=1;s.dtr=False;s.rts=False;s.open()
print('Serial monitor open; tap RST to print AP credentials. Ctrl+C to exit.')
try:
    while True:
        line=s.readline()
        if line:print(line.decode('utf-8',errors='replace').rstrip())
except KeyboardInterrupt:pass
finally:s.close()
