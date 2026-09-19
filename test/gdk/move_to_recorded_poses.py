#!/usr/bin/env python3
"""
末端执行器姿态运动控制
先运动到第一个记录姿态，再运动到第二个记录姿态
"""

import agibot_gdk
import time
import json
import math
import os


# 配置参数
MAX_STEP_CM = 0.1  # 最大步长（厘米）
LIFETIME = 0.02    # 生命周期（秒）
RATE_HZ = 50.0     # 发送频率（Hz）


def slerp(q0, q1, t):
    """四元数球面线性插值"""
    dot = q0[0]*q1[0] + q0[1]*q1[1] + q0[2]*q1[2] + q0[3]*q1[3]
    
    if dot < 0.0:
        dot = -dot
        q1 = [-q1[0], -q1[1], -q1[2], -q1[3]]
    
    dot = max(-1.0, min(1.0, dot))
    
    if dot > 0.9995:
        # 线性插值
        result = [q0[i] + t * (q1[i] - q0[i]) for i in range(4)]
        norm = math.sqrt(sum(r*r for r in result))
        if norm > 0.0:
            result = [r / norm for r in result]
    else:
        # 球面插值
        theta_0 = math.acos(dot)
        sin_theta_0 = math.sin(theta_0)
        theta = theta_0 * t
        sin_theta = math.sin(theta)
        s0 = math.cos(theta) - dot * sin_theta / sin_theta_0
        s1 = sin_theta / sin_theta_0
        result = [s0 * q0[i] + s1 * q1[i] for i in range(4)]
    
    return result


def distance(p1, p2):
    """计算两点距离"""
    return math.sqrt((p2[0]-p1[0])**2 + (p2[1]-p1[1])**2 + (p2[2]-p1[2])**2)


def plan_trajectory(start_pose, goal_pose, n_steps):
    """规划轨迹"""
    trajectory = []
    for i in range(n_steps):
        t = float(i) / (n_steps - 1) if n_steps > 1 else 0.0
        
        # 位置线性插值
        pos = [start_pose['position'][j] + t * (goal_pose['position'][j] - start_pose['position'][j]) for j in range(3)]
        
        # 四元数SLERP插值
        q0 = start_pose['orientation']
        q1 = goal_pose['orientation']
        quat = slerp(q0, q1, t)
        
        trajectory.append({'position': pos, 'orientation': quat})
    
    return trajectory


def find_current_pose(status, target_name):
    """查找当前位姿"""
    for i, frame_name in enumerate(status.frame_names):
        if frame_name == target_name:
            pose = status.frame_poses[i]
            return {
                'position': [pose.position.x, pose.position.y, pose.position.z],
                'orientation': [pose.orientation.x, pose.orientation.y, pose.orientation.z, pose.orientation.w]
            }
    raise RuntimeError(f"Frame '{target_name}' not found")


def load_pose_from_json(json_file):
    """从JSON文件加载姿态"""
    with open(json_file, 'r') as f:
        data = json.load(f)
    
    left = data['left_end_effector']
    right = data['right_end_effector']
    
    return {
        'left': {
            'position': [left['position']['x'], left['position']['y'], left['position']['z']],
            'orientation': [left['orientation']['x'], left['orientation']['y'], left['orientation']['z'], left['orientation']['w']]
        },
        'right': {
            'position': [right['position']['x'], right['position']['y'], right['position']['z']],
            'orientation': [right['orientation']['x'], right['orientation']['y'], right['orientation']['z'], right['orientation']['w']]
        }
    }


def move_to_pose(robot, goal_pose):
    """运动到目标姿态"""
    # 获取当前姿态
    status = robot.get_motion_control_status()
    start_left = find_current_pose(status, "arm_l_end_link")
    start_right = find_current_pose(status, "arm_r_end_link")
    
    # 计算步数
    n_left = max(int(distance(start_left['position'], goal_pose['left']['position']) * 100 / MAX_STEP_CM), 1)
    n_right = max(int(distance(start_right['position'], goal_pose['right']['position']) * 100 / MAX_STEP_CM), 1)
    n_steps = max(n_left, n_right)
    
    print(f"运动步数: {n_steps}")
    
    # 规划轨迹
    traj_left = plan_trajectory(start_left, goal_pose['left'], n_steps)
    traj_right = plan_trajectory(start_right, goal_pose['right'], n_steps)
    
    # 执行轨迹
    dt = 1.0 / RATE_HZ
    for i in range(n_steps):
        # 创建控制请求
        end_pose = agibot_gdk.EndEffectorPose()
        end_pose.life_time = LIFETIME
        end_pose.group = agibot_gdk.EndEffectorControlGroup.kBothArms
        
        # 左臂
        end_pose.left_end_effector_pose.position.x = traj_left[i]['position'][0]
        end_pose.left_end_effector_pose.position.y = traj_left[i]['position'][1]
        end_pose.left_end_effector_pose.position.z = traj_left[i]['position'][2]
        end_pose.left_end_effector_pose.orientation.x = traj_left[i]['orientation'][0]
        end_pose.left_end_effector_pose.orientation.y = traj_left[i]['orientation'][1]
        end_pose.left_end_effector_pose.orientation.z = traj_left[i]['orientation'][2]
        end_pose.left_end_effector_pose.orientation.w = traj_left[i]['orientation'][3]
        
        # 右臂
        end_pose.right_end_effector_pose.position.x = traj_right[i]['position'][0]
        end_pose.right_end_effector_pose.position.y = traj_right[i]['position'][1]
        end_pose.right_end_effector_pose.position.z = traj_right[i]['position'][2]
        end_pose.right_end_effector_pose.orientation.x = traj_right[i]['orientation'][0]
        end_pose.right_end_effector_pose.orientation.y = traj_right[i]['orientation'][1]
        end_pose.right_end_effector_pose.orientation.z = traj_right[i]['orientation'][2]
        end_pose.right_end_effector_pose.orientation.w = traj_right[i]['orientation'][3]
        
        robot.end_effector_pose_control(end_pose)
        time.sleep(dt)
    
    print("✓ 运动完成")


def main():
    # JSON文件路径
    poses_dir = os.path.join(os.path.dirname(__file__), "poses")
    json_file1 = os.path.join(poses_dir, "end_effector_poses_20260919_205622.json")
    json_file2 = os.path.join(poses_dir, "end_effector_poses_20260919_205750.json")
    
    # 初始化
    if agibot_gdk.gdk_init() != agibot_gdk.GDKRes.kSuccess:
        print("GDK初始化失败")
        return
    
    print("GDK初始化成功")
    
    try:
        robot = agibot_gdk.Robot()
        time.sleep(2)
        
        # 加载姿态
        print("\n加载目标姿态...")
        pose1 = load_pose_from_json(json_file1)
        pose2 = load_pose_from_json(json_file2)
        print(f"✓ 姿态1: {json_file1}")
        print(f"✓ 姿态2: {json_file2}")
        
        # 运动到第一个姿态
        print("\n运动到第一个姿态...")
        move_to_pose(robot, pose1)
        time.sleep(1)
        
        # 运动到第二个姿态
        print("\n运动到第二个姿态...")
        move_to_pose(robot, pose2)
        
        print("\n✓ 全部运动完成")
        
    except Exception as e:
        print(f"错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        agibot_gdk.gdk_release()
        print("\nGDK释放成功")


if __name__ == "__main__":
    main()
