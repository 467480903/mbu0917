export default {
  key: 'base', title: '底盘', description: '相对移动、速度移动、点位导航与停止',
  commands: [
    { cmd: 'relative', label: '相对移动', motion: true, waitFor: 'done', payload: { x: 0, y: 0, rotate: 0 } },
    { cmd: 'relative2', label: '带速度相对移动', motion: true, waitFor: 'done', payload: { x: 0, y: 0, rotate: 0, vel_line: 0.25, vel_rotate: 10 } },
    { cmd: 'point', label: '单点导航', motion: true, waitFor: 'done', payload: { name: '1' } },
    { cmd: 'points', label: '多点导航', motion: true, waitFor: 'done', payload: { val: ['1', '2'], vel_line: 0.25, vel_rotate: 10 } },
    { cmd: 'stop', label: '停止底盘', motion: true, payload: {} },
  ],
};
