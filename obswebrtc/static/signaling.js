// WebSocket signaling client with auto-reconnect. Messages are handled one at a
// time so e.g. ICE candidates never race ahead of setRemoteDescription().
export class Signaling {
  constructor(onMessage, onState = () => {}) {
    this.onMessage = onMessage;
    this.onState = onState;
    this.ws = null;
    this.joinMsg = null;
    this.closed = false;
    this.queue = Promise.resolve();
  }

  connect(joinMsg) {
    this.joinMsg = joinMsg;
    this.closed = false;
    this._open();
  }

  send(msg) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(msg));
    }
  }

  close() {
    this.closed = true;
    if (this.ws) this.ws.close();
  }

  _open() {
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const ws = new WebSocket(`${proto}//${location.host}/ws`);
    this.ws = ws;

    ws.onopen = () => {
      this.onState('open');
      if (this.joinMsg) this.send(this.joinMsg);
    };
    ws.onmessage = (e) => {
      let msg;
      try { msg = JSON.parse(e.data); } catch { return; }
      this.queue = this.queue.then(() => this.onMessage(msg)).catch((err) => console.error(err));
    };
    ws.onclose = () => {
      if (this.ws !== ws) return;
      this.onState('closed');
      if (!this.closed) setTimeout(() => this._open(), 2000);
    };
  }
}
