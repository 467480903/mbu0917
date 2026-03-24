import { TOPICS, responseTopics } from './topics.js';
import { nextTimestamp } from './timestamp.js';

export class ServiceClient {
  constructor(transport, onEvent = () => {}) {
    this.transport = transport;
    this.onEvent = onEvent;
    this.pending = new Map();
    transport.onMessage((topic, payload) => this._receive(topic, payload));
  }

  async connect() {
    await this.transport.connect();
    responseTopics().forEach(topic => this.transport.subscribe(topic));
  }

  send(group, body, { waitFor = 'response', timeout = 120000 } = {}) {
    const config = TOPICS[group];
    if (!config) return Promise.reject(new Error(`未知服务模块: ${group}`));
    const payload = { ...body, time: body.time || nextTimestamp() };
    const targetTopic = waitFor === 'done'
      ? TOPICS.done
      : (group === 'sync' && payload.cmd === 'readData' ? config.data : config.response);
    this.onEvent('send', config.request, payload);
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(payload.time);
        reject(new Error(`等待 ${payload.cmd} 反馈超时`));
      }, timeout);
      this.pending.set(payload.time, { cmd: payload.cmd, targetTopic, resolve, reject, timer });
      try { this.transport.publish(config.request, payload); }
      catch (error) { clearTimeout(timer); this.pending.delete(payload.time); reject(error); }
    });
  }

  _receive(topic, payload) {
    this.onEvent('receive', topic, payload);
    const request = this.pending.get(payload.time);
    if (!request || request.cmd !== payload.cmd || request.targetTopic !== topic) return;
    clearTimeout(request.timer);
    this.pending.delete(payload.time);
    if (payload.success === false) request.reject(new Error(payload.error || '服务执行失败'));
    else request.resolve(payload);
  }
}
