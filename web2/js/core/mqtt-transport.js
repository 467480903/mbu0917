export class MqttTransport {
  constructor({ host, port = 9001 }) {
    this.host = host;
    this.port = Number(port);
    this.client = null;
    this.listeners = new Set();
    this.connected = false;
  }

  onMessage(listener) {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  connect() {
    if (!window.Paho) return Promise.reject(new Error('Paho MQTT 未加载'));
    return new Promise((resolve, reject) => {
      const id = `g2_web2_${Math.random().toString(16).slice(2, 10)}`;
      this.client = new window.Paho.Client(this.host, this.port, id);
      this.client.onMessageArrived = message => {
        try {
          const payload = JSON.parse(message.payloadString);
          this.listeners.forEach(listener => listener(message.destinationName, payload));
        } catch (error) {
          console.error('[web2] MQTT JSON 解析失败', error);
        }
      };
      this.client.onConnectionLost = () => { this.connected = false; };
      this.client.connect({
        useSSL: false,
        timeout: 5,
        onSuccess: () => { this.connected = true; resolve(); },
        onFailure: error => reject(new Error(error.errorMessage || 'MQTT 连接失败')),
      });
    });
  }

  subscribe(topic) {
    if (!this.connected) throw new Error('MQTT 未连接');
    this.client.subscribe(topic, { qos: 2 });
  }

  publish(topic, payload) {
    if (!this.connected) throw new Error('MQTT 未连接');
    const message = new window.Paho.Message(JSON.stringify(payload));
    message.destinationName = topic;
    message.qos = 2;
    this.client.send(message);
  }
}
