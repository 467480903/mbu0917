import agibot_gdk
import time
import math

# 控制参数
CONTROL_PERIOD = 0.01  # 控制周期（秒）
RATE_HZ = 100.0        # 发送频率（Hz）
DURATION = 5.0         # 控制持续时间（秒）

class ArmJointServoController:
    def __init__(self, robot):
        self.robot = robot

    def get_joint_position_by_name(self, joint_states, joint_name):
        """根据关节名称获取关节位置"""
        for state in joint_states['states']:
            if state['name'] == joint_name:
                return state['motor_position']
        raise RuntimeError(f"Joint name {joint_name} not found")

    def interpolate_position(self, start_pos, target_pos, t):
        """线性插值计算中间位置"""
        return start_pos + t * (target_pos - start_pos)

    def execute_arm_joint_servo_control(self, target_positions, control_group):
        """执行手臂关节位置伺服控制"""
        time.sleep(1.0)  # 等待1秒

        # 获取当前关节状态
        current_joint_states = self.robot.get_joint_states()

        # 获取起始位置
        arm_joint_names = [
            "idx21_arm_l_joint1", "idx22_arm_l_joint2", "idx23_arm_l_joint3",
            "idx24_arm_l_joint4", "idx25_arm_l_joint5", "idx26_arm_l_joint6",
            "idx27_arm_l_joint7",  # 左臂7个关节
            "idx61_arm_r_joint1", "idx62_arm_r_joint2", "idx63_arm_r_joint3",
            "idx64_arm_r_joint4", "idx65_arm_r_joint5", "idx66_arm_r_joint6",
            "idx67_arm_r_joint7"   # 右臂7个关节
        ]
        start_positions = []
        for joint_name in arm_joint_names:
            try:
                pos = self.get_joint_position_by_name(current_joint_states, joint_name)
                start_positions.append(pos)
                print(f"关节 {joint_name} 当前位置: {pos:.3f} 弧度")
            except RuntimeError as e:
                print(f"错误: {e}")
                return

        # 计算步数
        n_steps = int(DURATION * RATE_HZ)
        print(f"总步数: {n_steps}, 持续时间: {DURATION} 秒")

        # 执行轨迹
        dt = 1.0 / RATE_HZ
        start_time = time.time()

        for i in range(n_steps):
            t = float(i) / (n_steps - 1) if n_steps > 1 else 0.0

            # 计算当前目标位置（线性插值）
            current_positions = []
            for j in range(14):
                interp_pos = self.interpolate_position(
                    start_positions[j], target_positions[j], t
                )
                current_positions.append(interp_pos)

            try:
                # 使用普通模式（enable_low_latency=False，默认值）
                result = self.robot.move_arm_joint_servo(
                    current_positions, CONTROL_PERIOD, control_group
                )
                # 如需使用低延时模式，可传入 enable_low_latency=True：
                # result = self.robot.move_arm_joint_servo(
                #     current_positions, CONTROL_PERIOD, control_group, enable_low_latency=True
                # )
                if result != 0:
                    print(f"控制命令发送失败，步数: {i}")
                    return
            except Exception as e:
                print(f"控制命令发送异常，步数: {i}, 错误: {e}")
                return

            # 控制发送频率
            elapsed = time.time() - start_time
            expected_time = (i + 1) * dt
            sleep_time = expected_time - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

        print("手臂关节位置伺服控制完成")

        # 保持最终位置
        print("进入最终位置保持（Ctrl+C 结束）...")
        try:
            while True:
                try:
                    # 使用普通模式（enable_low_latency=False，默认值）
                    result = self.robot.move_arm_joint_servo(
                        target_positions, CONTROL_PERIOD, control_group
                    )
                    # 如需使用低延时模式，可传入 enable_low_latency=True：
                    # result = self.robot.move_arm_joint_servo(
                    #     target_positions, CONTROL_PERIOD, control_group, enable_low_latency=True
                    # )
                    if result != 0:
                        print("保持位置失败")
                        break
                except Exception as e:
                    print(f"保持位置异常: {e}")
                    break

                time.sleep(dt)
        except KeyboardInterrupt:
            print("\n已中断保持")


def main():
    # 初始化GDK系统
    if agibot_gdk.gdk_init() != agibot_gdk.GDKRes.kSuccess:
        print("GDK初始化失败")
        return

    print("GDK初始化成功")

    try:
        robot = agibot_gdk.Robot()
        time.sleep(2)  # 等待机器人初始化

        # 获取当前关节状态
        current_joint_states = robot.get_joint_states()

        # 定义目标位置（示例：手臂关节）
        target_positions = [
            0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,  # 左臂7个关节
            0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0   # 右臂7个关节
        ]

        print(f"\n目标角度:")
        arm_joint_names = [
            "idx21_arm_l_joint1", "idx22_arm_l_joint2", "idx23_arm_l_joint3",
            "idx24_arm_l_joint4", "idx25_arm_l_joint5", "idx26_arm_l_joint6",
            "idx27_arm_l_joint7",  # 左臂7个关节
            "idx61_arm_r_joint1", "idx62_arm_r_joint2", "idx63_arm_r_joint3",
            "idx64_arm_r_joint4", "idx65_arm_r_joint5", "idx66_arm_r_joint6",
            "idx67_arm_r_joint7"   # 右臂7个关节
        ]
        for i, joint_name in enumerate(arm_joint_names):
            print(f"  {joint_name}: {target_positions[i]:.3f} 弧度")

        # 执行手臂关节位置伺服控制
        controller = ArmJointServoController(robot)
        controller.execute_arm_joint_servo_control(target_positions, 2)

    except Exception as e:
        print(f"执行过程中发生错误: {e}")
    finally:
        # 释放GDK系统资源
        if agibot_gdk.gdk_release() != agibot_gdk.GDKRes.kSuccess:
            print("GDK释放失败")
        else:
            print("GDK释放成功")


if __name__ == "__main__":
    main()