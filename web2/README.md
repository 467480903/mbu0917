# G2 Web2

`web2` 是面向测试的纯前端 MQTT-over-WebSocket 控制台，不修改原 `web/` 目录。

## 结构

- `js/core/`：MQTT 传输、请求/反馈关联、topic 定义。
- `js/modules/`：与 `serivces2` 一一对应的 9 个功能模块。
- `js/ui/`：通用模块测试界面。
- `tests/*.html`：各功能模块的独立页面测试程序，默认模拟 MQTT。
- `server.js`：零依赖 Node 静态服务。

## 启动

```bash
cd /data/wxf/mbu0917/web2
npm run start
```

默认监听 `0.0.0.0:8003`，可以通过 `HOST` 和 `PORT` 环境变量调整。

- 主页：`http://10.42.1.101:8003/`
- 测试页：`http://10.42.1.101:8003/tests/`
- 主页模拟模式：`http://10.42.1.101:8003/?mock=1`

真实模式默认连接当前页面主机的 MQTT WebSocket `9001` 端口。所有运动命令在真实模式下会弹出人工确认。

## Playwright 可见测试示例

`playwright_examples/` 中包含与 9 个功能模块一一对应的测试脚本。详细运行方式见 `playwright_examples/README.md`。

- 使用 Playwright CLI skill，不依赖项目内安装 Playwright。
- 使用 `--headed` 打开可见浏览器。
- 每个操作前后打印步骤并暂停，保留浏览器供人工查看。
- 默认模拟 MQTT，不会控制真实机器人。
- 测试会校验成功状态、MQTT topic 和浏览器控制台错误。
