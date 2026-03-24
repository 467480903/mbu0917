const zeros = length => Array(length).fill(0);
export default {
  key: 'joint', title: '关节', description: '头部、腰部、手臂、全身和单关节控制',
  commands: [
    { cmd: 'head', label: '头部 3 关节', motion: true, waitFor: 'done', payload: { joints: zeros(3), speed: 0.3 } },
    { cmd: 'waist', label: '腰部 5 关节', motion: true, waitFor: 'done', payload: { joints: zeros(5), speed: 0.3 } },
    { cmd: 'left_arm', label: '左臂 7 关节', motion: true, waitFor: 'done', payload: { joints: zeros(7), speed: 0.2 } },
    { cmd: 'right_arm', label: '右臂 7 关节', motion: true, waitFor: 'done', payload: { joints: zeros(7), speed: 0.2 } },
    { cmd: 'arms', label: '双臂', motion: true, waitFor: 'done', payload: { joints: { left: zeros(7), right: zeros(7) }, speed: 0.2 } },
    { cmd: 'wbc', label: '全身关节', motion: true, waitFor: 'done', payload: { joints: {}, speed: 0.2 } },
    { cmd: 'single_joint', label: '单关节', motion: true, waitFor: 'done', payload: { name: 'idx11_head_joint1', value: 0, speed: 0.2 } },
  ],
};
