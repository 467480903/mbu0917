#!/usr/bin/env python3
"""执行 runtime2 用户程序。"""

import argparse
import runpy
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="运行 G2 runtime2 用户程序")
    parser.add_argument("program", help="要执行的 Python 程序路径")
    args = parser.parse_args()
    program = Path(args.program).expanduser().resolve()
    if not program.is_file() or program.suffix != ".py":
        raise SystemExit(f"不是有效的 Python 程序: {program}")
    runpy.run_path(str(program), run_name="__main__")


if __name__ == "__main__":
    main()
