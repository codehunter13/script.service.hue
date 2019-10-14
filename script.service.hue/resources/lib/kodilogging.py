# -*- coding: utf-8 -*-

import logging
import os
from logging.handlers import TimedRotatingFileHandler

import xbmc

from resources.lib import globals

prefix = "[{}]".format(globals.ADDONID)
formatter = logging.Formatter(prefix + '[%(module)s][%(funcName)s](%(lineno)d): %(message)s')
fileFormatter = logging.Formatter('%(asctime)s %(levelname)s [%(module)s][%(funcName)s](%(lineno)d): %(message)s')


class KodiLogHandler(logging.StreamHandler):

    def __init__(self):
        logging.StreamHandler.__init__(self)
        self.setFormatter(formatter)

    def emit(self, record):
        levels = {
            logging.CRITICAL: xbmc.LOGFATAL,
            logging.ERROR: xbmc.LOGERROR,
            logging.WARNING: xbmc.LOGWARNING,
            logging.INFO: xbmc.LOGINFO,
            logging.DEBUG: xbmc.LOGDEBUG,
            logging.NOTSET: xbmc.LOGNONE,
        }

        xbmc.log(self.format(record), levels[record.levelno])

        # =======================================================================
        # try:
        #     xbmc.log(self.format(record), levels[record.levelno])
        # except UnicodeEncodeError:
        #     xbmc.log(self.format(record).encode(
        #         'utf-8', 'ignore'), levels[record.levelno])
        # =======================================================================

    def flush(self):
        pass


def config():
    separate_log_file = globals.ADDON.getSettingBool("separate_log_file")
    logger = logging.getLogger(globals.ADDONID)

    if separate_log_file:
        if not os.path.isdir(globals.ADDONDIR):
            # xbmc.log("Hue Service: profile directory doesn't exist: " + globals.ADDONDIR + "   Trying to create.", level=xbmc.LOGNOTICE)
            try:
                os.mkdir(globals.ADDONDIR)
                xbmc.log("Hue Service: profile directory created: " + globals.ADDONDIR, level=xbmc.LOGNOTICE)
            except OSError as e:
                xbmc.log("Hue Service: Log: can't create directory: " + globals.ADDONDIR, level=xbmc.LOGERROR)
                xbmc.log("Exception: {}".format(e.message), xbmc.LOGERROR)

        file_handler = TimedRotatingFileHandler(os.path.join(globals.ADDONDIR, 'kodiHue.log'), when="midnight",
                                                backupCount=2)
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(fileFormatter)
        logger.addHandler(file_handler)

    logger.addHandler(KodiLogHandler())
    logger.setLevel(logging.DEBUG)
