# Link / ESP32 通用通信网关 1.3
现成固件仅针对 **ESP32-S3 N16R8（16MB Flash）**。

## 一键部署与自动配对

以 **root** 登录Debian/Ubuntu服务器，复制整行：

```bash
bash -c 'f=$(mktemp) && curl -fsSL https://raw.githubusercontent.com/roxy-king/esp32-universal-gateway/v1.3.0/install.sh -o "$f" && bash "$f"; r=$?; test -z "$f" || rm -f -- "$f"; exit "$r"'
```

若提示curl不存在，先运行 `apt-get update && apt-get install -y curl ca-certificates`。
向导会下载固定v1.3.0源码，安装服务、配置HTTPS并生成ESP配对文件。请先完成独立域名DNS解析，并开放80/443端口。
完成后把 `/etc/esp-gateway/pairing.json` 下载到电脑的 `private/pairing.json`，连接ESP热点并运行 `connect.cmd`；服务器不能替你连接本地设备热点。

也可以从仓库的 **Releases** 下载完整包，使用Windows向导：
双击 **setup.cmd**：SSH上传服务端 → 安装服务与HTTPS → 下载配对凭据 → 连接ESP热点 → 自动写入服务器与Wi-Fi配置。
已部署服务器、只需重新配对时运行 **connect.cmd**。首次域名解析、SSH登录和连接热点仍需按提示操作。
详细步骤：[一键部署与配对](docs/一键部署与配对.md)。

## 已提供

- 脱离电脑的 UART ↔ Wi-Fi ↔ WebSocket/WSS 通信。
- 设备热点内的中文设置面板：项目名、设备ID、Wi-Fi、服务器主机/端口/路径、认证令牌、TLS与CA、NTP、波特率、GPIO、校验位、分包方式与控制权限。
- 文本行和任意二进制字节（HEX封装）；默认9600、8N1、RX18/TX17。
- Wi-Fi重连、云端重连、心跳、开机会话ID、过期命令拒绝、重复命令拒绝、默认只读。
- 状态诊断、事件记录、脱敏配置导出/导入、重启、恢复项目配置。
- 独立服务端：账号登录、多设备注册、远程发送、串口记录、浏览器常用命令。
- 预编译固件、烧录工具、源码、测试与部署模板。

## 先看这一点

通用指“传输不再绑定洗衣逻辑”，不是“不写单片机程序就能控制任意设备”。新项目必须定义可执行命令与状态反馈。旧洗衣机网站的协议不同，本固件不能直接连接原网站。当前服务器未被修改，也未给你的ESP32自动烧录。

## 第一步：烧录ESP32

1. 整个目录解压到短路径，例如 `D:\ESP32Gateway`。
2. 拔开与单片机之间的信号线也可独立配置；用USB数据线连接ESP32，关闭旧串口监视器。
3. 双击 `flash.cmd`，填写实际COM端口，输入 `FLASH` 确认。此操作会覆盖ESP固件，合并镜像也可能清除此前保存的设置；先记录旧配置。
4. 烧录后点按ESP32的RST；如果连接超时，按住BOOT、点按RST、松开BOOT，再重新烧录。
5. 用串口工具打开USB COM，**115200**。点按RST，读取 `AP: Gateway-Setup-... password: ...`。
   也可先 `py -m pip install pyserial`，再 `py serial_monitor.py COM5`。
6. 手机连接输出的热点。密码为每台设备首次生成的随机密码，不是原来的WasherSetup密码。访问 `http://192.168.4.1`。

普通用户用现成BIN即可，不需要安装Arduino工具链。

## 第二步：先准备独立服务器配置

本机试验（Python 3.11及以上）：
```powershell
cd D:\ESP32Gateway
py -m venv .venv
.\.venv\Scripts\python -m pip install -r server\requirements.txt
.\.venv\Scripts\python server\configure.py
```
按提示输入网页完整地址，例如 `http://127.0.0.1:8766`（仅电脑浏览器试验），或者 `https://gateway.你的域名`（公网）。设备ID填ESP面板显示的值。程序生成：

- `server/private/server.json`：账号哈希和设备令牌哈希。
- `server/private/device-token.txt`：填入ESP面板的设备令牌，仅本地保存。

启动：
```powershell
.\.venv\Scripts\python server\server.py --config server\private\server.json
```
默认只监听127.0.0.1。ESP接入局域网测试时，运行参数增加 `--host 0.0.0.0`，网页地址在生成配置时改为 `http://电脑局域网IP:8766`，放行Windows专用网络的8766入站。ESP填写电脑局域网IP、8766、`/gateway/ws`，临时关闭TLS。**这仅用于可信局域网测试，不向公网暴露明文端口。**

局域网模式也需要校时才能验证命令有效期：允许网关访问NTP（通常UDP123），或在面板填写局域网内可用的NTP服务器。

公网长期运行请按 [服务器部署](docs/服务器部署.md) 配置独立域名与HTTPS。

## 第三步：填写ESP面板

1. 项目名自定；设备ID必须与server.json注册的一致。
2. 填2.4GHz Wi-Fi名称和密码。密码留空代表保留；换成开放Wi-Fi需勾选清除密码。
3. 主机只填域名/IP，不含 `https://`；公网端口443、路径 `/gateway/ws`，打开TLS。
4. 设备令牌填生成的device-token.txt内容。以后留空保留。不要填网页登录密码。
5. 公网证书链若由ISRG Root X1信任，CA留空即可；其他CA粘贴对应PEM根证书。始终验证证书，不提供“忽略证书错误”。
6. 根据单片机设置串口。先保持“允许远程发送串口命令”关闭，验证数据接收后再开启。
7. 保存并重启。正常Wi-Fi连接后热点不自动开启；**开机完成后长按BOOT 3秒**可重新开热点，不清空项目配置。
8. Wi-Fi未连上超过45秒会自动开热点。云端未连接但Wi-Fi正常时，用BOOT手动开热点查看诊断。

热点开启期间管理HTTP只接受经热点接口进入的连接，不向家庭局域网开放管理页面。热点没有自动关闭计时，配置结束可重启关闭（Wi-Fi配置成功时）。

## 第四步：接单片机

| ESP32 | 电平转换器低压侧 | 高压侧 / 单片机 |
|---|---|---|
| GPIO18（RX） | LV1 | HV1 → 单片机TX |
| GPIO17（TX） | LV2 | HV2 → 单片机RX |
| 3V3 | LV | 不接5V |
| GND | GND | 单片机GND |
| — | — | HV → 单片机5V参考电源 |

两块板分别正常供电。3.3V MCU可用兼容3.3V TTL连接；5V单片机不能直接输出到ESP引脚。
原CT107D兼容固件：P37为TX、P36为RX，按住S4再上电进入ESP串口模式。新育苗固件的引脚以它自身实现为准。

## 第五步：验证远程链路

1. 打开服务器网页登录。未接单片机时，网关也可以显示云端在线；这不表示单片机在线。
2. 让单片机每秒发送 `TEMP,25.5\r\n`，网页应出现RX记录。
3. 在热点面板开启远程写入，保存重启。网页发送单片机确实支持的命令。
4. 观察“已进入串口发送队列”后单片机自己的反馈。不要把网关ACK当成业务执行成功。
5. 换手机移动数据再次登录，检查真正的公网远程链路。
6. 断开Wi-Fi、恢复Wi-Fi、重启ESP，检查自动恢复；断线期间旧指令不会缓存补发。

如果暂无单片机，可断开其所有信号线后，把ESP GPIO17与GPIO18短接做3.3V UART回环，文本模式发送 `PING`，应接收相同内容。完成后移除短接。不要在仍连接单片机TX时短接，以免两个输出端相互驱动。

## 更换项目与常用操作

- 换服务器：BOOT开热点 → 改主机/端口/路径/令牌/CA → 保存重启。不必重新编译。
- 换项目：改单片机程序及命令，调整串口参数；服务端可直接作为原始命令控制台，也可进一步做育苗图表。
- 导出配置不包含Wi-Fi密码和令牌；导入只填表单，不立即保存。
- 恢复出厂清除项目配置，保留本机热点密码；忘记热点密码可USB串口115200查看，不必清空设备。
- 服务端支持多设备，每台设备独立ID与令牌；详见部署文档。
- 本版未提供OTA、MQTT、RS485自动方向控制。当前固件是明确限定硬件的UART/WSS网关，不承诺所有ESP型号通用。

## 自行编译与修改

```powershell
py embed_portal.py
powershell -ExecutionPolicy Bypass -File build.ps1 -InstallDependencies
```
首次需要联网下载ESP32 Arduino Core 3.3.2。随包库：WebSockets2.6.1、ArduinoJson7.4.2。构建固定16MB Flash、40MHz、PSRAM关闭、CDC关闭，并应用NETWORK_EVENTS_MUTEX ABI标志。
修改 `portal.html` 后必须运行嵌入脚本，再编译。固件里没有个人域名、固定令牌或项目密码。

## 工程入口

- 固件：`firmware/UniversalGateway/UniversalGateway.ino`
- 可烧录合并镜像：`firmware_release/UniversalGateway.ino.merged.bin`，地址0x0
- 设备面板：`portal.html`
- 云端：`server/server.py`、`server/index.html`
- [协议说明](docs/协议与适配.md)、[服务器部署](docs/服务器部署.md)、[技术参考](docs/技术参考.md)
- 验证结果：`docs/验证记录.txt`。本次为编译、自动化集成及浏览器检查，不代替实物验收。

## 修改控制台账号密码

安装时密码最低8位。登录控制台后展开页面底部的“账号设置”，填写用户名、当前密码和两次新密码即可保存；保存后需重新登录，所有旧会话失效。设备ID、设备令牌与ESP配置不变，不需要重刷ESP。

已用本向导安装的服务器，重新运行上面的v1.3.0命令即可更新，保留原账号、令牌与配对文件。首次升级不强迫你修改旧密码；可以登录后再改成8位或更长。
账号修改保存于 `/var/lib/esp-gateway/account.json`，通过systemd StateDirectory限定写入目录。该文件优先于初始server.json内的账号设置，备份时也需包含它。手动启动时默认保存在server.json同目录，也可以传 `--account-file` 指定可写路径。
