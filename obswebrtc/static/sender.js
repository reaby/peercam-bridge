import { Signaling } from './signaling.js';

const $ = (id) => document.getElementById(id);
const els = {
  app: $('app'), preview: $('preview'), cam: $('cam'), facing: $('facing'),
  bitrate: $('bitrate'), audio: $('audio'), start: $('start'), status: $('status'),
  dim: $('dim'), blackout: $('blackout'), blackoutText: $('blackout-text'), wake: $('wake'),
};

const PREFS_KEY = 'obswebrtc.sender';
const pcs = new Map(); // viewer id -> RTCPeerConnection
const viewers = new Set(); // viewer ids the server says are in our slot
let stream = null;
let sig = null;
let wakeLock = null;
let live = false;

const setStatus = (text) => { els.status.textContent = text; };

// --- preferences -------------------------------------------------------------

function loadPrefs() {
  try { return JSON.parse(localStorage.getItem(PREFS_KEY)) || {}; } catch { return {}; }
}

function savePrefs() {
  const prefs = { cam: els.cam.value, facing: els.facing.value,
                  bitrate: els.bitrate.value, audio: els.audio.checked };
  try { localStorage.setItem(PREFS_KEY, JSON.stringify(prefs)); } catch {}
}

async function init() {
  let cfg = { maxCameras: 5, activeCams: [] };
  try { cfg = await (await fetch('/api/config')).json(); } catch {}

  for (let i = 1; i <= cfg.maxCameras; i++) {
    const opt = new Option(`Cam ${i}${cfg.activeCams.includes(i) ? ' (in use)' : ''}`, i);
    els.cam.add(opt);
  }

  const prefs = loadPrefs();
  if (prefs.cam && prefs.cam <= cfg.maxCameras) els.cam.value = prefs.cam;
  if (prefs.facing) els.facing.value = prefs.facing;
  if (prefs.bitrate) els.bitrate.value = prefs.bitrate;
  els.audio.checked = prefs.audio ?? true;

  if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
    els.start.disabled = true;
    setStatus('Camera access needs HTTPS. Open this page via https:// (or localhost).');
  }
}

// --- media -------------------------------------------------------------------

function videoConstraints() {
  return {
    facingMode: { ideal: els.facing.value },
    width: { ideal: 1920 }, height: { ideal: 1080 }, frameRate: { ideal: 30 },
  };
}

function audioConstraints() {
  // Raw-ish sound for recording; phone call processing makes ambience sound bad.
  return els.audio.checked
    ? { echoCancellation: false, noiseSuppression: false, autoGainControl: false }
    : false;
}

function showPreview() {
  els.preview.srcObject = stream;
  els.preview.classList.toggle('mirror', els.facing.value === 'user');
}

function prepareVideoTrack(track) {
  // Prefer keeping resolution over frame rate when bandwidth drops.
  if (track && 'contentHint' in track) track.contentHint = 'detail';
}

async function captureTrack(kind) {
  const constraints = kind === 'video' ? { video: videoConstraints() } : { audio: audioConstraints() };
  const track = (await navigator.mediaDevices.getUserMedia(constraints)).getTracks()[0];
  if (kind === 'video') prepareVideoTrack(track);
  return track;
}

// Swap a track in the local stream and in every connection, without renegotiating.
async function swapTrack(old, track) {
  stream.removeTrack(old);
  stream.addTrack(track);
  for (const pc of pcs.values()) {
    const senders = pc.getSenders();
    const sender = senders.find((s) => s.track === old) || senders.find((s) => s.track?.kind === track.kind);
    if (sender) await sender.replaceTrack(track);
  }
  showPreview();
}

async function switchLens() {
  const old = stream?.getVideoTracks()[0];
  if (!old) return;
  // Many phones can't open two cameras at once, so release the old one first.
  old.stop();
  await swapTrack(old, await captureTrack('video'));
}

// Locking the phone or leaving the browser can end camera/mic tracks; reopen them.
async function recoverTracks() {
  if (!stream) return;
  const ended = stream.getTracks().filter((t) => t.readyState === 'ended');
  for (const old of ended) {
    try {
      await swapTrack(old, await captureTrack(old.kind));
    } catch (e) {
      setStatus(`Could not reopen ${old.kind}: ${e.message || e.name}`);
      return;
    }
  }
  if (ended.length) updateLiveStatus();
}

async function applyBitrate(pc) {
  const kbps = Number(els.bitrate.value);
  for (const sender of pc.getSenders()) {
    if (sender.track?.kind !== 'video') continue;
    const params = sender.getParameters();
    if (!params.encodings?.length) params.encodings = [{}];
    if (kbps) params.encodings[0].maxBitrate = kbps * 1000;
    else delete params.encodings[0].maxBitrate;
    try { await sender.setParameters(params); } catch (e) { console.warn('setParameters', e); }
  }
}

// --- peer connections --------------------------------------------------------

function closePc(id) {
  pcs.get(id)?.close();
  pcs.delete(id);
  updateLiveStatus();
}

async function connectViewer(id) {
  closePc(id);
  const pc = new RTCPeerConnection({ iceServers: [] });
  pcs.set(id, pc);
  for (const track of stream.getTracks()) pc.addTrack(track, stream);

  pc.onicecandidate = (e) => {
    if (e.candidate) sig.send({ type: 'candidate', to: id, candidate: e.candidate });
  };
  pc.onconnectionstatechange = () => {
    if (pc.connectionState === 'failed' && pcs.get(id) === pc) {
      closePc(id);
      // e.g. after the phone was locked for a while: offer again if OBS is still there.
      setTimeout(() => {
        if (live && viewers.has(id) && !pcs.has(id)) connectViewer(id).catch(console.error);
      }, 1000);
    }
    updateLiveStatus();
  };

  await pc.setLocalDescription(await pc.createOffer());
  sig.send({ type: 'offer', to: id, sdp: pc.localDescription });
}

function updateLiveStatus() {
  if (!live) return;
  const connected = [...pcs.values()].filter((pc) => pc.connectionState === 'connected').length;
  setStatus(`Live on Cam ${els.cam.value} · ${connected ? `${connected} viewer(s)` : 'waiting for OBS'}`);
}

async function onSignal(msg) {
  switch (msg.type) {
    case 'joined':
      updateLiveStatus();
      break;
    case 'viewer-joined':
      viewers.add(msg.id);
      await connectViewer(msg.id);
      break;
    case 'viewer-left':
      viewers.delete(msg.id);
      closePc(msg.id);
      break;
    case 'answer': {
      const pc = pcs.get(msg.from);
      if (!pc) break;
      await pc.setRemoteDescription(msg.sdp);
      await applyBitrate(pc);
      break;
    }
    case 'candidate':
      await pcs.get(msg.from)?.addIceCandidate(msg.candidate);
      break;
    case 'replaced':
      stop();
      setStatus(`Another device took Cam ${els.cam.value}.`);
      break;
    case 'error':
      setStatus(`Server: ${msg.error}`);
      break;
  }
}

function onSocketState(state) {
  if (!live) return;
  if (state === 'closed') {
    // The server re-pairs everyone after we rejoin.
    viewers.clear();
    for (const id of [...pcs.keys()]) closePc(id);
    setStatus('Connection lost, reconnecting…');
  }
}

// --- start / stop ------------------------------------------------------------

function setWakeStatus(text, ok) {
  els.wake.textContent = text;
  els.wake.classList.toggle('warn', !ok);
}

async function requestWakeLock() {
  if (!('wakeLock' in navigator)) {
    setWakeStatus('This browser can\'t keep the screen on. Turn off auto-lock in phone settings.', false);
    return;
  }
  if (wakeLock && !wakeLock.released) return;
  try {
    const lock = await navigator.wakeLock.request('screen');
    wakeLock = lock;
    setWakeStatus('Screen will stay on. Use Dim instead of the power button.', true);
    // The browser drops the lock whenever the page is hidden; re-taken on return.
    lock.addEventListener('release', () => {
      if (live && wakeLock === lock) setWakeStatus('Screen lock released, will re-enable when visible.', false);
    });
  } catch (e) {
    setWakeStatus(`Could not keep the screen on (${e.name}). Turn off auto-lock in phone settings.`, false);
  }
}

function releaseWakeLock() {
  const lock = wakeLock;
  wakeLock = null;
  lock?.release().catch(() => {});
  setWakeStatus('', true);
}

// --- blackout ("dim") --------------------------------------------------------

function setBlackout(on) {
  els.blackout.hidden = !on;
  els.blackoutText.textContent = `Live on Cam ${els.cam.value}. Tap to wake.`;
  if (on) els.preview.pause();
  else els.preview.play().catch(() => {});
}

function setLive(on) {
  live = on;
  els.app.classList.toggle('live', on);
  els.start.textContent = on ? 'Stop' : 'Start';
  els.cam.disabled = on;
  els.audio.disabled = on;
  els.dim.hidden = !on;
  if (!on) setBlackout(false);
}

async function start() {
  els.start.disabled = true;
  // Ask before the camera prompt: some browsers only grant it right after a tap.
  requestWakeLock();
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      video: videoConstraints(), audio: audioConstraints(),
    });
  } catch (e) {
    setStatus(`Camera error: ${e.message || e.name}`);
    releaseWakeLock();
    els.start.disabled = false;
    return;
  }
  prepareVideoTrack(stream.getVideoTracks()[0]);
  showPreview();
  setLive(true);
  savePrefs();

  sig = new Signaling(onSignal, onSocketState);
  sig.connect({ type: 'join', role: 'sender', cam: Number(els.cam.value) });
  setStatus('Connecting…');
  els.start.disabled = false;
}

function stop() {
  sig?.close();
  sig = null;
  viewers.clear();
  for (const id of [...pcs.keys()]) closePc(id);
  stream?.getTracks().forEach((t) => t.stop());
  stream = null;
  els.preview.srcObject = null;
  releaseWakeLock();
  setLive(false);
  setStatus('Stopped.');
}

els.start.addEventListener('click', () => (live ? stop() : start()));

els.bitrate.addEventListener('change', () => {
  savePrefs();
  for (const pc of pcs.values()) applyBitrate(pc);
});

els.facing.addEventListener('change', async () => {
  savePrefs();
  if (!live) return;
  try { await switchLens(); } catch (e) { setStatus(`Lens switch failed: ${e.message || e.name}`); }
});

els.cam.addEventListener('change', savePrefs);
els.audio.addEventListener('change', savePrefs);

els.dim.addEventListener('click', () => setBlackout(true));
els.blackout.addEventListener('click', () => setBlackout(false));

document.addEventListener('visibilitychange', () => {
  if (!live || document.visibilityState !== 'visible') return;
  requestWakeLock();
  recoverTracks();
});

init();
