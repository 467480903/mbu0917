export default {
  key: 'sync', title: '数据同步', description: 'Modbus / S7 变量的读取与写入',
  commands: [
    { cmd: 'readData', label: '读取变量', payload: { name: 'heart_beat_g2' } },
    { cmd: 'setData', label: '写入变量', payload: { name: 'heart_beat_g2', value: 1 } },
  ],
};
