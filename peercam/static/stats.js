// Live connection stats for the viewer overlay (?stats). Buffer delays are
// averaged over the last interval, so they show the current value, not history.
export class StatsOverlay {
  constructor(el) {
    this.el = el;
    this.prev = new Map(); // stat id -> previous stat
  }

  clear() {
    this.el.textContent = '';
    this.prev.clear();
  }

  async update(pc, { cam, bufferMs, bufferSource }) {
    if (!pc) {
      this.clear();
      return;
    }
    const report = await pc.getStats();
    let video, audio, pair;
    report.forEach((s) => {
      if (s.type === 'inbound-rtp' && s.kind === 'video') video = s;
      else if (s.type === 'inbound-rtp' && s.kind === 'audio') audio = s;
      else if (s.type === 'transport' && s.selectedCandidatePairId) pair = report.get(s.selectedCandidatePairId);
    });
    if (!pair) {
      report.forEach((s) => {
        if (s.type === 'candidate-pair' && s.nominated && s.state === 'succeeded') pair = s;
      });
    }

    const vBuf = this.bufferMs(video);
    const aBuf = this.bufferMs(audio);
    const kbps = (this.kbps(video) ?? 0) + (this.kbps(audio) ?? 0);
    const rtt = pair?.currentRoundTripTime != null ? pair.currentRoundTripTime * 1000 : null;
    const size = video?.frameWidth ? `${video.frameWidth}×${video.frameHeight}` : '–';
    const target = bufferMs > 0 ? `${bufferMs} ms (${bufferSource})` : 'adaptive';
    const est = vBuf != null ? vBuf + (rtt ?? 0) / 2 : null;

    this.el.textContent = [
      `Cam ${cam} · ${size} · ${fmt(video?.framesPerSecond)} fps · ${(kbps / 1000).toFixed(1)} Mbps`,
      `Target  ${target}`,
      `Buffer  video ${fmt(vBuf)} ms · audio ${fmt(aBuf)} ms`,
      `Network rtt ${fmt(rtt)} ms · lost ${video?.packetsLost ?? '–'}`,
      `≈ ${fmt(est)} ms network + buffer (+ phone capture/encode)`,
    ].join('\n');

    for (const s of [video, audio]) if (s) this.prev.set(s.id, s);
  }

  delta(stat, key) {
    const p = stat && this.prev.get(stat.id);
    return p && stat[key] != null && p[key] != null ? stat[key] - p[key] : null;
  }

  bufferMs(stat) {
    const delay = this.delta(stat, 'jitterBufferDelay');
    const count = this.delta(stat, 'jitterBufferEmittedCount');
    return count > 0 ? (delay / count) * 1000 : null;
  }

  kbps(stat) {
    const bytes = this.delta(stat, 'bytesReceived');
    const ms = this.delta(stat, 'timestamp');
    return ms > 0 ? (bytes * 8) / ms : null;
  }
}

const fmt = (v) => (v == null ? '–' : Math.round(v));
