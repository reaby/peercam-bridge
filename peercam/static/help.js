const $ = (id) => document.getElementById(id);
const dialog = $('qr-dialog');
let info = null;

async function copy(text, button) {
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    const ta = Object.assign(document.createElement('textarea'), { value: text });
    document.body.append(ta);
    ta.select();
    document.execCommand('copy');
    ta.remove();
  }
  const label = button.textContent;
  button.textContent = 'Copied';
  setTimeout(() => { button.textContent = label; }, 1200);
}

function fill(key, value) {
  for (const el of document.querySelectorAll(`[data-fill="${key}"]`)) el.textContent = value;
}

function render() {
  fill('maxCameras', info.maxCameras);
  fill('localPort', new URL(info.localUrl).port);
  fill('httpsPort', info.httpsPort ?? 'off');
  fill('buffer', info.bufferMs > 0 ? `${info.bufferMs} ms` : 'adaptive');

  for (const el of document.querySelectorAll('[data-self-signed]')) el.hidden = info.customCert;
  for (const el of document.querySelectorAll('[data-custom-cert]')) el.hidden = !info.customCert;

  const hosts = info.phoneUrls.map((u) => new URL(u).hostname);
  $('mkcert-cmd').textContent =
    `mkcert -cert-file certs/lan.pem -key-file certs/lan-key.pem ${[...hosts, 'localhost'].join(' ')}`;

  const table = $('viewer-table');
  info.viewerUrls.forEach((url, i) => {
    const row = table.insertRow();
    row.dataset.cam = i + 1;
    row.insertCell().innerHTML = `<span class="dot"></span>Cam ${i + 1}`;
    row.insertCell().innerHTML = `<code></code>`;
    row.cells[1].firstChild.textContent = url;
    const btn = Object.assign(document.createElement('button'), { className: 'small', textContent: 'Copy' });
    btn.addEventListener('click', () => copy(url, btn));
    row.insertCell().append(btn);
  });

  const select = $('qr-select');
  info.phoneUrls.forEach((url, i) => {
    const host = new URL(url).hostname;
    select.add(new Option(i === 0 ? `${host} (recommended)` : `${host} (other adapter)`, i));
  });
  const hasUrls = info.phoneUrls.length > 0;
  $('qr-body').hidden = !hasUrls;
  $('qr-none').hidden = hasUrls;
  $('qr-multi').hidden = info.phoneUrls.length < 2;
  showQr(0);
}

function showQr(index) {
  const url = info?.phoneUrls[index];
  if (!url) return;
  $('qr-img').src = `/api/qr/${index}`;
  $('qr-url').textContent = url;
}

async function refreshLive() {
  try {
    const cfg = await (await fetch('/api/config')).json();
    for (const row of $('viewer-table').querySelectorAll('tr[data-cam]')) {
      row.querySelector('.dot').classList.toggle('live', cfg.activeCams.includes(Number(row.dataset.cam)));
    }
    $('live-pill').textContent = `${cfg.activeCams.length} / ${cfg.maxCameras} cameras live`;
    if (info && cfg.bufferMs !== info.bufferMs) {
      info.bufferMs = cfg.bufferMs;
      fill('buffer', cfg.bufferMs > 0 ? `${cfg.bufferMs} ms` : 'adaptive');
    }
  } catch {
    $('live-pill').textContent = 'server offline';
  }
}

$('show-qr').addEventListener('click', () => dialog.showModal());
$('close-qr').addEventListener('click', () => dialog.close());
dialog.addEventListener('click', (e) => { if (e.target === dialog) dialog.close(); });
$('qr-select').addEventListener('change', (e) => showQr(Number(e.target.value)));
$('copy-qr').addEventListener('click', (e) => copy($('qr-url').textContent, e.target));

info = await (await fetch('/api/info')).json();
render();
refreshLive();
setInterval(refreshLive, 3000);
if (location.hash === '#qr') dialog.showModal();
