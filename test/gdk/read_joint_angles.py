#!/usr/bin/env python3
"""
读取当前所有电机关节角度并保存到文件
"""

import agibot_gdk
import time
import sys
import os
import json
from datetime import datetime


def read_and_save_joint_angles():
    """读取并保存关节角度"""
    print("=" * 60)
    print("关节角度读取与保存程序")
    print("=" * 60)
    
    # 初始化GDK
    print("\n[1/3] 初始化GDK...")
    if agibot_gdk.gdk_init() != agibot_gdk.GDKRes.kSuccess:
        print("❌ GDK初始化失败")
        return False
    print("✓ GDK初始化成功")
    
    try:
        # 创建机器人对象
        print("\n[2/3] 创建机器人对象...")
        robot = agibot_gdk.Robot()
        time.sleep(2)  # 等待机器人初始化完成
        print("✓ 机器人对象创建成功")
        
        # 获取当前关节状态
        print("\n[3/3] 读取关节状态...")
        joint_states = robot.get_joint_states()
        
        print(f"✓ 关节数量: {joint_states['nums']}")
        print(f"  时间戳: {joint_states['timestamp']}")
        
        # 创建logs目录
        logs_dir = os.path.join(os.path.dirname(__file__), "logs")
        os.makedirs(logs_dir, exist_ok=True)
        print(f"\n日志目录: {logs_dir}")
        
        # 准备关节角度数据
        joint_angles_data = {
            "timestamp": joint_states['timestamp'],
            "read_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "joint_count": joint_states['nums'],
            "joints": []
        }
        
        # 显示关节信息
        print("\n当前关节角度:")
        print("-" * 80)
        print(f"{'关节名称':<25} {'位置(rad)':<12} {'速度(rad/s)':<15} {'力矩(N·m)':<12}")
        print("-" * 80)
        
        for state in joint_states['states']:
            joint_info = {
                "name": state['name'],
                "position_rad": round(state['position'], 4),
                "position_deg": round(state['position'] * 180.0 / 3.14159, 2),
                "velocity": round(state['velocity'], 4),
                "effort": round(state['effort'], 4),
                "motor_position": round(state['motor_position'], 4),
                "motor_current": round(state['motor_current'], 4),
                "error_code": state['error_code']
            }
            joint_angles_data["joints"].append(joint_info)
            
            # 显示关节信息
            print(f"{state['name']:<25} {state['position']:<12.4f} {state['velocity']:<15.4f} {state['effort']:<12.4f}")
        
        print("-" * 80)
        
        # 生成文件名（带时间戳）
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        json_filename = f"joint_angles_{timestamp_str}.json"
        json_filepath = os.path.join(logs_dir, json_filename)
        
        # 保存为JSON格式
        with open(json_filepath, 'w', encoding='utf-8') as f:
            json.dump(joint_angles_data, f, indent=2, ensure_ascii=False)
        
        print(f"\n✓ 关节角度已保存到: {json_filename}")
        
        # 同时保存一份简洁的角度值文件（方便其他程序读取）
        simple_filename = f"joint_angles_{timestamp_str}_simple.txt"
        simple_filepath = os.path.join(logs_dir, simple_filename)
        
        with open(simple_filepath, 'w', encoding='utf-8') as f:
            for joint in joint_angles_data["joints"]:
                f.write(f"{joint['name']}: {joint['position_rad']:.4f} rad ({joint['position_deg']:.2f} deg)\n")
        
        print(f"✓ 简洁格式已保存到: {simple_filename}")
        
        # 显示统计信息
        print("\n关节统计信息:")
        print(f"  总关节数: {len(joint_angles_data['joints'])}")
        
        # 按部位分组统计
        body_joints = [j for j in joint_angles_data['joints'] if 'body' in j['name']]
        head_joints = [j for j in joint_angles_data['joints'] if 'head' in j['name']]
        arm_l_joints = [j for j in joint_angles_data['joints'] if 'arm_l' in j['name']]
        arm_r_joints = [j for j in joint_angles_data['joints'] if 'arm_r' in j['name']]
        
        print(f"  - 腰部关节: {len(body_joints)} 个")
        print(f"  - 头部关节: {len(head_joints)} 个")
        print(f"  - 左臂关节: {len(arm_l_joints)} 个")
        print(f"  - 右臂关节: {len(arm_r_joints)} 个")
        
        # 检查是否有错误码
        error_joints = [j for j in joint_angles_data['joints'] if j['error_code'] != 0]
        if error_joints:
            print(f"\n⚠ 检测到 {len(error_joints)} 个关节有错误:")
            for joint in error_joints:
                print(f"  {joint['name']}: 错误码 {joint['error_code']}")
        else:
            print("\n✓ 所有关节状态正常")
        
        print("\n" + "=" * 60)
        print("✓ 关节角度读取完成")
        print("=" * 60)
        
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
        success = read_and_save_joint_angles()
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
