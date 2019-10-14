# -*- coding: utf-8 -*-
import logging

from resources.lib import core
from resources.lib import globals
from resources.lib import kodilogging

kodilogging.config()
logger = logging.getLogger(globals.ADDONID)

logger.info("**** Starting default.py, version {}, Kodi: {}".format(globals.ADDONVERSION, globals.KODIVERSION))
try:
    core.menu()  # Run menu
except Exception:
    logger.exception("Core menu exception")
logger.info("**** Shutting down default.py, version {}, Kodi: {}".format(globals.ADDONVERSION, globals.KODIVERSION))
