#!/usr/bin/env python3
"""
记录当前左右手末端执行器的姿态
"""

import agibot_gdk
import time
import json
import os
from datetime import datetime


LEFT_END_EFFECTOR = "arm_l_end_link"
RIGHT_END_EFFECTOR = "arm_r_end_link"


def find_pose_by_name(status, target_name):
    """根据名称查找位姿"""
    for i, frame_name in enumerate(status.frame_names):
        if frame_name == target_name:
            pose = status.frame_poses[i]
            return {
                'position': [pose.position.x, pose.position.y, pose.position.z],
                'orientation': [pose.orientation.x, pose.orientation.y, pose.orientation.z, pose.orientation.w]
            }
    raise RuntimeError(f"Frame '{target_name}' not found")


def record_end_effector_poses():
    """记录并保存末端执行器姿态"""
    # 初始化
    if agibot_gdk.gdk_init() != agibot_gdk.GDKRes.kSuccess:
        print("GDK初始化失败")
        return False
    
    try:
        robot = agibot_gdk.Robot()
        time.sleep(1)
        
        # 获取姿态
        status = robot.get_motion_control_status()
        left_pose = find_pose_by_name(status, LEFT_END_EFFECTOR)
        right_pose = find_pose_by_name(status, RIGHT_END_EFFECTOR)
        
        # 构建数据
        data = {
            'record_time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'left_end_effector': {
                'name': LEFT_END_EFFECTOR,
                'position': {'x': left_pose['position'][0], 'y': left_pose['position'][1], 'z': left_pose['position'][2]},
                'orientation': {'x': left_pose['orientation'][0], 'y': left_pose['orientation'][1], 'z': left_pose['orientation'][2], 'w': left_pose['orientation'][3]}
            },
            'right_end_effector': {
                'name': RIGHT_END_EFFECTOR,
                'position': {'x': right_pose['position'][0], 'y': right_pose['position'][1], 'z': right_pose['position'][2]},
                'orientation': {'x': right_pose['orientation'][0], 'y': right_pose['orientation'][1], 'z': right_pose['orientation'][2], 'w': right_pose['orientation'][3]}
            }
        }
        
        # 保存JSON
        output_dir = os.path.join(os.path.dirname(__file__), "poses")
        os.makedirs(output_dir, exist_ok=True)
        
        filename = f"end_effector_poses_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        filepath = os.path.join(output_dir, filename)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        print(f"\n✓ 姿态已保存: {filepath}")
        print(f"\n左手末端:")
        print(f"  位置: {left_pose['position']}")
        print(f"  姿态: {left_pose['orientation']}")
        print(f"\n右手末端:")
        print(f"  位置: {right_pose['position']}")
        print(f"  姿态: {right_pose['orientation']}")
        
        return True
        
    except Exception as e:
        print(f"错误: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        agibot_gdk.gdk_release()


if __name__ == "__main__":
    record_end_effector_poses()
