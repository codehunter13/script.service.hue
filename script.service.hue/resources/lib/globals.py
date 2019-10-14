# -*- coding: utf-8 -*-
import functools
import time
from collections import deque
from logging import getLogger

import xbmc
import xbmcaddon

NUM_GROUPS = 2  # group0= video, group1=audio
STRDEBUG = False  # Show string ID in UI
DEBUG = False  # Enable python remote debug
REMOTE_DBG_SUSPEND = False  # Auto suspend thread when debugger attached
QHUE_TIMEOUT = 0.5  # passed to requests, in seconds.

ADDON = xbmcaddon.Addon()
ADDONID = ADDON.getAddonInfo('id')
ADDONDIR = xbmc.translatePath(ADDON.getAddonInfo('profile'))  # .decode('utf-8'))
ADDONVERSION = ADDON.getAddonInfo('version')
KODIVERSION = xbmc.getInfoLabel('System.BuildVersion')
logger = getLogger(ADDONID)

settings_changed = False
connected = False
daylight = False
force_on_sunset = False
daylight_disable = False
separate_log_file = False
initial_flash = False
reload_flash = False
enable_schedule = False
ambi_enabled = False
disable_connection_message = False
start_time = None
end_time = None

video_minimum_duration = 0
video_enable_movie = True
video_enable_episode = True
video_enable_music_video = True
video_enable_other = True

lastMediaType = 0

process_times = deque(maxlen=200)
average_process_time = 0


def timer(func):
    """Logs the runtime of the decorated function"""

    @functools.wraps(func)
    def wrapper_timer(*args, **kwargs):
        start_time = time.time()  # 1
        value = func(*args, **kwargs)
        end_time = time.time()  # 2
        run_time = end_time - start_time  # 3
        process_times.append(run_time)
        # logger.debug("[{}] Completed in {:02.0f}ms".format(func.__name__, run_time * 1000))
        return value

    return wrapper_timer
