#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
interaction_controller.py — 交互控制器

职责：
  - 控制TTS输出
"""


class InteractionController:
    """交互控制器"""
    
    def __init__(self, interaction, mqtt_client, topic_response):
        """构造函数
        
        Parameters
        ----------
        interaction : agibot_gdk.Interaction
            GDK Interaction 对象
        mqtt_client : mqtt.Client
            MQTT 客户端
        topic_response : str
            反馈主题
        """
        self.interaction = interaction
        self.mqtt_client = mqtt_client
        self.topic_response = topic_response
        self._volume = 80
    
    def _publish_response(self, cmd, ts, success=False, extra=None):
        """发布反馈报文"""
        import json
        resp = {"cmd": cmd, "time": ts}
        if success:
            resp["success"] = True
        if extra:
            resp.update(extra)
        self.mqtt_client.publish(self.topic_response, json.dumps(resp, ensure_ascii=False))
    
    # ── TTS 控制（不嵌套，直接调用 GDK）────────────────────
    
    def speak(self, text):
        """TTS 语音输出
        
        Parameters
        ----------
        text : str
            要朗读的文本
        """
        print(f"[TTS] {text}")
        
        try:
            self.interaction.tts_speak(text)
            return True
        except Exception as e:
            print(f"[TTS] 错误: {e}")
            return False
    
    def set_volume(self, volume):
        """设置音量
        
        Parameters
        ----------
        volume : int
            音量 0~100
        """
        self._volume = max(0, min(100, int(volume)))
        print(f"[TTS] 音量: {self._volume}")
        return True
    
    def get_volume(self):
        """获取当前音量"""
        return self._volume
