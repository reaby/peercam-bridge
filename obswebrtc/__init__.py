"""OBS WebRTC package. Modules here must not import ``obspython`` so they can
also run standalone (``python -m obswebrtc``) for development. The one
exception is ``obs_sources``, which only the OBS entry script imports."""

__version__ = "0.1.0"
