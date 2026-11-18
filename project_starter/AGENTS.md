# 项目开发约定

先读 README.md、docs/项目需求表.md、docs/通信协议.md，再修改项目。

- 项目定义以 project.json 为准。名称、字段、参数范围必须在固件、服务端、网页和 AI 上一致。
- platform/gateway.py 是 Gateway v1 传输层。新业务不修改 ESP 固件，不绕过登录、CSRF、令牌或命令过期检查。
- 业务适配主要修改 firmware/logic.c、firmware/main.c 的状态字段和外设初始化、project.json、platform/index.html 的项目专用布局。
- 不能假设传感器型号、接线、电平或动作安全范围。缺失的硬件信息必须标记待确认；不能以模拟读数冒充真实采集。
- 单片机只有完成/接受已定义动作后才回 OK，拒绝回 ERR。持续动作的 OK 代表启动已应用，不代表动作周期已完成，最终状态由 telemetry 表达。
- 断网保护、执行器时长限制、上电安全状态放在单片机。修改定时器时核对 UART Timer2，避免抢占同一资源。
- 所有控制入口（网页、预约、AI）共用 check_action/execute。AI只生成候选方案，用户确认后才可发送。
- 新增操作须有参数范围、确认要求、可否预约、可否AI调用。不要插入可以任意执行 shell、Python 或直接拼接串口命令的表达式。
- 运行 python tools/project.py check --generate，编译固件，再运行 python -m unittest discover -s tests -v。页面变更要检查桌面/手机和真实功能路径。
- 报告必须分清模拟测试、编译验证、实机验证和实际第三方AI调用。没有完成的不能写成通过。
- private/、.venv/、API密钥、SSH凭据、设备令牌、用户数据不得加入发布包或Git。
- 不覆盖原项目、不自动烧录当前连接的开发板。新固件烧录和生产迁移须在用户授权的目标上执行。
