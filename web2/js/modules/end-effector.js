export default {
  key: 'ee', title: '夹爪', description: '左夹爪、右夹爪与双夹爪协同控制',
  commands: [
    { cmd: 'left_gripper', label: '左夹爪', motion: true, waitFor: 'done', payload: { position: 0 } },
    { cmd: 'right_gripper', label: '右夹爪', motion: true, waitFor: 'done', payload: { position: 0 } },
    { cmd: 'both_grippers', label: '双夹爪', motion: true, waitFor: 'done', payload: { left: 0, right: 0 } },
  ],
};
