"""PeerCam Bridge - entry script loaded by OBS (Tools > Scripts).

Keep this file thin: it bootstraps the local venv, wires OBS callbacks and
delegates everything else to the ``peercam`` package.
"""

import os
import site
import sys
import webbrowser

_HERE = os.path.dirname(os.path.abspath(__file__))
_VENV = os.path.join(_HERE, ".venv")
_PY_VERSION = f"{sys.version_info.major}.{sys.version_info.minor}"

if os.name == "nt":
    _VENV_SITE = os.path.join(_VENV, "Lib", "site-packages")
else:
    _VENV_SITE = os.path.join(_VENV, "lib", f"python{_PY_VERSION}", "site-packages")


def _venv_python_version():
    try:
        with open(os.path.join(_VENV, "pyvenv.cfg"), encoding="utf-8") as f:
            for line in f:
                key, _, value = line.partition("=")
                if key.strip() in ("version", "version_info"):
                    return ".".join(value.strip().split(".")[:2])
    except OSError:
        pass
    return None


_venv_version = _venv_python_version()
if _venv_version and _venv_version != _PY_VERSION:
    print(f"[peercam] WARNING: .venv was made with Python {_venv_version} but OBS runs "
          f"Python {_PY_VERSION}. Recreate it with the same Python OBS uses (see README).")
if os.path.isdir(_VENV_SITE):
    site.addsitedir(_VENV_SITE)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

# Drop cached package modules so "Reload Scripts" in OBS picks up code changes.
for _name in [m for m in sys.modules if m == "peercam" or m.startswith("peercam.")]:
    del sys.modules[_name]

import obspython as obs  # noqa: E402

try:
    from peercam import __version__, obs_sources  # noqa: E402
    from peercam.log import get_logger, setup_logging  # noqa: E402
    from peercam.server import SignalingServer  # noqa: E402
except ImportError as e:
    print(f"[peercam] ERROR: {e}. Run setup.bat (Windows) or setup.sh (Linux/macOS) "
          f"in {_HERE} with Python {_PY_VERSION}, then reload the script.")
    raise

setup_logging()
log = get_logger()

DEFAULT_PORT = 8080
DEFAULT_HTTPS_PORT = 8443
DEFAULT_MAX_CAMERAS = 5
DEFAULT_BUFFER_MS = 100
SOURCE_SIZES = [
    ("1920×1080 (landscape)", "1920x1080"),
    ("1280×720", "1280x720"),
    ("1080×1920 (portrait)", "1080x1920"),
]

_server = None
_server_error = None
_config = None  # (port, https_port, max_cameras) currently applied
_source_cam = 1
_source_size = SOURCE_SIZES[0][1]


def _apply(port, https_port, max_cameras, buffer_ms):
    global _server, _server_error, _config
    config = (port, https_port, max_cameras)
    if _config == config:
        # The buffer can change live; everything else needs a restart.
        if _server is not None:
            _server.set_buffer_ms(buffer_ms)
        return
    _config = config

    if _server is not None:
        _server.stop()
        _server = None

    server = SignalingServer(port, max_cameras, https_port=https_port, buffer_ms=buffer_ms)
    try:
        server.start()
    except Exception as e:
        _server_error = str(e)
        log.error("Failed to start server (ports %s/%s): %s", port, https_port, e)
        return
    _server_error = None
    _server = server


def _open_help_page(props, prop):
    if _server is not None:
        webbrowser.open(f"{_server.local_url}/help")
    return False


def _add_sources(cams):
    if _server is None:
        log.warning("Server isn't running, can't add sources (see errors above)")
        return
    width, height = (int(v) for v in _source_size.split("x"))
    for cam in cams:
        obs_sources.add_or_update(cam, f"{_server.local_url}/view?cam={cam}", width, height)


def _add_selected_source(props, prop):
    _add_sources([_source_cam])
    return False


def _add_all_sources(props, prop):
    if _server is not None:
        _add_sources(range(1, _server.max_cameras + 1))
    return False


def _fill_cam_list(prop, max_cameras):
    obs.obs_property_list_clear(prop)
    for cam in range(1, max_cameras + 1):
        obs.obs_property_list_add_int(prop, f"Cam {cam}", cam)


def _max_cameras_changed(props, prop, settings):
    _fill_cam_list(obs.obs_properties_get(props, "source_cam"),
                   obs.obs_data_get_int(settings, "max_cameras"))
    return True


# --- OBS callbacks -----------------------------------------------------------

def script_description():
    return (
        '<h2 style="margin-bottom:2px">PeerCam Bridge</h2>'
        "<p>Phones and tablets as wireless cameras, over your local network.</p>"
        '<table cellspacing="0" cellpadding="1">'
        "<tr><td><b>1.</b>&nbsp;</td><td>Open the help page and scan the QR code with a phone</td></tr>"
        "<tr><td><b>2.</b>&nbsp;</td><td>On the phone, pick a camera slot and press Start</td></tr>"
        "<tr><td><b>3.</b>&nbsp;</td><td>Add that camera to your scene under Browser Sources</td></tr>"
        "</table>"
        f'<p style="color:#888">v{__version__} · Python {sys.version.split()[0]}</p>'
    )


def script_defaults(settings):
    obs.obs_data_set_default_int(settings, "port", DEFAULT_PORT)
    obs.obs_data_set_default_int(settings, "https_port", DEFAULT_HTTPS_PORT)
    obs.obs_data_set_default_int(settings, "max_cameras", DEFAULT_MAX_CAMERAS)
    obs.obs_data_set_default_int(settings, "buffer_ms", DEFAULT_BUFFER_MS)
    obs.obs_data_set_default_int(settings, "source_cam", 1)
    obs.obs_data_set_default_string(settings, "source_size", SOURCE_SIZES[0][1])


def script_properties():
    props = obs.obs_properties_create()
    obs.obs_properties_add_button(props, "connect", "Open help && phone QR code", _open_help_page)

    if _server is None:
        status = f"Server not running: {_server_error or 'see Script Log'}"
    elif _server.phone_urls:
        status = f"Phones connect address:  {_server.phone_urls[0]}"
    else:
        status = "No network address found, connect this PC to the network"
    info = obs.obs_properties_add_text(props, "status", status, obs.OBS_TEXT_INFO)
    if _server is None or not _server.phone_urls:
        obs.obs_property_text_set_info_type(info, obs.OBS_TEXT_INFO_WARNING)

    server = obs.obs_properties_create()
    obs.obs_properties_add_int(server, "port", "OBS port (localhost)", 1, 65535, 1)
    obs.obs_properties_add_int(server, "https_port", "Phone port (HTTPS)", 1, 65535, 1)
    max_cams = obs.obs_properties_add_int(server, "max_cameras", "Max cameras", 1, 8, 1)
    obs.obs_property_set_modified_callback(max_cams, _max_cameras_changed)
    buffer = obs.obs_properties_add_int(server, "buffer_ms", "Stable buffer (ms)", 0, 1000, 10)
    obs.obs_property_set_long_description(
        buffer, "Fixed receive buffer for all cameras so their delay stays constant and equal. "
                "0 = browser default (adaptive, lower but drifting delay).")
    obs.obs_properties_add_group(props, "server", "Server", obs.OBS_GROUP_NORMAL, server)

    sources = obs.obs_properties_create()
    cam_list = obs.obs_properties_add_list(sources, "source_cam", "Camera",
                                           obs.OBS_COMBO_TYPE_LIST, obs.OBS_COMBO_FORMAT_INT)
    _fill_cam_list(cam_list, _server.max_cameras if _server else DEFAULT_MAX_CAMERAS)
    size_list = obs.obs_properties_add_list(sources, "source_size", "Source size",
                                            obs.OBS_COMBO_TYPE_LIST, obs.OBS_COMBO_FORMAT_STRING)
    for label, value in SOURCE_SIZES:
        obs.obs_property_list_add_string(size_list, label, value)
    obs.obs_properties_add_button(sources, "add_source", "Add / update in current scene",
                                  _add_selected_source)
    obs.obs_properties_add_button(sources, "add_all_sources", "Add all cameras", _add_all_sources)
    obs.obs_properties_add_group(props, "sources", "Browser Sources", obs.OBS_GROUP_NORMAL, sources)
    return props


def script_update(settings):
    global _source_cam, _source_size
    _source_cam = obs.obs_data_get_int(settings, "source_cam")
    _source_size = obs.obs_data_get_string(settings, "source_size") or SOURCE_SIZES[0][1]
    _apply(
        obs.obs_data_get_int(settings, "port"),
        obs.obs_data_get_int(settings, "https_port"),
        obs.obs_data_get_int(settings, "max_cameras"),
        obs.obs_data_get_int(settings, "buffer_ms"),
    )


def script_unload():
    global _server, _config
    if _server is not None:
        _server.stop()
        _server = None
    _config = None
