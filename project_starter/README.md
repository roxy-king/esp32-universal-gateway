# Link 项目开发模板 1.0

这是可运行的项目平台与单片机基础工程。它复用 ESP32 通用网关，提供账号、设备状态、控制回执、常用方案、GMT+8 预约、记录、离线提醒和可配置 API 的 AI 助手。

默认示例是 **CT107D 板载 LED**：开关、限时点亮、停止。它不包含尚未指定的育苗传感器或水泵驱动，也不自动把一句需求变成经过硬件验证的产品。

## 不接 ESP，先试用

安装 Python 3.11 或以上版本，Windows 双击 `start-demo.cmd`。第一次需联网安装依赖，然后浏览器打开 http://127.0.0.1:8880。

演示用户名 `demo`，密码 `demo1234`。该模式只监听本机，连接的是模拟网关和模拟单片机；临时数据在退出后删除，不能用于公网部署。按 Ctrl+C 停止。

也可以使用命令：

```text
python -m pip install -r requirements.txt
python tools/project.py demo
```

AI 功能需要在“设置 → AI 接口”填写自己的兼容 API Base URL、模型名和 Key。密钥只保存在服务端，不回传浏览器。演示模式的配置也会在退出时删除。

## 开始自己的项目

```text
python tools/project.py init D:/MyProjects/nursery --name 智能育苗箱 --id nursery
```

上述命令复制一个没有任何个人凭据的新工程，不覆盖已有目录。刚创建的工程仍是 LED 示例，仅更改项目名称/ID，不会虚构育苗功能。

新工程不复制预编译 HEX，避免误烧仍使用旧项目 ID 的固件；请在适配后重新编译。模板自带 HEX 仅对应默认的 bench 项目。

1. 填写新工程中的 [项目需求表](docs/项目需求表.md)，硬件和引脚不清楚时提供原理图/照片。
2. 把整个工程交给 AI，复制 [AI 开发提示词](docs/AI开发提示词.md)。
3. 由 AI 适配业务驱动、项目定义、页面，并运行检查、编译和测试。
4. 烧录单片机、部署项目网站，再按 [实机验收](docs/实机验收.md) 验证。

## 工程结构

| 路径 | 用途 |
| --- | --- |
| project.json | 数据字段、允许操作、参数边界和功能开关 |
| firmware/main.c | STC UART、解析/回执、重复命令防护、状态上报 |
| firmware/logic.c | 当前项目业务逻辑，示例为板载 LED |
| firmware/prebuilt/ | 已编译的 LED 示例 HEX，两种运行频率 |
| platform/gateway.py | 从通用网关 v1.6.0 复用的传输与鉴权层 |
| platform/app.py | 项目状态、执行链路、常用方案、预约、记录 |
| platform/assistant.py | 自定义 API、持久聊天、只提议不自动执行的 AI 控制 |
| platform/index.html | 可直接使用并按项目改造的中文网页 |
| tools/project.py | 创建项目、配置检查、初始化凭据、本机演示 |
| deploy/ | 独立服务安装及代码回退，不覆盖原网关服务 |
| tests/ | 协议、服务端、预约、AI 和真实 C 逻辑测试 |

## 编译与运行

配置与固件项目 ID 同步：

```text
python tools/project.py check --generate
powershell -ExecutionPolicy Bypass -File firmware/build.ps1 -KeilRoot D:/Keil_v5 -Clock 11059200
python -m unittest discover -s tests -v
```

Keil C51 需要用户合法安装，不随模板分发。`-Clock` 可为 11059200 或 12000000，必须与 STC-ISP 中选择的频率一致。编译输出在 firmware/output/。

真实部署前初始化账号与设备令牌：

```text
python tools/project.py configure --origin https://project.example.com --username admin
python platform/app.py --config private/server.json --data private/data --port 8767
```

默认监听127.0.0.1，由 HTTPS 反向代理提供公网入口。正式账号无默认密码，初始化时自己输入。详情见 [部署与回退](docs/部署与回退.md)。

## 兼容与边界

- 保持 IAP15F2K61S2、ESP32-S3 N16R8，不需要因新项目重刷 ESP。ESP 使用 Gateway v1、文本行、9600、8N1、CRLF、RX18/TX17。
- 项目单片机使用 P1 串口协议，与旧洗衣机的 `STATUS/MODE` 协议不同。旧洗衣机固件不会直接响应本模板，必须烧录本项目固件或编写明确的旧协议适配器。
- ESP 一次连接一个服务器。新项目服务可部署到同一台服务器的独立域名/端口，但切换 ESP 的服务器地址与令牌后，原服务不会同时接收这台 ESP 的数据。
- 基础项目定义支持最多16个整数字段、16个单整数参数操作，范围0–65535。小数可缩放、负值可偏移并标注单位；复杂多参数/二进制业务需 AI 同步扩展协议、解析和测试，不是只改标题。
- 同一平台实例对应一个项目定义，可连接多台同项目设备。不同项目使用独立实例、域名和数据目录。
- 预约采用 GMT+8，一次性执行，超过60秒宽限的任务标记错过；重启时已经派发的任务标记未知，不重放。离线时失败，避免恢复联网后突然动作。
- `succeeded` 仅在收到本项目、正确设备、匹配命令 ID 的单片机 OK 回执后出现。网关入队 ACK 不是执行成功；回执仍不等于独立传感器证明物理动作完成。
- AI 候选方案须在120秒内确认，确认时再次校验状态与参数。关闭页面后没有后台推送；离线提醒只在打开的网页中生效。
- 本模板不是视频、高速采集或硬实时控制方案，也不代替实际硬件的保护电路。
