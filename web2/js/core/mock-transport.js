import { TOPICS } from './topics.js';

export class MockTransport {
  constructor() {
    this.listeners = new Set();
    this.connected = false;
    this.joints = [];
    this.positions = [];
    this.mapPoints = [];
  }
  onMessage(listener) { this.listeners.add(listener); return () => this.listeners.delete(listener); }
  async connect() { this.connected = true; }
  subscribe() {}
  publish(topic, payload) {
    const group = Object.keys(TOPICS).find(key => TOPICS[key]?.request === topic);
    const config = TOPICS[group];
    if (!config) throw new Error(`未知模拟 topic: ${topic}`);
    const responseTopic = group === 'sync' && payload.cmd === 'readData' ? config.data : config.response;
    const response = { cmd: payload.cmd, time: payload.time, success: true, mock: true };
    if (payload.name) response.name = payload.name;
    if (group === 'joint' && payload.cmd === 'get_current_angles') {
      const names = [
        'idx01_body_joint1', 'idx02_body_joint2', 'idx03_body_joint3',
        'idx04_body_joint4', 'idx05_body_joint5',
        'idx11_head_joint1', 'idx12_head_joint2', 'idx13_head_joint3',
        'idx21_arm_l_joint1', 'idx22_arm_l_joint2', 'idx23_arm_l_joint3',
        'idx24_arm_l_joint4', 'idx25_arm_l_joint5', 'idx26_arm_l_joint6',
        'idx27_arm_l_joint7',
        'idx61_arm_r_joint1', 'idx62_arm_r_joint2', 'idx63_arm_r_joint3',
        'idx64_arm_r_joint4', 'idx65_arm_r_joint5', 'idx66_arm_r_joint6',
        'idx67_arm_r_joint7',
      ];
      response.result = Object.fromEntries(names.map((name, index) => [name, index / 100]));
    }
    if (group === 'pose' && payload.cmd === 'get_current_pose') {
      response.side = payload.side;
      response.result = {
        position: payload.side === 'left' ? [0.4, 0.2, 1.0] : [0.4, -0.2, 1.0],
        orientation: [0, 0, 0, 1],
      };
    }
    if (group === 'db') this._databaseResponse(payload, response);
    if (group === 'tts' && payload.cmd === 'get_volume') response.volume = 80;
    if (group === 'sync' && payload.cmd === 'readData') response.value = 0;
    setTimeout(() => this._emit(responseTopic, response), 20);
    if (['base', 'joint', 'pose', 'ee'].includes(group)
        && payload.cmd !== 'stop' && !payload.cmd.startsWith('get_')) {
      setTimeout(() => this._emit(TOPICS.done, {
        cmd: payload.cmd, time: payload.time, type: group, success: true, mock: true,
      }), 45);
    }
  }

  _databaseResponse(payload, response) {
    const collections = {
      Joint: this.joints,
      Position: this.positions,
      MapPoint: this.mapPoints,
    };
    const getCommands = {
      getJoints: this.joints,
      getPositions: this.positions,
      getMapPoints: this.mapPoints,
    };
    if (getCommands[payload.cmd]) {
      response.result = structuredClone(getCommands[payload.cmd]);
      return;
    }
    const suffix = Object.keys(collections).find(name => payload.cmd.endsWith(name));
    if (!suffix) return;
    const collection = collections[suffix];
    if (payload.cmd.startsWith('add')) {
      const duplicate = collection.some(item => item.name === payload.name
        && (suffix === 'MapPoint' || item.type === payload.type));
      if (duplicate) {
        response.success = false;
        response.error = `变量已存在: ${payload.name}`;
        return;
      }
      const item = suffix === 'MapPoint'
        ? { name: payload.name, position: payload.position, orientation: payload.orientation }
        : { type: payload.type, name: payload.name, value: payload.value };
      collection.push(structuredClone(item));
      response.result = true;
    }
  }

  _emit(topic, payload) { this.listeners.forEach(listener => listener(topic, payload)); }
}
