# 第三方组件

发行包包含开发与烧录工具，许可证原文随相应组件保留：

| 组件 | 上游 | 许可证文件位置（完整发行包） |
|---|---|---|
| Arduino CLI | https://github.com/arduino/arduino-cli | tools/ARDUINO_CLI_LICENSE.txt |
| esptool | https://github.com/espressif/esptool | tools/ESPTOOL_LICENSE |
| ArduinoJson | https://github.com/bblanchon/ArduinoJson | tools/arduino-user/libraries/ArduinoJson/LICENSE.txt |
| arduinoWebSockets | https://github.com/Links2004/arduinoWebSockets | tools/arduino-user/libraries/WebSockets/LICENSE |
| libb64 | https://github.com/Links2004/arduinoWebSockets/tree/master/src/libb64 | WebSockets/src/libb64/LICENSE |

Arduino ESP32核心在首次构建时从官方源下载，未把完整核心工具链提交进仓库。预编译固件的依赖版本与构建参数见README及验证记录。
固件内ISRG Root X1为公开CA证书，不是私钥或设备认证令牌。
项目源代码公开可见不代表第三方组件许可证被替换；分发与修改各组件时应遵循相应许可证。
