#include <Arduino.h>
#include <WiFi.h>
#include <WebServer.h>
#include <WebSocketsClient.h>
#include <Preferences.h>
#include <ArduinoJson.h>
#include <time.h>
#include "RootCA.h"
#include "Portal.h"

// Generic UART gateway: delivery acknowledgement is NOT application execution.
HardwareSerial uart(1);
WebServer http(80);
WebSocketsClient ws;
Preferences nv;
JsonDocument cfg;
String apPassword, apName, nonce, auth, ca, seen[128], logs[24];
unsigned seenAt=0, logAt=0;
bool ap=false, started=false, online=false, discarding=false;
uint32_t rxBytes=0,txBytes=0,drops=0,lastRx=0,lastHeartbeat=0,lastRetry=0,hold=0,rebootAt=0,lastTx=0;
uint32_t publishWindow=0,publishCount=0;
uint8_t buf[512]; size_t used=0;
String bootId;
uint32_t wifiStartAt=0,wifiBeginAt=0;
bool scanning=false;

String randomHex(){return String(esp_random(),HEX)+String(esp_random(),HEX);}
void logEvent(const String& s){logs[logAt++%24]=String(millis()/1000)+"s "+s.substring(0,140);Serial.println(s);}
bool safeText(const String&s,size_t max){if(s.length()>max)return false;for(size_t i=0;i<s.length();i++)if(uint8_t(s[i])<32||s[i]==127)return false;return true;}
bool safeId(const String&s){if(!s.length()||s.length()>48)return false;for(char c:s)if(!isalnum(c)&&c!='-'&&c!='_')return false;return true;}
bool safePin(int n){return n==4||n==5||n==6||n==7||n==15||n==16||n==17||n==18;}
void defaults(){
 cfg["name"]="通用通信网关";cfg["device_id"]="esp-"+String(uint32_t(ESP.getEfuseMac()),HEX);
 cfg["ssid"]="";cfg["wifi_password"]="";cfg["host"]="";cfg["port"]=443;cfg["path"]="/gateway/ws";
 cfg["tls"]=true;cfg["token"]="";cfg["ca"]="";cfg["baud"]=9600;cfg["rx"]=18;cfg["tx"]=17;
 cfg["format"]="8N1";cfg["mode"]="line";cfg["ending"]="crlf";cfg["idle_ms"]=20;cfg["ntp"]="pool.ntp.org";
 cfg["remote_write"]=false;
}
String validate(JsonDocument& c,bool cloudRequired=true){
 if(!String(c["name"]|"").length()||!safeText(c["name"]|"",48)||!safeId(c["device_id"]|""))return "设备名称或ID不正确";
 String ssid=c["ssid"]|"",pass=c["wifi_password"]|"",host=c["host"]|"",path=c["path"]|"",token=c["token"]|"",cert=c["ca"]|"",ntp=c["ntp"]|"";
 if(!ssid.length()||!safeText(ssid,32)||pass.length()>63||(pass.length()&&pass.length()<8))return "Wi-Fi名称或密码长度不正确";
 if((cloudRequired&&host.length()<1)||host.length()>253)return "请填写服务器主机名或IPv4地址，不含协议";
 for(char ch:host)if(!isalnum(ch)&&ch!='.'&&ch!='-')return "主机名不能含协议、端口、路径或空格";
 if(!path.startsWith("/")||!safeText(path,128)||path.indexOf(' ')>=0)return "路径须以 / 开头，不能含空格";
 int port=c["port"]|0,baud=c["baud"]|0;
 if(port<1||port>65535||baud<1200||baud>115200)return "端口或波特率超出范围";
 if(!safePin(c["rx"]|-1)||!safePin(c["tx"]|-1)||c["rx"]==c["tx"])return "串口引脚不合法或重复";
 String fmt=c["format"]|"",mode=c["mode"]|"",ending=c["ending"]|"";
 if(fmt!="8N1"&&fmt!="8E1"&&fmt!="8O1"&&fmt!="8N2")return "不支持的串口格式";
 if(mode!="line"&&mode!="hex")return "不支持的传输模式";
 if(ending!="crlf"&&ending!="lf"&&ending!="none")return "不支持的行尾";
 if(!safeText(token,256)||((cloudRequired||token.length())&&token.length()<16))return "设备令牌至少16字符，不允许换行";
 if(!safeText(ntp,128)||!ntp.length()||ntp.indexOf(' ')>=0)return "NTP服务器不正确";
 if((c["idle_ms"]|0)<5||(c["idle_ms"]|0)>200)return "分包间隔应为5至200毫秒";
 if(cert.length()>4096||(cert.length()&&(!cert.startsWith("-----BEGIN CERTIFICATE-----")||cert.indexOf("-----END CERTIFICATE-----")<0)))return "CA证书格式不正确";
 if(!c["tls"].is<bool>()||!c["remote_write"].is<bool>())return "开关类型不正确";
 return "";
}
bool local(){return ap&&http.client().localIP()==WiFi.softAPIP();}
void jsonReply(JsonDocument& d,int status=200){String s;serializeJson(d,s);http.sendHeader("Cache-Control","no-store");http.send(status,"application/json",s);}
void error(const String&s,int code=400){JsonDocument d;d["error"]=s;jsonReply(d,code);}
bool mutation(){if(!local()||http.header("X-Gateway-Nonce")!=nonce){error("请通过设备热点重新打开面板",403);return false;}return true;}
void startAP(){
 if(ap)return;
 WiFi.mode(WIFI_AP_STA);
 ap=WiFi.softAP(apName.c_str(),apPassword.c_str());
 if(ap){nonce=randomHex();logEvent("配置热点已开启 "+apName);Serial.println("AP password: "+apPassword);}
}
void status(JsonDocument& d){
 d["firmware"]="UniversalGateway 1.1.1";d["device_id"]=cfg["device_id"];d["boot_id"]=bootId;
 d["wifi"]=WiFi.status()==WL_CONNECTED;d["ip"]=WiFi.localIP().toString();d["rssi"]=WiFi.status()==WL_CONNECTED?WiFi.RSSI():0;
 d["ssid"]=cfg["ssid"];d["cloud_configured"]=String(cfg["host"]|"").length()>0;
 d["wifi_message"]=WiFi.status()==WL_CONNECTED?"已连接 Wi-Fi":!String(cfg["ssid"]|"").length()?"请选择 Wi-Fi":WiFi.status()==WL_NO_SSID_AVAIL?"找不到热点，请确认已开启 2.4 GHz":WiFi.status()==WL_CONNECT_FAILED?"连接失败，请检查密码和路由器设置":wifiStartAt&&uint32_t(millis()-wifiStartAt)<30000?"正在连接，请稍候…":"尚未连接，请检查密码、信号和路由器 DHCP；可重新连接";
 d["clock"]=time(nullptr)>1700000000;d["cloud"]=online;d["rx_bytes"]=rxBytes;d["tx_bytes"]=txBytes;d["dropped_frames"]=drops;
 d["last_rx_ms"]=rxBytes?int64_t(uint32_t(millis()-lastRx)):-1;d["uptime_s"]=millis()/1000;d["free_heap"]=ESP.getFreeHeap();
 d["remote_write"]=cfg["remote_write"];d["mode"]=cfg["mode"];
}
void setupPortal(){
 const char* headers[]={"X-Gateway-Nonce"};http.collectHeaders(headers,1);
 http.on("/",HTTP_GET,[]{if(!local()){error("管理面板仅限设备热点",403);return;}http.sendHeader("Cache-Control","no-store");http.send_P(200,"text/html; charset=utf-8",PORTAL);});
 http.on("/api/config",HTTP_GET,[]{if(!local()){error("仅限配置热点",403);return;}JsonDocument d;d.set(cfg);d.remove("wifi_password");d.remove("token");d["token_set"]=String(cfg["token"]|"").length()>0;d["nonce"]=nonce;jsonReply(d);});
 http.on("/api/status",HTTP_GET,[]{if(!local()){error("仅限配置热点",403);return;}JsonDocument d;status(d);JsonArray a=d["logs"].to<JsonArray>();for(unsigned i=logAt>24?logAt-24:0;i<logAt;i++)a.add(logs[i%24]);jsonReply(d);});
 http.on("/api/scan",HTTP_POST,[]{
  if(!mutation())return;
  if(wifiBeginAt){error("正在提交连接，请稍后重试",409);return;}
  if(!scanning&&WiFi.status()!=WL_CONNECTED){WiFi.setAutoReconnect(false);WiFi.disconnect(false,false);wifiStartAt=0;lastRetry=millis();}
  if(!scanning){WiFi.scanDelete();int result=WiFi.scanNetworks(true,true);if(result==WIFI_SCAN_FAILED){error("扫描启动失败，请重试",503);return;}scanning=true;}
  JsonDocument d;d["running"]=true;jsonReply(d);
 });
 http.on("/api/scan",HTTP_GET,[]{
  if(!local()){error("仅限配置热点",403);return;}
  int count=WiFi.scanComplete();JsonDocument d;d["running"]=count==WIFI_SCAN_RUNNING;
  if(count==WIFI_SCAN_FAILED){scanning=false;error("扫描失败，请重新扫描",503);return;}
  JsonArray a=d["networks"].to<JsonArray>();
  for(int i=0;i<count&&a.size()<40;i++){String ssid=WiFi.SSID(i);if(!ssid.length())continue;bool duplicate=false;for(JsonObject n:a)if(n["ssid"]==ssid)duplicate=true;if(duplicate)continue;JsonObject n=a.add<JsonObject>();n["ssid"]=ssid;n["rssi"]=WiFi.RSSI(i);n["open"]=WiFi.encryptionType(i)==WIFI_AUTH_OPEN;}
  jsonReply(d);if(count>=0)scanning=false;
 });
 http.on("/api/wifi",HTTP_POST,[]{
  if(!mutation())return;
  if(scanning&&WiFi.scanComplete()==WIFI_SCAN_RUNNING){error("扫描尚未结束，请稍候",409);return;}
  JsonDocument patch,next;if(http.arg("plain").length()>512||deserializeJson(patch,http.arg("plain"))||!patch["ssid"].is<String>()||!patch["password"].is<String>()){error("Wi-Fi 参数无效");return;}
  next.set(cfg);next["ssid"]=patch["ssid"];next["wifi_password"]=patch["password"];
  String why=validate(next,false);if(why.length()){error(why);return;}
  String saved;serializeJson(next,saved);if(nv.putString("config",saved)!=saved.length()){error("保存失败",500);return;}
  cfg.set(next);wifiBeginAt=millis()+500;
  JsonDocument d;d["message"]="已保存，正在连接；请保持连接网关热点查看结果";jsonReply(d);
 });
 http.on("/api/config",HTTP_POST,[]{
  if(!mutation())return;
  JsonDocument patch,next;if(http.arg("plain").length()>6500||deserializeJson(patch,http.arg("plain"))||!patch.is<JsonObject>()){error("配置JSON无效或过大");return;}
  next.set(cfg);
  for(JsonPair p:patch.as<JsonObject>()){
   String key=p.key().c_str();if(!cfg[key].isNull())next[key]=p.value();
  }
  if(String(patch["token"]|"").isEmpty())next["token"]=cfg["token"];
  if(String(patch["wifi_password"]|"").isEmpty()&&!(patch["clear_wifi_password"]|false))next["wifi_password"]=cfg["wifi_password"];
  if(patch["clear_wifi_password"]|false)next["wifi_password"]="";
  String why=validate(next);if(why.length()){error(why);return;}
  String s;serializeJson(next,s);if(nv.putString("config",s)!=s.length()){error("保存失败",500);return;}
  JsonDocument d;d["message"]="配置已保存，即将重启；修改后请重新连接热点";jsonReply(d);rebootAt=millis()+1200;
 });
 http.on("/api/reboot",HTTP_POST,[]{if(!mutation())return;JsonDocument d;d["message"]="正在重启";jsonReply(d);rebootAt=millis()+1000;});
 http.on("/api/reset",HTTP_POST,[]{if(!mutation())return;if(http.arg("plain")!="RESET"){error("恢复出厂确认不正确");return;}nv.remove("config");JsonDocument d;d["message"]="已清除项目配置，热点密码保留";jsonReply(d);rebootAt=millis()+1000;});
 http.onNotFound([]{error("Not found",404);});http.begin();
}
bool sendDoc(JsonDocument&d){if(!online)return false;String s;serializeJson(d,s);return ws.sendTXT(s);}
void ack(const String&id,bool ok,const char*reason){JsonDocument d;d["v"]=1;d["type"]="ack";d["id"]=id;d["ok"]=ok;d["result"]=reason;sendDoc(d);}
void onWS(WStype_t type,uint8_t* payload,size_t len){
 if(type==WStype_CONNECTED){online=true;logEvent("云端 WebSocket 已连接");JsonDocument d;status(d);d["v"]=1;d["type"]="hello";sendDoc(d);return;}
 if(type==WStype_DISCONNECTED){online=false;logEvent("云端已断开，自动重连");return;}
 if(type==WStype_ERROR){logEvent("云连接错误：检查地址、令牌、证书和时钟");return;}
 if(type!=WStype_TEXT){if(type==WStype_BIN||type==WStype_FRAGMENT_TEXT_START||type==WStype_FRAGMENT_BIN_START)ws.disconnect();return;}
 if(len>2048){ws.disconnect();return;}
 JsonDocument d;if(deserializeJson(d,payload,len)||d["v"]!=1||d["type"]!="tx")return;
 String id=d["id"]|"";if(!safeId(id))return;
 if(d["boot_id"]!=bootId){ack(id,false,"boot_changed");return;}
 if(!d["expires_at"].is<double>()){ack(id,false,"bad_expiry");return;}
 double left=d["expires_at"].as<double>()-double(time(nullptr));
 if(!isfinite(left)||left<=0||left>10){ack(id,false,"expired");return;}
 for(const String&s:seen)if(s==id){ack(id,false,"duplicate");return;}
 if(!(cfg["remote_write"]|false)){ack(id,false,"read_only");return;}
 if(lastTx&&uint32_t(millis()-lastTx)<100){ack(id,false,"rate_limited");return;}
 String data=d["data"]|"",enc=d["encoding"]|"";uint8_t out[514];size_t count=0;
 if(enc=="text"&&cfg["mode"]=="line"){
  if(!data.length()||!safeText(data,512)){ack(id,false,"bad_text");return;}
  memcpy(out,data.c_str(),data.length());count=data.length();
  if(cfg["ending"]=="crlf")out[count++]='\r';if(cfg["ending"]!="none")out[count++]='\n';
 }else if(enc=="hex"&&cfg["mode"]=="hex"){
  if(data.length()==0||data.length()>1024||data.length()%2){ack(id,false,"bad_hex");return;}
  for(size_t i=0;i<data.length();i+=2){if(!isxdigit(data[i])||!isxdigit(data[i+1])){ack(id,false,"bad_hex");return;}out[count++]=strtoul(data.substring(i,i+2).c_str(),nullptr,16);}
 }else{ack(id,false,"encoding_mismatch");return;}
 if(uart.availableForWrite()<int(count)){ack(id,false,"uart_busy");return;}
 seen[seenAt++%128]=id;lastTx=millis();size_t written=uart.write(out,count);txBytes+=written;
 ack(id,written==count,written==count?"uart_queued_not_executed":"partial_write_unknown");
 logEvent("TX "+String(written)+" bytes，等待项目自身反馈");
}
void emit(){
 if(!used)return;
 if(uint32_t(millis()-publishWindow)>=1000){publishWindow=millis();publishCount=0;}
 if(!online||publishCount>=20){drops++;used=0;return;}publishCount++;
 JsonDocument d;d["v"]=1;d["type"]="rx";d["device_id"]=cfg["device_id"];d["boot_id"]=bootId;
 d["encoding"]="hex"; // RX is always lossless hex, including invalid UTF-8.
 String s;s.reserve(used*2);const char*digits="0123456789abcdef";
 for(size_t i=0;i<used;i++){s+=digits[buf[i]>>4];s+=digits[buf[i]&15];}d["data"]=s;
 if(!sendDoc(d))drops++;used=0;
}
void readUART(){
 unsigned budget=1024;
 while(budget--&&uart.available()){
  uint8_t c=uart.read();rxBytes++;lastRx=millis();
  if(cfg["mode"]=="line"){
   if(c=='\n'){if(!discarding){if(used&&buf[used-1]=='\r')used--;emit();}used=0;discarding=false;}
   else if(!discarding){if(used<sizeof(buf))buf[used++]=c;else{discarding=true;used=0;drops++;}}
  }else{buf[used++]=c;if(used==256)emit();}
 }
 if(cfg["mode"]=="hex"&&used&&uint32_t(millis()-lastRx)>=uint32_t(cfg["idle_ms"]|20))emit();
}
void setup(){
 Serial.begin(115200);pinMode(0,INPUT_PULLUP);nv.begin("unigw",false);bootId=randomHex();defaults();
 String saved=nv.getString("config","");if(saved.length()){JsonDocument d;if(!deserializeJson(d,saved)&&validate(d,false).isEmpty())cfg.set(d);}
 apPassword=nv.getString("ap_pass","");if(apPassword.length()<12){apPassword=randomHex()+"Gw";nv.putString("ap_pass",apPassword);}
 apName="Gateway-Setup-"+String(uint32_t(ESP.getEfuseMac()),HEX);Serial.println("AP: "+apName+" password: "+apPassword);
 uart.setRxBufferSize(4096);uart.setTxBufferSize(1024);
 String fmt=cfg["format"]|"8N1";uint32_t format=fmt=="8E1"?SERIAL_8E1:fmt=="8O1"?SERIAL_8O1:fmt=="8N2"?SERIAL_8N2:SERIAL_8N1;
 uart.begin(cfg["baud"]|9600,format,cfg["rx"]|18,cfg["tx"]|17);
 WiFi.mode(WIFI_STA);WiFi.setAutoReconnect(false);
 String ssid=cfg["ssid"]|"";if(ssid.length()){WiFi.begin(ssid.c_str(),cfg["wifi_password"]|"");wifiStartAt=millis();}else startAP();
 configTime(0,0,cfg["ntp"]|"pool.ntp.org","time.cloudflare.com","ntp.aliyun.com");
 setupPortal();ws.onEvent(onWS);ws.setReconnectInterval(5000);ws.enableHeartbeat(15000,3000,2);logEvent((cfg["remote_write"]|false)?"通用网关启动，远程写入已开启":"通用网关启动，只读模式");
}
void loop(){
 readUART();http.handleClient();
 if(wifiBeginAt&&int32_t(millis()-wifiBeginAt)>=0){
  wifiBeginAt=0;ws.disconnect();started=false;online=false;WiFi.disconnect(false,false);WiFi.scanDelete();scanning=false;
  WiFi.begin(cfg["ssid"].as<const char*>(),cfg["wifi_password"].as<const char*>());wifiStartAt=lastRetry=millis();logEvent("正在连接已配置 Wi-Fi");
 }
 if(rebootAt&&int32_t(millis()-rebootAt)>=0)ESP.restart();
 if(digitalRead(0)==LOW){if(!hold)hold=millis();if(uint32_t(millis()-hold)>3000)startAP();}else hold=0;
 if(WiFi.status()!=WL_CONNECTED){if(millis()>45000)startAP();if(!ap&&!scanning&&String(cfg["ssid"]|"").length()&&millis()-lastRetry>30000){lastRetry=millis();WiFi.reconnect();}}
 bool ready=WiFi.status()==WL_CONNECTED&&time(nullptr)>1700000000&&String(cfg["host"]|"").length();
 if(ready&&!started){
  auth=String("Authorization: Bearer ")+String(cfg["token"]|"")+"\r\nX-Device-Id: "+String(cfg["device_id"]|"");
  ca=String(cfg["ca"]|"");if(ca.isEmpty())ca=ROOT_CA;
  if(cfg["tls"]|true)ws.beginSslWithCA(cfg["host"],cfg["port"]|443,cfg["path"],ca.c_str(),"");
  else ws.begin(cfg["host"].as<const char*>(),cfg["port"]|80,cfg["path"].as<const char*>(),"");
  ws.setExtraHeaders(auth.c_str());started=true;
 }
 if(!ready&&started){ws.disconnect();started=false;online=false;}
 if(started)ws.loop();
 if(online&&millis()-lastHeartbeat>=5000){lastHeartbeat=millis();JsonDocument d;status(d);d["v"]=1;d["type"]="status";sendDoc(d);}
 readUART();delay(1);
}
