import agibot_gdk
import time

# 初始化GDK系统
if agibot_gdk.gdk_init() != agibot_gdk.GDKRes.kSuccess:
    print("GDK初始化失败")
    exit(1)
print("GDK初始化成功")

pnc = agibot_gdk.Pnc()
time.sleep(2)  # 等待PNC初始化

# 创建导航目标
target = agibot_gdk.NaviReq()
target.target.position.x = -0.14157561800950003
target.target.position.y = 0.015152394013126735
target.target.position.z = 0.0040338473100211417
target.target.orientation.x = 0.01146358383671978
target.target.orientation.y = -0.01720065085681078
target.target.orientation.z = 0.83847410642918951
target.target.orientation.w = 0.54454926012574167

# 执行导航
try:
    pnc.normal_navi(target)
    print("正常导航请求发送成功")
except Exception as e:
    print(f"正常导航失败: {e}")

# 释放GDK系统资源
if agibot_gdk.gdk_release() != agibot_gdk.GDKRes.kSuccess:
    print("GDK释放失败")
else:
    print("GDK释放成功")