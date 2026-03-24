const target = () => ({ position: [0.4, 0.2, 0.8], orientation: [0, 0, 0, 1] });
export default {
  key: 'pose', title: '末端位姿', description: '单臂、双臂、相对偏移与腰部位姿',
  commands: [
    { cmd: 'relative', label: '末端相对偏移', motion: true, waitFor: 'done', payload: { side: 'left', offset: [0, 0, 0], rotation: [0, 0, 0] } },
    { cmd: 'left', label: '左臂绝对位姿', motion: true, waitFor: 'done', payload: target() },
    { cmd: 'right', label: '右臂绝对位姿', motion: true, waitFor: 'done', payload: target() },
    { cmd: 'both', label: '双臂位姿', motion: true, waitFor: 'done', payload: { left: target(), right: target() } },
    { cmd: 'waist', label: '腰部偏移', motion: true, waitFor: 'done', payload: { offset: [0, 0, 0] } },
  ],
};
