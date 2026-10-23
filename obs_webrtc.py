"""OBS WebRTC - entry script loaded by OBS (Tools > Scripts).

Keep this file thin: it bootstraps the local venv, wires OBS callbacks and
delegates everything else to the ``obswebrtc`` package.
"""

import os
import site
import sys
import webbrowser

_HERE = os.path.dirname(os.path.abspath(__file__))
_VENV_SITE = os.path.join(_HERE, ".venv", "Lib", "site-packages")

if os.path.isdir(_VENV_SITE):
    site.addsitedir(_VENV_SITE)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

# Drop cached package modules so "Reload Scripts" in OBS picks up code changes.
for _name in [m for m in sys.modules if m == "obswebrtc" or m.startswith("obswebrtc.")]:
    del sys.modules[_name]

import obspython as obs  # noqa: E402

from obswebrtc.log import get_logger, setup_logging  # noqa: E402
from obswebrtc.server import SignalingServer  # noqa: E402

setup_logging()
log = get_logger()

DEFAULT_PORT = 8080
DEFAULT_HTTPS_PORT = 8443
DEFAULT_MAX_CAMERAS = 5
DEFAULT_BUFFER_MS = 100

_server = None
_config = None  # (enabled, port, phones, https_port, max_cameras) currently applied


def _apply(enabled, port, phones, https_port, max_cameras, buffer_ms):
    global _server, _config
    config = (enabled, port, phones, https_port, max_cameras)
    if _config == config:
        # The buffer can change live; everything else needs a restart.
        if _server is not None:
            _server.set_buffer_ms(buffer_ms)
        return
    _config = config

    if _server is not None:
        _server.stop()
        _server = None

    if not enabled:
        return

    server = SignalingServer(port, max_cameras, https_port=https_port if phones else None,
                             buffer_ms=buffer_ms)
    try:
        server.start()
    except Exception as e:
        log.error("Failed to start server (ports %s/%s): %s", port, https_port, e)
        return
    _server = server


def _open_help_page(props, prop):
    if _server is not None:
        webbrowser.open(f"{_server.local_url}/help")
    return False


# --- OBS callbacks -----------------------------------------------------------

def script_description():
    return (
        "<b>OBS WebRTC</b><br>"
        "Phones and tablets as WebRTC cameras.<br>"
        f"Python {sys.version.split()[0]}"
    )


def script_defaults(settings):
    obs.obs_data_set_default_bool(settings, "enabled", True)
    obs.obs_data_set_default_int(settings, "port", DEFAULT_PORT)
    obs.obs_data_set_default_bool(settings, "phones", True)
    obs.obs_data_set_default_int(settings, "https_port", DEFAULT_HTTPS_PORT)
    obs.obs_data_set_default_int(settings, "max_cameras", DEFAULT_MAX_CAMERAS)
    obs.obs_data_set_default_int(settings, "buffer_ms", DEFAULT_BUFFER_MS)


def script_properties():
    props = obs.obs_properties_create()
    obs.obs_properties_add_bool(props, "enabled", "Enable server")
    obs.obs_properties_add_int(props, "port", "OBS port (localhost)", 1, 65535, 1)
    obs.obs_properties_add_bool(props, "phones", "Allow phones (HTTPS on LAN)")
    obs.obs_properties_add_int(props, "https_port", "Phone port (HTTPS)", 1, 65535, 1)
    obs.obs_properties_add_int(props, "max_cameras", "Max cameras", 1, 8, 1)
    buffer = obs.obs_properties_add_int(props, "buffer_ms", "Stable buffer (ms)", 0, 1000, 10)
    obs.obs_property_set_long_description(
        buffer, "Fixed receive buffer for all cameras so their delay stays constant and equal. "
                "0 = browser default (adaptive, lower but drifting delay).")

    if _server is None:
        status = "Server not running"
    elif _server.phone_urls:
        status = f"Phones: {_server.phone_urls[0]}"
    else:
        status = "Phones: off"
    obs.obs_properties_add_text(props, "status", status, obs.OBS_TEXT_INFO)
    obs.obs_properties_add_button(props, "connect", "Open help && phone QR code", _open_help_page)
    return props


def script_update(settings):
    _apply(
        obs.obs_data_get_bool(settings, "enabled"),
        obs.obs_data_get_int(settings, "port"),
        obs.obs_data_get_bool(settings, "phones"),
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
