#!/usr/bin/env python3
"""
全身关节运动控制示例
控制机器人所有关节运动到0位置
"""

import agibot_gdk
import time
import sys

# 全身关节名称列表（按顺序）
joint_names = [ 
    "idx01_body_joint1",  # 腰部关节1
    "idx02_body_joint2",  # 腰部关节2
    "idx03_body_joint3",  # 腰部关节3
    "idx04_body_joint4",  # 腰部关节4
    "idx05_body_joint5",  # 腰部关节5（升降）
    "idx11_head_joint1",  # 头部关节1
    "idx12_head_joint2",  # 头部关节2
    "idx13_head_joint3",  # 头部关节3
    "idx21_arm_l_joint1", # 左臂关节1
    "idx22_arm_l_joint2", # 左臂关节2
    "idx23_arm_l_joint3", # 左臂关节3
    "idx24_arm_l_joint4", # 左臂关节4
    "idx25_arm_l_joint5", # 左臂关节5
    "idx26_arm_l_joint6", # 左臂关节6
    "idx27_arm_l_joint7", # 左臂关节7
    "idx61_arm_r_joint1", # 右臂关节1
    "idx62_arm_r_joint2", # 右臂关节2
    "idx63_arm_r_joint3", # 右臂关节3
    "idx64_arm_r_joint4", # 右臂关节4
    "idx65_arm_r_joint5", # 右臂关节5
    "idx66_arm_r_joint6", # 右臂关节6
    "idx67_arm_r_joint7"  # 右臂关节7
]


def move_all_joints_to_zero():
    """控制全身关节运动到零位"""
    print("=" * 60)
    print("全身关节归零控制程序")
    print("=" * 60)
    
    # 初始化GDK
    print("\n[1/5] 初始化GDK...")
    if agibot_gdk.gdk_init() != agibot_gdk.GDKRes.kSuccess:
        print("❌ GDK初始化失败")
        return False
    print("✓ GDK初始化成功")
    
    try:
        # 创建机器人对象
        print("\n[2/5] 创建机器人对象...")
        robot = agibot_gdk.Robot()
        time.sleep(2)  # 等待机器人初始化完成
        print("✓ 机器人对象创建成功")
        
        # 获取当前关节状态
        print("\n[3/5] 获取当前关节状态...")
        joint_states = robot.get_joint_states()
        print(f"✓ 关节数量: {joint_states['nums']}")
        print("\n当前关节位置:")
        for i, state in enumerate(joint_states['states']):
            print(f"  {state['name']:20s}: {state['position']:7.3f} rad")
        
        # 准备关节控制命令
        print("\n[4/5] 准备关节控制命令...")
        joint_positions = [0.0] * len(joint_names)  # 目标位置：所有关节归零
        joint_velocities = [0.3] * len(joint_names)  # 运动速度：0.3 rad/s
        
        # 创建关节控制请求
        joint_control_request = agibot_gdk.JointControlReq()
        joint_control_request.life_time = 5.0  # 命令有效期5秒
        joint_control_request.joint_names = joint_names
        joint_control_request.joint_positions = joint_positions
        joint_control_request.joint_velocities = joint_velocities
        
        print("✓ 关节控制命令准备完成")
        print(f"  目标位置: 所有关节归零 (0.0 rad)")
        print(f"  运动速度: 0.3 rad/s")
        print(f"  命令有效期: 5.0 秒")
        
        # 发送关节控制命令
        print("\n[5/5] 发送关节控制命令...")
        robot.joint_control_request(joint_control_request)
        print("✓ 关节控制命令已发送")
        

        
        return True
        
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        # 释放GDK资源
        print("\n释放GDK资源...")
        if agibot_gdk.gdk_release() != agibot_gdk.GDKRes.kSuccess:
            print("❌ GDK释放失败")
        else:
            print("✓ GDK释放成功")


def main():
    """主函数"""
    try:
        success = move_all_joints_to_zero()
        if not success:
            sys.exit(1)
    except KeyboardInterrupt:
        print("\n\n⚠ 用户中断程序")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ 程序运行出错: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
