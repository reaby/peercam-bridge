# OBS WebRTC

Use phones and tablets as wireless cameras in OBS Studio, over your local network.
No app to install on the phone: open a web page, pick a camera slot, press Start.

- Up to 8 camera slots, each one a Browser Source in OBS
- Phone page: camera slot, back/front lens, bitrate, audio on/off, keeps the screen awake,
  dim mode, reconnects by itself
- Low latency: video goes straight from the phone to OBS (WebRTC), not through a cloud service
- Stable buffer option, so every camera has the same steady delay and one audio sync offset fits all
- One-click "Add camera to scene" in the script settings
- Built-in help page with a QR code for phones
- Works with the [Source Record](https://obsproject.com/forum/resources/source-record.1285/) plugin
  to record each camera to its own file

```
 Phone (browser)  ── WebRTC video/audio ──▶  OBS Browser Source
        │                                         │
        └──── signaling ──▶  this script  ◀───────┘
                    (small web server inside OBS)
```

## Requirements

- **OBS Studio 28 or newer**, 64-bit (30+ recommended)
- **Python 3.12, 64-bit** (the version this is tested with). The Python you use for the
  script must be the same version that OBS loads.
- Phones/tablets with a current browser: Chrome on Android, Safari on iPhone/iPad
- Phones and the OBS computer on the **same network** (Wi-Fi or Ethernet)

## Installation

### 1. Get the files

```
git clone https://github.com/reaby/obs-webrtc.git
```

Or download the ZIP from GitHub and extract it. Keep the folder somewhere permanent, because
OBS loads the script from there.

### 2. Install Python

**Windows:** install 64-bit Python 3.12 from [python.org](https://www.python.org/downloads/).
The default install location is fine.

**macOS:** install Python 3.12 from [python.org](https://www.python.org/downloads/macos/)
(OBS needs the python.org build, not Homebrew's).

**Linux:** OBS uses the system Python, so use your distribution's `python3` and make sure the
venv module is installed (`sudo apt install python3-venv` on Debian/Ubuntu). The Flatpak
version of OBS uses its own Python and isn't supported by these instructions.

### 3. Create the virtual environment

The script keeps its Python packages in a `.venv` folder next to it, so nothing is installed
into your system Python.

**Windows:** double-click `setup.bat`, or run it from a terminal:

```bat
setup.bat
```

It uses Python 3.12 through the `py` launcher if available, otherwise `python`. To choose a
specific Python, pass its path: `setup.bat C:\Python312\python.exe`

**Linux / macOS:**

```sh
./setup.sh
```

It uses `python3`. To choose a specific Python, pass its path: `./setup.sh /usr/bin/python3.12`

When the script finishes, it prints the Python folder to use in the next step.

<details>
<summary>Manual setup (without the scripts)</summary>

Run these in the obs-webrtc folder, using the **same Python version as OBS**.

Windows:

```bat
C:\Python312\python.exe -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Linux / macOS:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
```

To find a Python's install folder for OBS: `python -c "import sys; print(sys.base_prefix)"`

</details>

### 4. Point OBS at Python (Windows and macOS)

1. In OBS: **Tools → Scripts → Python Settings**.
2. Set the **Python install path** to your Python folder, e.g. `C:\Python312` on Windows
   (`setup.bat` prints it).
3. It should say "Loaded Python version: 3.12". Restart OBS if it asks.

On Linux, OBS already uses the system Python; skip this step.

### 5. Add the script

1. **Tools → Scripts → Scripts** tab → **+** → choose `obs_webrtc.py`.
2. The script starts its server right away. The settings panel shows the
   **Phones connect address**.
3. **Windows Firewall:** when Windows asks, allow OBS on **Private** networks.
   Without this, phones can't connect.

## Usage

1. Press **Open help & phone QR code** in the script settings. The help page opens in your browser.
2. Press **Show phone QR code** and scan it with the phone. The first time, the phone warns
   about the certificate; accept it (the help page shows how for each browser).
3. On the phone, pick a camera slot and press **Start**.
4. In the script settings under **Browser Sources**, pick that camera and press
   **Add / update in current scene**.

The help page covers the rest: phone controls, Browser Source settings, audio sync,
recording each camera for editing, network tips and troubleshooting.

### Script settings

| Setting | Default | |
|---|---|---|
| OBS port | 8080 | Local address the Browser Sources load (`http://127.0.0.1:8080`) |
| Phone port | 8443 | HTTPS address phones open |
| Max cameras | 5 | Number of camera slots (1–8) |
| Stable buffer | 100 ms | Fixed receive buffer for steady, equal delay; 0 = browser default. Applies live |
| Camera / Source size | Cam 1 / 1920×1080 | Used by the Add buttons |

### Camera URLs

Each camera is a Browser Source at `http://127.0.0.1:8080/view?cam=N`. Options to add:

| Option | Effect |
|---|---|
| `&quiet` | Hide the "Waiting for Cam N" text |
| `&stats` | Show connection stats and delay (for setup; visible in the picture) |
| `&delay=150` | Override the stable buffer for this camera, in ms |

### Certificate

Phones only allow camera access on HTTPS pages, so the script creates a self-signed
certificate in `certs/` on first start, and each phone accepts a warning once.
To avoid the warning, create a trusted certificate with [mkcert](https://github.com/FiloSottile/mkcert)
and save it as `certs/lan.pem` and `certs/lan-key.pem`. The help page shows the exact command.

## Updating

```
git pull
```

Then run `setup.bat` / `setup.sh` again in case the requirements changed, and reload the
script in OBS (Tools → Scripts → ⟳).

## Troubleshooting

**The Script Log shows `No module named 'aiohttp'` (or similar).**
The `.venv` is missing or was made with a different Python version than OBS uses. The log
says which version OBS runs. Delete `.venv` and run the setup again with that version.

**The script doesn't appear to load, or the Python Settings tab says Python isn't loaded.**
Check the Python install path in step 4 points to a 64-bit Python of the right version.

**The settings show "Server not running".**
Usually another program is using port 8080 or 8443. Change the ports in the **Server** section.

**Phones can't open the page or stay on "Connecting…".**
Check the phone is on the same network (not guest Wi-Fi or mobile data) and that OBS is
allowed through the firewall on Private networks.

More fixes are in the help page's Troubleshooting section.

## Development

The server can run without OBS, which is handy for working on the web pages:

```
.venv\Scripts\python -m obswebrtc --port 8080 --https-port 8443 --max-cameras 5 --buffer-ms 100
```

Project layout:

```
obs_webrtc.py          OBS entry script: venv bootstrap, settings, callbacks
obswebrtc/
  server.py            aiohttp server on a background thread (HTTP for OBS, HTTPS for phones)
  rooms.py             camera-slot signaling
  obs_sources.py       creates/updates Browser Sources (the only module using the OBS API)
  certs.py             self-signed certificate
  netinfo.py, qr.py, log.py
  static/              sender, viewer and help pages
setup.bat, setup.sh    create .venv and install requirements.txt
```

## License

[MIT](LICENSE)
