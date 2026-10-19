#!/usr/bin/env python3
"""仅使用 agibot_gdk 播放 TTS。

运行前执行：
  source /home/agi/app/gdk/scripts/env.sh /home/agi/app
  python3 /data/wxf/mbu0917/test/gdk/tts.py "你好，我是 G2 机器人"
"""

import sys
import time

import agibot_gdk


def main():
    text = sys.argv[1] if len(sys.argv) > 1 else "GDK 语音输出测试"
    if agibot_gdk.gdk_init() != agibot_gdk.GDKRes.kSuccess:
        print("GDK 初始化失败")
        return 1

    try:
        interaction = agibot_gdk.Interaction()
        time.sleep(2)
        interaction.set_language(agibot_gdk.Language.kLanguageChinese)
        interaction.play_tts(text)
        print(f"TTS 播放命令执行成功: {text}")
        return 0
    except Exception as error:
        print(f"TTS 播放失败: {error}")
        return 1
    finally:
        agibot_gdk.gdk_release()


if __name__ == "__main__":
    raise SystemExit(main())
