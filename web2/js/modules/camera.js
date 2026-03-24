export default {
  key: 'camera', title: '相机', description: '单相机拍照、全部拍照与 Base64 图像读取',
  commands: [
    { cmd: 'capture', label: '单相机拍照', payload: { camera: 'kHeadColor' } },
    { cmd: 'capture_all', label: '全部相机拍照', payload: {} },
    { cmd: 'get_image', label: '读取图像', payload: { camera: 'kHeadColor' } },
  ],
};
