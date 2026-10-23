"""Create or update OBS Browser Sources for camera slots.

Unlike the rest of the package this module imports ``obspython``, so only the
OBS entry script may import it.
"""

import obspython as obs

from .log import get_logger

log = get_logger("obs")

SOURCE_KIND = "browser_source"
OBS_ALIGN_CENTER = 0  # C macro, not exported to Python


def source_name(cam):
    return f"PeerCam {cam}"


def add_or_update(cam, url, width, height):
    """Create "PeerCam N" (or update it if it exists) and make sure it is in
    the current scene (the preview scene in Studio Mode)."""
    name = source_name(cam)
    settings = obs.obs_data_create()
    obs.obs_data_set_string(settings, "url", url)
    obs.obs_data_set_bool(settings, "is_local_file", False)
    obs.obs_data_set_int(settings, "width", width)
    obs.obs_data_set_int(settings, "height", height)
    obs.obs_data_set_bool(settings, "reroute_audio", True)        # Control audio via OBS
    obs.obs_data_set_bool(settings, "shutdown", False)            # keep running when hidden
    obs.obs_data_set_bool(settings, "restart_when_active", False)

    source = obs.obs_get_source_by_name(name)
    try:
        if source is not None:
            if obs.obs_source_get_unversioned_id(source) != SOURCE_KIND:
                log.error("A source named %r exists but isn't a Browser Source", name)
                return
            obs.obs_source_update(source, settings)
            action = "Updated"
        else:
            source = obs.obs_source_create(SOURCE_KIND, name, settings, None)
            action = "Created"
        scene_name = _ensure_in_scene(source)
    finally:
        obs.obs_data_release(settings)
        if source is not None:
            obs.obs_source_release(source)

    where = f", added to scene {scene_name!r}" if scene_name else ""
    log.info("%s %r (%dx%d)%s", action, name, width, height, where)


def _current_scene_source():
    if obs.obs_frontend_preview_program_mode_active():
        return obs.obs_frontend_get_current_preview_scene()
    return obs.obs_frontend_get_current_scene()


def _ensure_in_scene(source):
    """Add ``source`` to the current scene unless it's already there.
    Returns the scene name if it was added."""
    scene_source = _current_scene_source()
    if scene_source is None:
        return None
    try:
        scene = obs.obs_scene_from_source(scene_source)
        if obs.obs_scene_find_source(scene, obs.obs_source_get_name(source)) is not None:
            return None
        item = obs.obs_scene_add(scene, source)
        _fit_to_canvas(item)
        return obs.obs_source_get_name(scene_source)
    finally:
        obs.obs_source_release(scene_source)


def _fit_to_canvas(item):
    video = obs.obs_video_info()
    if not obs.obs_get_video_info(video):
        return
    bounds = obs.vec2()
    bounds.x = video.base_width
    bounds.y = video.base_height
    obs.obs_sceneitem_set_bounds_type(item, obs.OBS_BOUNDS_SCALE_INNER)
    obs.obs_sceneitem_set_bounds_alignment(item, OBS_ALIGN_CENTER)
    obs.obs_sceneitem_set_bounds(item, bounds)
