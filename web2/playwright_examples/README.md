# Playwright 模块测试示例

这些脚本供安装了 Codex Playwright skill 的开发机运行。它们通过浏览器访问机器人上的 `web2`，不需要在机器人内安装 Playwright。

## 1. 启动后台服务

在机器人的第一个终端中：

```bash
cd /data/wxf/mbu0917/serivces2/
source ~/app/env.sh
python main.py
```

## 2. 启动 web2

在机器人的第二个终端中：

```bash
cd /data/wxf/mbu0917/web2
npm run start
```

## 3. 在 Codex 开发机运行可见测试

```bash
cd /data/wxf/mbu0917/web2/playwright_examples
bash test_base.sh
```

可用示例：

```bash
bash test_base.sh
bash test_joint.sh
bash test_pose.sh
bash test_end_effector.sh
bash test_tts.sh
bash test_camera.sh
bash test_apriltag.sh
bash test_database.sh
bash test_sync.sh
```

默认使用模拟 MQTT，测试结束后保留浏览器。默认每个步骤暂停 2 秒，便于观察。

```bash
PW_STEP_DELAY=5 bash test_tts.sh
PW_KEEP_OPEN=0 bash test_tts.sh
WEB2_HOST=10.42.1.101 WEB2_PORT=8003 bash test_camera.sh
```

## 真实 MQTT 联调

只允许将非运动示例切换到真实 MQTT：

```bash
PLAYWRIGHT_LIVE=1 bash test_tts.sh
PLAYWRIGHT_LIVE=1 bash test_camera.sh
PLAYWRIGHT_LIVE=1 bash test_database.sh
PLAYWRIGHT_LIVE=1 bash test_sync.sh
```

底盘、关节、位姿和夹爪示例在脚本层面禁止自动真机联调。需要真机测试时，请在可见页面中人工核对参数并确认环境安全。
