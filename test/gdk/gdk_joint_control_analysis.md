# GDK关节运动控制分析报告

## 关键发现

### 1. 关节控制方式

GDK提供了两种主要的关节控制方式：

#### 方式一：`joint_control_request()` - 单次命令执行

**特点：**
- 一次发送一组关节目标位置
- 需要等待运动完成
- 多次调用会有停顿

**示例：**
```python
joint_control_request = agibot_gdk.JointControlReq()
joint_control_request.life_time = 1.0
joint_control_request.joint_names = ["idx01_body_joint1", "idx02_body_joint2"]
joint_control_request.joint_positions = [0.5, -0.3]
joint_control_request.joint_velocities = [0.3, 0.3]
robot.joint_control_request(joint_control_request)
```

#### 方式二：`move_arm_joint_servo()` - 伺服模式连续控制

**特点：**
- 以高频率（如200Hz）持续发送目标位置
- **支持连续轨迹执行，中间无停顿**
- 需要在循环中持续调用

**示例（来自servo_control.py）：**
```python
# 以200Hz频率持续发送位置命令
t = 0.0
dt = 0.01  # 10ms = 100Hz
freq = 0.5
omega = 2*math.pi*freq
amp = 0.087
phases = [i*0.2 for i in range(14)]

while True:
    # 计算当前时刻的目标位置
    arm_positions = [base[i] + amp * math.sin(omega*t + phases[i]) for i in range(14)]
    # 发送伺服命令
    robot.move_arm_joint_servo(arm_positions, 0.01, 2, False)
    t += dt
    time.sleep(dt)
```

### 2. 多关节组连续执行的实现方案

根据GDK代码分析，有以下几种方案：

#### 方案A：使用JSON动作序列 + `joint_control_request`

**优点：**
- 简单易用
- 支持记录和回放

**缺点：**
- **会有停顿**，因为每次调用需要等待响应

**示例（来自mc_example.py和MotionControlReplay.py）：**
```python
# 从JSON文件读取动作序列
with open('action.json', 'r') as f:
    data = json.load(f)
    recorded_commands = data.get('recorded_commands', [])

# 逐个执行动作帧
for cmd in recorded_commands:
    joint_names = cmd['joint_names']
    joint_positions = cmd['joint_positions']
    
    # 发送单帧命令
    joint_control_request = agibot_gdk.JointControlReq()
    joint_control_request.life_time = 1.0
    joint_control_request.joint_names = joint_names
    joint_control_request.joint_positions = joint_positions
    joint_control_request.joint_velocities = [0.3] * len(joint_names)
    robot.joint_control_request(joint_control_request)
    
    # 这里会有停顿，因为需要等待运动完成
    time.sleep(1.0)
```

#### 方案B：使用伺服模式 `move_arm_joint_servo` ✅ **推荐**

**优点：**
- **连续执行，无停顿**
- 高频率控制（100-200Hz）
- 轨迹平滑

**实现要点：**
1. 以固定频率（如100Hz）持续发送目标位置
2. 每次发送当前时刻所有关节的目标位置
3. 机器人会平滑插值运动到目标位置

**代码实现：**
```python
import agibot_gdk
import time
import math

# 初始化
agibot_gdk.gdk_init()
robot = agibot_gdk.Robot()
time.sleep(1)

# 定义关节列表
joint_names = [
    "idx21_arm_l_joint1", "idx22_arm_l_joint2", "idx23_arm_l_joint3",
    "idx24_arm_l_joint4", "idx25_arm_l_joint5", "idx26_arm_l_joint6",
    "idx27_arm_l_joint7",
    "idx61_arm_r_joint1", "idx62_arm_r_joint2", "idx63_arm_r_joint3",
    "idx64_arm_r_joint4", "idx65_arm_r_joint5", "idx66_arm_r_joint6",
    "idx67_arm_r_joint7"
]

# 定义多个目标位置序列
trajectory = [
    [0.0] * 14,           # 位置1
    [0.5, -0.3, ...],     # 位置2
    [-0.2, 0.4, ...],     # 位置3
    # ... 更多位置
]

# 以伺服模式连续执行
dt = 0.01  # 10ms周期 = 100Hz
for target_positions in trajectory:
    # 发送当前目标位置
    robot.move_arm_joint_servo(target_positions, dt, 2, False)
    time.sleep(dt)
```

#### 方案C：使用回放服务 `ReplayRequest`

**优点：**
- 底层优化，性能好
- 支持速度调节

**示例：**
```python
from mc_msgs_pb.mc_service_pb2 import ReplayRequest

request = ReplayRequest()
request.record_file_name = "action_recording.bin"
request.uuid = str(uuid.uuid4())
replay_publisher.publish(request)
```

### 3. 最佳实践建议

#### 实现连续无停顿运动的关键：

1. **使用伺服模式** `move_arm_joint_servo()`
   - 以100-200Hz频率持续发送位置
   - 每次发送包含所有关节的目标位置
   - 机器人会平滑插值运动

2. **预计算轨迹**
   - 将多个关节组的目标位置预先计算好
   - 按时间顺序存储为轨迹点序列

3. **插值平滑**
   - 在两个目标点之间使用正弦或多项式插值
   - 避免突变导致机器人抖动

### 4. 完整示例：多关节组连续运动

```python
#!/usr/bin/env python3
"""
多关节组连续运动示例（无停顿）
使用伺服模式实现平滑连续的关节运动
"""

import agibot_gdk
import time
import math
import numpy as np

def execute_continuous_motion(robot, joint_groups, duration_per_group=2.0):
    """
    连续执行多个关节组的运动，中间无停顿
    
    参数:
        robot: GDK Robot对象
        joint_groups: 关节组列表，每个元素是字典:
            {
                'names': [关节名称列表],
                'positions': [目标位置列表]
            }
        duration_per_group: 每组的运动时长（秒）
    """
    # 获取当前关节状态
    joint_states = robot.get_joint_states()
    current_positions = {s['name']: s['motor_position'] for s in joint_states['states']}
    
    # 控制参数
    dt = 0.01  # 10ms = 100Hz
    steps_per_group = int(duration_per_group / dt)
    
    print(f"开始连续运动，共{len(joint_groups)}组，每组{duration_per_group}秒")
    
    for group_idx, group in enumerate(joint_groups):
        print(f"\n执行第{group_idx + 1}组关节运动...")
        
        joint_names = group['names']
        target_positions = group['positions']
        
        # 获取起始位置
        start_positions = [current_positions[name] for name in joint_names]
        
        # 插值生成轨迹点
        for step in range(steps_per_group):
            # 使用正弦插值实现平滑运动
            progress = step / steps_per_group
            smooth_progress = 0.5 * (1 - math.cos(math.pi * progress))
            
            # 计算当前时刻的位置
            current_target = [
                start + (target - start) * smooth_progress
                for start, target in zip(start_positions, target_positions)
            ]
            
            # 发送伺服命令（仅针对手臂关节）
            arm_positions = current_target[:14] if len(current_target) >= 14 else current_target
            robot.move_arm_joint_servo(arm_positions, dt, 2, False)
            
            time.sleep(dt)
        
        # 更新当前位置
        for name, pos in zip(joint_names, target_positions):
            current_positions[name] = pos
    
    print("\n✓ 连续运动完成")

# 使用示例
if __name__ == "__main__":
    # 初始化
    if agibot_gdk.gdk_init() != agibot_gdk.GDKRes.kSuccess:
        print("GDK初始化失败")
        exit(1)
    
    robot = agibot_gdk.Robot()
    time.sleep(2)
    
    # 定义多个关节组
    joint_groups = [
        {
            'names': ['idx21_arm_l_joint1', 'idx22_arm_l_joint2', ...],
            'positions': [0.5, -0.3, ...]
        },
        {
            'names': ['idx21_arm_l_joint1', 'idx22_arm_l_joint2', ...],
            'positions': [-0.2, 0.4, ...]
        },
        # 更多组...
    ]
    
    # 执行连续运动
    execute_continuous_motion(robot, joint_groups, duration_per_group=2.0)
    
    # 释放资源
    agibot_gdk.gdk_release()
```

### 5. 总结

**GDK支持多关节组连续无停顿运动的方式：**

✅ **支持**：使用 `move_arm_joint_servo()` 伺服模式
- 以高频率（100-200Hz）持续发送目标位置
- 每次发送包含所有关节的目标位置数组
- 机器人会平滑插值运动，中间无停顿

❌ **不支持**：使用 `joint_control_request()` 多次调用
- 每次调用需要等待运动完成
- 会有明显的停顿

**建议：**
- 对于连续轨迹运动，使用伺服模式 `move_arm_joint_servo()`
- 对于点对点运动，使用 `joint_control_request()`
- 预先计算好轨迹，以固定频率发送位置命令

---

**文件位置：**
- 示例代码：`/home/agi/app/gdk/examples/python/servo_control.py`
- 动作序列：`/home/agi/app/gdk/examples/python/saved_commands/`
- 回放工具：`/home/agi/app/gdk/aim_master/resources_scripts/utils/MotionControlReplay.py`
