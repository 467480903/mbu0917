export default {
  key: 'tts', title: '语音', description: 'TTS 播放与音量设置',
  commands: [
    { cmd: 'speak', label: '语音播放', payload: { text: 'G2 语音测试' } },
    { cmd: 'set_volume', label: '设置音量', payload: { volume: 80 } },
    { cmd: 'get_volume', label: '读取音量', payload: {} },
  ],
};
