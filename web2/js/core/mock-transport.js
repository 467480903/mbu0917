import { TOPICS } from './topics.js';

export class MockTransport {
  constructor() { this.listeners = new Set(); this.connected = false; }
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
    if (group === 'db' && payload.cmd.startsWith('get')) response.result = [];
    if (group === 'tts' && payload.cmd === 'get_volume') response.volume = 80;
    if (group === 'sync' && payload.cmd === 'readData') response.value = 0;
    setTimeout(() => this._emit(responseTopic, response), 20);
    if (['base', 'joint', 'pose', 'ee'].includes(group) && payload.cmd !== 'stop') {
      setTimeout(() => this._emit(TOPICS.done, {
        cmd: payload.cmd, time: payload.time, type: group, success: true, mock: true,
      }), 45);
    }
  }
  _emit(topic, payload) { this.listeners.forEach(listener => listener(topic, payload)); }
}
