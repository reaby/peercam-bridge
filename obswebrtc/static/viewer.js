import { Signaling } from './signaling.js';
import { StatsOverlay } from './stats.js';

const params = new URLSearchParams(location.search);
const cam = parseInt(params.get('cam') || '1', 10);
const quiet = params.has('quiet');
// ?delay=N overrides the buffer target set in OBS for this one viewer.
const delayParam = params.has('delay') ? clampDelay(parseInt(params.get('delay'), 10)) : null;

const video = document.getElementById('video');
const waiting = document.getElementById('waiting');
const stats = params.has('stats') ? new StatsOverlay(document.getElementById('stats')) : null;

let pc = null;
let senderId = null;
let bufferMs = delayParam ?? 0;

function clampDelay(ms) {
  return Number.isFinite(ms) ? Math.min(Math.max(ms, 0), 4000) : 0;
}

// A fixed jitter buffer keeps the delay constant (and equal across cameras),
// so one audio sync offset in OBS stays correct. 0 = browser's adaptive default.
function setBufferTarget(receiver) {
  try {
    if ('jitterBufferTarget' in receiver) {
      receiver.jitterBufferTarget = bufferMs > 0 ? bufferMs : null;
    } else if ('playoutDelayHint' in receiver && bufferMs > 0) {
      receiver.playoutDelayHint = bufferMs / 1000; // older Chromium, in seconds
    }
  } catch (e) {
    console.warn('buffer target', e);
  }
}

function applyBufferTarget() {
  for (const receiver of pc?.getReceivers() ?? []) setBufferTarget(receiver);
}

function onServerBuffer(ms) {
  if (delayParam !== null || typeof ms !== 'number') return;
  bufferMs = clampDelay(ms);
  applyBufferTarget();
}

function showWaiting(text) {
  waiting.textContent = text;
  waiting.classList.toggle('hidden', quiet || !text);
  video.classList.toggle('hidden', !!text);
}

function closePc() {
  pc?.close();
  pc = null;
  senderId = null;
  video.srcObject = null;
}

function play() {
  // OBS's browser allows autoplay with sound; regular browsers may require muting.
  video.muted = false;
  video.play().catch(() => {
    video.muted = true;
    video.play().catch(() => {});
  });
}

async function onOffer(msg) {
  closePc();
  senderId = msg.from;
  pc = new RTCPeerConnection({ iceServers: [] });

  pc.ontrack = (e) => {
    setBufferTarget(e.receiver);
    if (video.srcObject !== e.streams[0]) {
      video.srcObject = e.streams[0];
      play();
    }
    showWaiting('');
  };
  pc.onicecandidate = (e) => {
    if (e.candidate) sig.send({ type: 'candidate', to: senderId, candidate: e.candidate });
  };
  pc.onconnectionstatechange = () => {
    if (pc?.connectionState === 'failed') showWaiting(`Cam ${cam}: connection failed`);
  };

  await pc.setRemoteDescription(msg.sdp);
  await pc.setLocalDescription(await pc.createAnswer());
  sig.send({ type: 'answer', to: senderId, sdp: pc.localDescription });
}

async function onSignal(msg) {
  switch (msg.type) {
    case 'joined':
      onServerBuffer(msg.bufferMs);
      if (!msg.senderPresent) showWaiting(`Waiting for Cam ${cam}…`);
      break;
    case 'config':
      onServerBuffer(msg.bufferMs);
      break;
    case 'offer':
      await onOffer(msg);
      break;
    case 'candidate':
      if (pc && msg.from === senderId) await pc.addIceCandidate(msg.candidate);
      break;
    case 'sender-left':
      if (msg.from === senderId || senderId === null) {
        closePc();
        showWaiting(`Waiting for Cam ${cam}…`);
      }
      break;
    case 'error':
      showWaiting(`Cam ${cam}: ${msg.error}`);
      break;
  }
}

const sig = new Signaling(onSignal, (state) => {
  if (state === 'closed') {
    closePc();
    showWaiting('Reconnecting to server…');
  }
});

showWaiting('Connecting…');
sig.connect({ type: 'join', role: 'viewer', cam });

if (stats) {
  document.getElementById('stats').classList.remove('hidden');
  setInterval(() => {
    stats.update(pc, { cam, bufferMs, bufferSource: delayParam !== null ? 'url' : 'OBS' })
      .catch(() => {});
  }, 1000);
}
