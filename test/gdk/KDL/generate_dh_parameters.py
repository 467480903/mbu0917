#!/usr/bin/env python3
"""
从URDF文件提取DH参数并生成配置文件
DH参数用于机器人运动学计算
"""

import xml.etree.ElementTree as ET
import numpy as np
import json
import os
from datetime import datetime
import math


class URDFtoDHConverter:
    """从URDF提取DH参数"""
    
    def __init__(self, urdf_file):
        self.urdf_file = urdf_file
        self.tree = ET.parse(urdf_file)
        self.root = self.tree.getroot()
        self.joints = {}
        self.links = {}
        self.dh_params = {}
        
    def parse_urdf(self):
        """解析URDF文件"""
        print("=" * 60)
        print("解析URDF文件")
        print("=" * 60)
        
        # 解析所有link
        for link in self.root.findall('link'):
            link_name = link.get('name')
            self.links[link_name] = {
                'name': link_name,
                'inertial': None,
                'visual': None,
                'collision': None
            }
            
            # 提取惯性参数
            inertial = link.find('inertial')
            if inertial is not None:
                origin = inertial.find('origin')
                mass = inertial.find('mass')
                inertia = inertial.find('inertia')
                
                self.links[link_name]['inertial'] = {
                    'origin': origin.get('xyz').split() if origin is not None else [0, 0, 0],
                    'mass': float(mass.get('value')) if mass is not None else 0.0
                }
        
        # 解析所有joint
        for joint in self.root.findall('joint'):
            joint_name = joint.get('name')
            joint_type = joint.get('type')
            
            # 只处理旋转关节（revolute）和连续旋转关节（continuous）
            if joint_type not in ['revolute', 'continuous']:
                continue
            
            parent = joint.find('parent')
            child = joint.find('child')
            origin = joint.find('origin')
            axis = joint.find('axis')
            limit = joint.find('limit')
            
            joint_info = {
                'name': joint_name,
                'type': joint_type,
                'parent': parent.get('link') if parent is not None else None,
                'child': child.get('link') if child is not None else None,
                'origin_xyz': [0.0, 0.0, 0.0],
                'origin_rpy': [0.0, 0.0, 0.0],
                'axis': [0.0, 0.0, 1.0],  # 默认Z轴旋转
                'lower_limit': 0.0,
                'upper_limit': 0.0,
                'effort': 0.0,
                'velocity': 0.0
            }
            
            if origin is not None:
                xyz = origin.get('xyz')
                rpy = origin.get('rpy')
                if xyz:
                    joint_info['origin_xyz'] = [float(x) for x in xyz.split()]
                if rpy:
                    joint_info['origin_rpy'] = [float(x) for x in rpy.split()]
            
            if axis is not None:
                xyz = axis.get('xyz')
                if xyz:
                    joint_info['axis'] = [float(x) for x in xyz.split()]
            
            if limit is not None:
                joint_info['lower_limit'] = float(limit.get('lower', 0))
                joint_info['upper_limit'] = float(limit.get('upper', 0))
                joint_info['effort'] = float(limit.get('effort', 0))
                joint_info['velocity'] = float(limit.get('velocity', 0))
            
            self.joints[joint_name] = joint_info
        
        print(f"✓ 解析完成")
        print(f"  Link数量: {len(self.links)}")
        print(f"  关节数量: {len(self.joints)}")
        
    def compute_dh_parameters(self):
        """计算DH参数
        
        DH参数说明:
        - d: 沿Z轴的距离
        - theta: 绕Z轴的旋转角度
        - a: 沿X轴的距离
        - alpha: 绕X轴的旋转角度
        
        对于每个关节，我们需要根据URDF中的origin和axis计算DH参数
        """
        print("\n" + "=" * 60)
        print("计算DH参数")
        print("=" * 60)
        
        for joint_name, joint_info in self.joints.items():
            # 获取关节参数
            xyz = joint_info['origin_xyz']  # 平移
            rpy = joint_info['origin_rpy']  # 旋转（roll, pitch, yaw）
            axis = joint_info['axis']  # 旋转轴
            
            # 计算DH参数
            # 注意：URDF的坐标系定义与标准DH参数略有不同
            # 这里采用简化方法，提取关键的几何参数
            
            # d: 沿Z轴的距离
            d = xyz[2]  # z方向的平移
            
            # theta: 绕Z轴的旋转（关节角度）
            theta = 0.0  # 初始角度为0，这是关节变量
            
            # a: 沿X轴的距离
            a = math.sqrt(xyz[0]**2 + xyz[1]**2)  # xy平面的距离
            
            # alpha: 绕X轴的旋转
            alpha = rpy[0]  # roll角度
            
            # 根据旋转轴调整参数
            if axis == [1, 0, 0]:  # X轴旋转
                d = xyz[0]
                alpha = rpy[1]  # pitch
            elif axis == [0, 1, 0]:  # Y轴旋转
                d = xyz[1]
                alpha = rpy[2]  # yaw
            
            self.dh_params[joint_name] = {
                'name': joint_name,
                'parent': joint_info['parent'],
                'child': joint_info['child'],
                'd': round(d, 6),
                'theta': round(theta, 6),
                'a': round(a, 6),
                'alpha': round(alpha, 6),
                'axis': axis,
                'origin_xyz': xyz,
                'origin_rpy': rpy,
                'joint_limits': {
                    'lower': joint_info['lower_limit'],
                    'upper': joint_info['upper_limit']
                }
            }
        
        print(f"✓ DH参数计算完成")
        print(f"  处理关节数: {len(self.dh_params)}")
        
    def save_dh_parameters(self, output_dir):
        """保存DH参数到文件"""
        print("\n" + "=" * 60)
        print("保存DH参数")
        print("=" * 60)
        
        os.makedirs(output_dir, exist_ok=True)
        
        # 1. 保存JSON格式（完整信息）
        json_file = os.path.join(output_dir, 'dh_parameters.json')
        output_data = {
            'robot_name': 'G2',
            'generated_time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'source_file': self.urdf_file,
            'joint_count': len(self.dh_params),
            'dh_parameters': self.dh_params
        }
        
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
        
        print(f"✓ JSON格式保存: {json_file}")
        
        # 2. 保存CSV格式（便于导入其他工具）
        csv_file = os.path.join(output_dir, 'dh_parameters.csv')
        with open(csv_file, 'w', encoding='utf-8') as f:
            f.write("# DH Parameters for G2 Robot\n")
            f.write("# Generated: {}\n".format(datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            f.write("# Joint_Name, Parent, Child, d(m), theta(rad), a(m), alpha(rad), Axis, Lower_Limit(rad), Upper_Limit(rad)\n")
            
            for joint_name, params in self.dh_params.items():
                f.write("{},{},{},{:.6f},{:.6f},{:.6f},{:.6f},{},{:.6f},{:.6f}\n".format(
                    joint_name,
                    params['parent'],
                    params['child'],
                    params['d'],
                    params['theta'],
                    params['a'],
                    params['alpha'],
                    params['axis'],
                    params['joint_limits']['lower'],
                    params['joint_limits']['upper']
                ))
        
        print(f"✓ CSV格式保存: {csv_file}")
        
        # 3. 保存Python格式（便于程序使用）
        py_file = os.path.join(output_dir, 'dh_parameters.py')
        with open(py_file, 'w', encoding='utf-8') as f:
            f.write('"""\n')
            f.write('G2机器人DH参数配置文件\n')
            f.write('自动生成于: {}\n'.format(datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            f.write('源文件: {}\n'.format(self.urdf_file))
            f.write('"""\n\n')
            f.write('# DH参数定义\n')
            f.write('# 格式: [d, theta, a, alpha]\n')
            f.write('DH_TABLE = {\n')
            
            for joint_name, params in self.dh_params.items():
                f.write('    "{}": {{\n'.format(joint_name))
                f.write('        "d": {:.6f},\n'.format(params['d']))
                f.write('        "theta": {:.6f},\n'.format(params['theta']))
                f.write('        "a": {:.6f},\n'.format(params['a']))
                f.write('        "alpha": {:.6f},\n'.format(params['alpha']))
                f.write('        "axis": {},\n'.format(params['axis']))
                f.write('        "limits": [{:.6f}, {:.6f}]\n'.format(
                    params['joint_limits']['lower'],
                    params['joint_limits']['upper']
                ))
                f.write('    }},\n')
            
            f.write('}\n\n')
            f.write('# 关节顺序（按运动链）\n')
            f.write('JOINT_ORDER = [\n')
            
            # 按照G2的关节顺序排列
            joint_order = [
                'idx01_body_joint1', 'idx02_body_joint2', 'idx03_body_joint3',
                'idx04_body_joint4', 'idx05_body_joint5',
                'idx11_head_joint1', 'idx12_head_joint2', 'idx13_head_joint3',
                'idx21_arm_l_joint1', 'idx22_arm_l_joint2', 'idx23_arm_l_joint3',
                'idx24_arm_l_joint4', 'idx25_arm_l_joint5', 'idx26_arm_l_joint6',
                'idx27_arm_l_joint7',
                'idx61_arm_r_joint1', 'idx62_arm_r_joint2', 'idx63_arm_r_joint3',
                'idx64_arm_r_joint4', 'idx65_arm_r_joint5', 'idx66_arm_r_joint6',
                'idx67_arm_r_joint7'
            ]
            
            for joint in joint_order:
                if joint in self.dh_params:
                    f.write('    "{}",\n'.format(joint))
            
            f.write(']\n')
        
        print(f"✓ Python格式保存: {py_file}")
        
        # 4. 保存简洁文本格式（人类可读）
        txt_file = os.path.join(output_dir, 'dh_parameters.txt')
        with open(txt_file, 'w', encoding='utf-8') as f:
            f.write("=" * 80 + "\n")
            f.write("G2机器人DH参数表\n")
            f.write("生成时间: {}\n".format(datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            f.write("=" * 80 + "\n\n")
            
            # 按部位分组
            sections = {
                '腰部关节': ['idx01_body_joint1', 'idx02_body_joint2', 'idx03_body_joint3',
                           'idx04_body_joint4', 'idx05_body_joint5'],
                '头部关节': ['idx11_head_joint1', 'idx12_head_joint2', 'idx13_head_joint3'],
                '左臂关节': ['idx21_arm_l_joint1', 'idx22_arm_l_joint2', 'idx23_arm_l_joint3',
                           'idx24_arm_l_joint4', 'idx25_arm_l_joint5', 'idx26_arm_l_joint6',
                           'idx27_arm_l_joint7'],
                '右臂关节': ['idx61_arm_r_joint1', 'idx62_arm_r_joint2', 'idx63_arm_r_joint3',
                           'idx64_arm_r_joint4', 'idx65_arm_r_joint5', 'idx66_arm_r_joint6',
                           'idx67_arm_r_joint7']
            }
            
            for section_name, joint_list in sections.items():
                f.write(f"\n【{section_name}】\n")
                f.write("-" * 80 + "\n")
                f.write(f"{'关节名称':<25} {'d(m)':<10} {'theta(rad)':<12} {'a(m)':<10} {'alpha(rad)':<12}\n")
                f.write("-" * 80 + "\n")
                
                for joint_name in joint_list:
                    if joint_name in self.dh_params:
                        params = self.dh_params[joint_name]
                        f.write(f"{joint_name:<25} {params['d']:<10.6f} {params['theta']:<12.6f} "
                               f"{params['a']:<10.6f} {params['alpha']:<12.6f}\n")
                
                f.write("\n")
            
            f.write("=" * 80 + "\n")
            f.write("关节限位:\n")
            f.write("-" * 80 + "\n")
            
            for joint_name, params in self.dh_params.items():
                lower = params['joint_limits']['lower']
                upper = params['joint_limits']['upper']
                lower_deg = lower * 180.0 / math.pi
                upper_deg = upper * 180.0 / math.pi
                f.write(f"{joint_name:<25}: [{lower:7.4f}, {upper:7.4f}] rad "
                       f"[{lower_deg:7.2f}, {upper_deg:7.2f}] deg\n")
            
            f.write("=" * 80 + "\n")
        
        print(f"✓ 文本格式保存: {txt_file}")
        
    def print_summary(self):
        """打印摘要信息"""
        print("\n" + "=" * 60)
        print("DH参数摘要")
        print("=" * 60)
        
        # 按部位统计
        body_joints = [j for j in self.dh_params.keys() if 'body' in j]
        head_joints = [j for j in self.dh_params.keys() if 'head' in j]
        arm_l_joints = [j for j in self.dh_params.keys() if 'arm_l' in j]
        arm_r_joints = [j for j in self.dh_params.keys() if 'arm_r' in j]
        
        print(f"\n关节数量统计:")
        print(f"  腰部关节: {len(body_joints)}")
        print(f"  头部关节: {len(head_joints)}")
        print(f"  左臂关节: {len(arm_l_joints)}")
        print(f"  右臂关节: {len(arm_r_joints)}")
        print(f"  总计: {len(self.dh_params)}")
        
        print("\n示例关节DH参数:")
        for i, (joint_name, params) in enumerate(list(self.dh_params.items())[:3]):
            print(f"\n  关节 {i+1}: {joint_name}")
            print(f"    d     = {params['d']:.6f} m")
            print(f"    theta = {params['theta']:.6f} rad")
            print(f"    a     = {params['a']:.6f} m")
            print(f"    alpha = {params['alpha']:.6f} rad")
            print(f"    axis  = {params['axis']}")
        
        print("\n" + "=" * 60)


def main():
    """主函数"""
    # URDF文件路径
    urdf_file = "/data/wxf/mbu0917/web/meshes/model.urdf"
    
    # 输出目录
    output_dir = os.path.join(os.path.dirname(__file__), "dh_output")
    
    print("G2机器人DH参数生成工具")
    print("=" * 60)
    print(f"输入文件: {urdf_file}")
    print(f"输出目录: {output_dir}")
    print("=" * 60)
    
    # 检查URDF文件是否存在
    if not os.path.exists(urdf_file):
        print(f"错误: URDF文件不存在: {urdf_file}")
        return False
    
    try:
        # 创建转换器
        converter = URDFtoDHConverter(urdf_file)
        
        # 解析URDF
        converter.parse_urdf()
        
        # 计算DH参数
        converter.compute_dh_parameters()
        
        # 保存DH参数
        converter.save_dh_parameters(output_dir)
        
        # 打印摘要
        converter.print_summary()
        
        print("\n✓ DH参数生成完成!")
        print(f"输出文件位于: {output_dir}")
        
        return True
        
    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    import sys
    sys.exit(0 if main() else 1)
