export default {
  key: 'apriltag', title: 'Apriltag', description: '文件路径与已保存图片的 Apriltag 检测',
  commands: [
    { cmd: 'detect_file', label: '检测指定文件', payload: { file: '/data/wxf/mbu0917/images/sample.jpg' } },
    { cmd: 'detect_saved', label: '检测已保存图片', payload: { file: 'sample.jpg' } },
  ],
};
