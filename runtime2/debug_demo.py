#!/usr/bin/env python3
"""用于验证 runtime2 trace 单步调试的安全示例。"""


def 计算总和(数字列表):
    结果 = 0
    for 数字 in 数字列表:
        结果 += 数字
    return 结果


数据 = [1, 2, 3]
总和 = 计算总和(数据)
print(f"单步调试完成，总和={总和}")
