import agibot_gdk
import time
import math


# 常量定义
LEFT_NAME = "arm_l_end_link"
RIGHT_NAME = "arm_r_end_link"

# 目标位姿（位置和四元数）
TARGET_LEFT_POSITION = [0.626755,0.301127306,1.08398]
TARGET_LEFT_ORIENTATION =  [0.5858436, -0.02614889,0.80973243,0.02089957]

TARGET_RIGHT_POSITION = [0.6099763,-0.3903393, 1.050190472]
TARGET_RIGHT_ORIENTATION =  [0.648815,-0.001096,0.76094223696, 0.0020416]

# 控制参数
MAX_STEP_CM = 0.1  # 最大步长（厘米）
LIFETIME = 0.02    # 生命周期（秒）
RATE_HZ = 50.0     # 发送频率（Hz）
HOLD_FINAL = True  # 是否保持最终位姿


class EndEffectorController:
    def __init__(self, robot):
        self.robot = robot

    def slerp(self, q0, q1, t):
        """
        四元数球面线性插值
        q0, q1: 四元数 [x, y, z, w]
        t: 插值参数 [0, 1]
        返回: 插值后的四元数 [x, y, z, w]
        """
        # 计算点积
        dot = q0[0]*q1[0] + q0[1]*q1[1] + q0[2]*q1[2] + q0[3]*q1[3]

        # 如果点积为负，取反q1以确保最短路径
        if dot < 0.0:
            dot = -dot
            q1_neg = [-q1[0], -q1[1], -q1[2], -q1[3]]
            result = [q0[i] + t * (q1_neg[i] - q0[i]) for i in range(4)]
        else:
            result = [q0[i] + t * (q1[i] - q0[i]) for i in range(4)]

        # 限制点积范围
        dot = max(-1.0, min(1.0, dot))

        if dot > 0.9995:
            # 线性插值
            norm = math.sqrt(sum(r*r for r in result))
            if norm > 0.0:
                result = [r / norm for r in result]
        else:
            # 球面线性插值
            theta_0 = math.acos(dot)
            sin_theta_0 = math.sin(theta_0)
            theta = theta_0 * t
            sin_theta = math.sin(theta)
            s0 = math.cos(theta) - dot * sin_theta / sin_theta_0
            s1 = sin_theta / sin_theta_0

            result = [s0 * q0[i] + s1 * q1[i] for i in range(4)]

        return result

    def distance_between_points(self, p1, p2):
        """计算两点之间的距离"""
        dx = p2[0] - p1[0]
        dy = p2[1] - p1[1]
        dz = p2[2] - p1[2]
        return math.sqrt(dx*dx + dy*dy + dz*dz)

    def calculate_n_steps(self, start_pos, goal_pos, max_step_cm):
        """计算需要的步数"""
        dist_cm = self.distance_between_points(start_pos, goal_pos) * 100.0
        return max(int(math.ceil(dist_cm / max_step_cm)), 1)

    def plan_trajectory(self, start_pose, goal_pose, n_steps):
        """
        规划轨迹
        start_pose, goal_pose: 包含position和orientation的字典
        n_steps: 步数
        返回: 轨迹列表
        """
        trajectory = []

        for i in range(n_steps):
            t = float(i) / (n_steps - 1) if n_steps > 1 else 0.0

            # 位置线性插值
            pos = [
                start_pose['position'][0] + t * (goal_pose['position'][0] - start_pose['position'][0]),
                start_pose['position'][1] + t * (goal_pose['position'][1] - start_pose['position'][1]),
                start_pose['position'][2] + t * (goal_pose['position'][2] - start_pose['position'][2])
            ]

            # 四元数SLERP插值
            q0 = start_pose['orientation']
            q1 = goal_pose['orientation']
            quat = self.slerp(q0, q1, t)

            trajectory.append({
                'position': pos,
                'orientation': quat
            })

        return trajectory

    def find_pose_by_name(self, status, target_name):
        """根据名称查找位姿"""
        for i, frame_name in enumerate(status.frame_names):
            if frame_name == target_name:
                pose = status.frame_poses[i]
                # 提取位置和四元数
                position = [pose.position.x, pose.position.y, pose.position.z]
                orientation = [pose.orientation.x, pose.orientation.y,
                              pose.orientation.z, pose.orientation.w]
                return {'position': position, 'orientation': orientation}
        raise RuntimeError(f"Frame name {target_name} not found")

    def execute_end_pose_control(self):
        """执行末端位姿控制"""
        time.sleep(1.0)  # 等待1秒

        # 获取当前状态
        status = self.robot.get_motion_control_status()

        # 获取起始位姿
        start_left_pose = self.find_pose_by_name(status, LEFT_NAME)
        start_right_pose = self.find_pose_by_name(status, RIGHT_NAME)

        # 目标位姿
        goal_left_pose = {
            'position': TARGET_LEFT_POSITION,
            'orientation': TARGET_LEFT_ORIENTATION
        }
        goal_right_pose = {
            'position': TARGET_RIGHT_POSITION,
            'orientation': TARGET_RIGHT_ORIENTATION
        }

        # 计算步数
        n_left = self.calculate_n_steps(start_left_pose['position'],
                                        goal_left_pose['position'],
                                        MAX_STEP_CM)
        n_right = self.calculate_n_steps(start_right_pose['position'],
                                        goal_right_pose['position'],
                                        MAX_STEP_CM)
        n_steps = max(n_left, n_right)

        print(f"左臂步数: {n_left}, 右臂步数: {n_right}, 总步数: {n_steps}")
        # 规划轨迹
        traj_left = self.plan_trajectory(start_left_pose, goal_left_pose, n_steps)
        traj_right = self.plan_trajectory(start_right_pose, goal_right_pose, n_steps)

        # 执行轨迹
        dt = 1.0 / RATE_HZ
        for i in range(n_steps):
            # 创建末端执行器位姿控制请求
            end_pose = agibot_gdk.EndEffectorPose()
            end_pose.life_time = LIFETIME
            end_pose.group = agibot_gdk.EndEffectorControlGroup.kBothArms

            # 设置左臂位姿
            end_pose.left_end_effector_pose.position.x = traj_left[i]['position'][0]
            end_pose.left_end_effector_pose.position.y = traj_left[i]['position'][1]
            end_pose.left_end_effector_pose.position.z = traj_left[i]['position'][2]
            end_pose.left_end_effector_pose.orientation.x = traj_left[i]['orientation'][0]
            end_pose.left_end_effector_pose.orientation.y = traj_left[i]['orientation'][1]
            end_pose.left_end_effector_pose.orientation.z = traj_left[i]['orientation'][2]
            end_pose.left_end_effector_pose.orientation.w = traj_left[i]['orientation'][3]

            # 设置右臂位姿
            end_pose.right_end_effector_pose.position.x = traj_right[i]['position'][0]
            end_pose.right_end_effector_pose.position.y = traj_right[i]['position'][1]
            end_pose.right_end_effector_pose.position.z = traj_right[i]['position'][2]
            end_pose.right_end_effector_pose.orientation.x = traj_right[i]['orientation'][0]
            end_pose.right_end_effector_pose.orientation.y = traj_right[i]['orientation'][1]
            end_pose.right_end_effector_pose.orientation.z = traj_right[i]['orientation'][2]
            end_pose.right_end_effector_pose.orientation.w = traj_right[i]['orientation'][3]

            try:
                result = self.robot.end_effector_pose_control(end_pose)
                if result != 0:
                    print(f"控制命令发送失败，步数: {i}")
                    return
                print(f"控制命令发送成功，步数: {i}")
            except Exception as e:
                print(f"控制命令发送异常，步数: {i}, 错误: {e}")
                return

            time.sleep(dt)

        # 保持最终位姿
        if HOLD_FINAL:
            print("进入末端位姿保持（Ctrl+C 结束）...")
            try:
                final_left = traj_left[-1]
                final_right = traj_right[-1]

                while True:
                    end_pose = agibot_gdk.EndEffectorPose()
                    end_pose.life_time = LIFETIME
                    end_pose.group = agibot_gdk.EndEffectorControlGroup.kBothArms

                    # 设置左臂位姿
                    end_pose.left_end_effector_pose.position.x = final_left['position'][0]
                    end_pose.left_end_effector_pose.position.y = final_left['position'][1]
                    end_pose.left_end_effector_pose.position.z = final_left['position'][2]
                    end_pose.left_end_effector_pose.orientation.x = final_left['orientation'][0]
                    end_pose.left_end_effector_pose.orientation.y = final_left['orientation'][1]
                    end_pose.left_end_effector_pose.orientation.z = final_left['orientation'][2]
                    end_pose.left_end_effector_pose.orientation.w = final_left['orientation'][3]

                    # 设置右臂位姿
                    end_pose.right_end_effector_pose.position.x = final_right['position'][0]
                    end_pose.right_end_effector_pose.position.y = final_right['position'][1]
                    end_pose.right_end_effector_pose.position.z = final_right['position'][2]
                    end_pose.right_end_effector_pose.orientation.x = final_right['orientation'][0]
                    end_pose.right_end_effector_pose.orientation.y = final_right['orientation'][1]
                    end_pose.right_end_effector_pose.orientation.z = final_right['orientation'][2]
                    end_pose.right_end_effector_pose.orientation.w = final_right['orientation'][3]

                    try:
                        result = self.robot.end_effector_pose_control(end_pose)
                        if result != 0:
                            print("保持位姿失败")
                            break
                    except Exception as e:
                        print(f"保持位姿异常: {e}")
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

        print("正在移动到初始位姿...")
        joint_control_req = agibot_gdk.JointControlReq()
        joint_control_req.joint_names = [
            "idx01_body_joint1", "idx02_body_joint2", "idx03_body_joint3", "idx04_body_joint4", "idx05_body_joint5",
            "idx11_head_joint1", "idx12_head_joint2", "idx13_head_joint3",
            "idx21_arm_l_joint1", "idx22_arm_l_joint2", "idx23_arm_l_joint3",
            "idx24_arm_l_joint4", "idx25_arm_l_joint5", "idx26_arm_l_joint6",
            "idx27_arm_l_joint7",  # 左臂7个关节
            "idx61_arm_r_joint1", "idx62_arm_r_joint2", "idx63_arm_r_joint3",
            "idx64_arm_r_joint4", "idx65_arm_r_joint5", "idx66_arm_r_joint6",
            "idx67_arm_r_joint7"   # 右臂7个关节
        ]
        joint_control_req.joint_positions = [-0.12526109443163597,
                                            0.8407635483115572,
                                            -0.971927299903638,
                                            0, 
                                            0,
                                            0,
                                            0,
                                            0.0036426282540360732,
                                            1.7301117664332919,
                                            -1.1500181062743811,
                                            -1.5999388458662482,
                                            -1.79993398793182,
                                            -0.41992232715148303, 
                                            5.8962386534354331e-05, 
                                            3.8709046444301724e-05, 
                                            -1.7301030279359648, 
                                            -1.1500377304426637, 
                                            1.5999483134039236, 
                                            -1.6252835640650924, 
                                            0.42000178256260562, 
                                            1.3781858641160056e-05, 
                                            3.7151097206605374e-06]
        joint_control_req.joint_velocities = [0.3] * 22 # 设置速度
        joint_control_req.life_time = 5.0

        result = robot.joint_control_request(joint_control_req)
        if result != 0:
            print("移动到初始位姿失败")
            return
        print("移动到初始位姿成功，等待到位...")
        time.sleep(2)  

        controller = EndEffectorController(robot)
        controller.execute_end_pose_control()

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