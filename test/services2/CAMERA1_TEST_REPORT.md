# CAMERA1 验证记录 — 2026-11-05

目标机器：10.20.17.172，项目 `/data/wxf/mbu0917`。
验证页面：`http://10.20.17.172:8002/index.html`。
全程未发送机器人运动指令；经用户确认无运动任务后校正系统时间，解决 HTTPS 证书时间错误。未关闭 TLS 校验。

## 已验证

- Python 编译、三个前端 JS 语法检查及 run.sh shell 语法检查通过。
- `test_camera1_units.py` 四项通过：单路开关隔离、仅发布/保存指定相机、保活到期停止、LLM 输出与路径检查。
- `test_camera1_mqtt.py` 真实 localhost MQTT status/capture 成功，拍摄回包含图像。
- Playwright CLI 操作真实网页：头部 RGB 开启、拍照和停止；左手腕开启并连拍；停止头部后左手腕继续工作；深度及右手腕单帧拍照成功。
- Playwright 验证切换到“程序”菜单时，右上实时画面与右下识别结果均保留；未点击程序运行。
- 真实头部照片 Apriltag 请求成功回包，当前现场画面返回 0 个码（不表示验证了正样本识别精度）。
- 真实头部照片经独立 LLM 服务返回 JSON 及带标线图片，页面显示完成；输出 `image/llm/line-760e8786d9aa42928e9d5f73a5beb6af.jpg`。
- 四路最终均为停止状态、连拍关闭、图片可解码显示。测试产生照片保留在 `images/`，未删除用户数据。
- `cg-humanoid.service` 为 enabled，其 ExecStart 指向修改后的 `service2/run.sh start`，启动列表已包含 llm_server；本次未重启整机。
- `.venv-llm`、密钥文件被 Git 忽略；密钥权限为 600。

## 测试发现及处理

原始大图连续发布曾导致 WebSocket 发送队列积压约 2.7 MB，页面控制回包延迟并超时。
已将连续预览缩小为最长边 640 像素、最高 2 Hz，照片与识别原图分辨率不变。
复测实时显示、控制回包、Apriltag 与 LLM 流程通过，观察到 WebSocket 队列回到约 475 字节。
服务启动先后造成的初始状态超时，通过周期读取状态恢复。

## 未通过的精度项

附图围栏测试已完成两次真实模型调用，均能生成 JSON 和图片，但横杆端点定位有明显偏差。
输出分别为：

- `image/llm/line-7316667ca33b485ca3deba1f8f79690c.jpg`
- `image/llm/line-0f566b7cab2749e68f881f72e0ee9bf8.jpg`

因此，只确认 API、MQTT、页面与绘图流程可用，**不宣称围栏几何定位精度达标**。
模型自报置信度不作为精度保证；LLM 结果没有接入任何机器人运动控制。
若后续需要可靠斜率，应增加专门线段检测和几何校验。

## 测试文件

- `test_llm_fence.py`：独立调用 LLM 识别用户附图，可用 `--image` 指定项目 image/images 下的另一张图片。
- `test_camera1_mqtt.py`：真实 MQTT 单路相机请求，默认仅拍照；可选 `--camera`、`--cmd`。
- `test_camera1_units.py`：不依赖 GDK、不联网的单元检查。

源码改动前备份目录：`/data/wxf/mbu0917/.camera1-backup-4Dnmp0`。
