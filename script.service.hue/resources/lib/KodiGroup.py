# -*- coding: utf-8 -*-
import datetime

import resources.lib.kodiHue
import xbmc

from resources.lib import globals
from resources.lib.globals import logger
from resources.lib.qhue import QhueException

STATE_STOPPED = 0
STATE_PLAYING = 1
STATE_PAUSED = 2

VIDEO = 1
AUDIO = 2
ALLMEDIA = 3


class KodiGroup(xbmc.Player):
    def __init__(self):
        # super(xbmc.Player, self).__init__()
        super().__init__()

    def load_settings(self):
        logger.debug("KodiGroup Load settings")
        self.enabled = globals.ADDON.getSettingBool("group{}_enabled".format(self.kgroup_id))

        self.start_behavior = globals.ADDON.getSettingBool("group{}_start_behavior".format(self.kgroup_id))
        self.start_scene = globals.ADDON.getSettingString("group{}_start_scene_id".format(self.kgroup_id))

        self.pause_behavior = globals.ADDON.getSettingBool("group{}_pause_behavior".format(self.kgroup_id))
        self.pause_scene = globals.ADDON.getSettingString("group{}_pause_scene_id".format(self.kgroup_id))

        self.stop_behavior = globals.ADDON.getSettingBool("group{}_stop_behavior".format(self.kgroup_id))
        self.stop_scene = globals.ADDON.getSettingString("group{}_stop_scene_id".format(self.kgroup_id))

    def setup(self, bridge, kgroup_id, flash=False, media_type=VIDEO):
        if not hasattr(self, "state"):
            self.state = STATE_STOPPED
        self.bridge = bridge
        self.mediaType = media_type

        self.lights = bridge.lights
        self.kgroup_id = kgroup_id

        self.load_settings()

        self.groupResource = bridge.groups[0]

        if flash:
            self.flash()

    def flash(self):
        logger.debug("in KodiGroup Flash")
        try:
            self.groupResource.action(alert="select")
        except QhueException() as e:
            logger.error("Hue Error: {}".format(e))

    def onAVStarted(self):
        logger.info(
            "In KodiGroup[{}], onPlaybackStarted. Group enabled: {},start_behavior: {} , isPlayingVideo: {}, isPlayingAudio: {}, self.media_type: {},self.playback_type(): {}".format(
                self.kgroup_id, self.enabled, self.start_behavior, self.isPlayingVideo(), self.isPlayingAudio(),
                self.mediaType, self.playback_type()))
        self.state = STATE_PLAYING
        globals.lastMediaType = self.playback_type()

        if self.isPlayingVideo() and self.mediaType == VIDEO:  # If video group, check video activation. Otherwise it's audio so ignore this and check other conditions.
            try:
                self.videoInfoTag = self.getVideoInfoTag()
            except Exception as e:
                logger.debug("Get InfoTag Exception: {}".format(e))
                return
            logger.debug("InfoTag: {}".format(self.videoInfoTag))
            if not self.check_video_activation(self.videoInfoTag):
                return
        else:
            self.videoInfoTag = None

        if self.enabled and self.check_active_time() and self.start_behavior and self.mediaType == self.playback_type():
            try:
                self.groupResource.action(scene=self.start_scene)
            except QhueException as e:
                logger.error("onAVStarted: Hue call fail: {}".format(e))

    def onPlayBackStopped(self):
        logger.info("In KodiGroup[{}], onPlaybackStopped() , media_type: {}, lastMediaType: {} ".format(self.kgroup_id,
                                                                                                        self.mediaType,
                                                                                                        globals.lastMediaType))
        self.state = STATE_STOPPED

        try:
            if self.mediaType == VIDEO and not self.check_video_activation(
                    self.videoInfoTag):  # If video group, check video activation. Otherwise it's audio so ignore this and check other conditions.
                return
        except AttributeError:
            logger.error("No videoInfoTag")

        if self.enabled and self.check_active_time() and self.stop_behavior and self.mediaType == globals.lastMediaType:
            try:
                xbmc.sleep(100)  # sleep for any left over ambilight calls to complete first.
                self.groupResource.action(scene=self.stop_scene)
                logger.info("In KodiGroup[{}], onPlaybackStop() Stop scene activated")
            except QhueException as e:
                logger.error("onPlaybackStopped: Hue call fail: {}".format(e))

    def onPlayBackPaused(self):
        logger.info(
            "In KodiGroup[{}], onPlaybackPaused() , isPlayingVideo: {}, isPlayingAudio: {}".format(self.kgroup_id,
                                                                                                   self.isPlayingVideo(),
                                                                                                   self.isPlayingAudio()))
        self.state = STATE_PAUSED

        if self.mediaType == VIDEO and not self.check_video_activation(
                self.videoInfoTag):  # If video group, check video activation. Otherwise it's audio so we ignore this and continue
            return

        if self.enabled and self.check_active_time() and self.pause_behavior and self.mediaType == self.playback_type():
            self.lastMediaType = self.playback_type()
            try:
                xbmc.sleep(500)  # sleep for any left over ambilight calls to complete first.
                self.groupResource.action(scene=self.pause_scene)
                logger.info("In KodiGroup[{}], onPlaybackPaused() Pause scene activated")
            except QhueException as e:
                logger.error("onPlaybackStopped: Hue call fail: {}".format(e))

    def onPlayBackResumed(self):
        logger.info("In KodiGroup[{}], onPlaybackResumed()".format(self.kgroup_id))
        self.onAVStarted()

    def onPlayBackError(self):
        logger.info("In KodiGroup[{}], onPlaybackError()".format(self.kgroup_id))
        self.onPlayBackStopped()

    def onPlayBackEnded(self):
        logger.info("In KodiGroup[{}], onPlaybackEnded()".format(self.kgroup_id))
        self.onPlayBackStopped()

    def sunset(self):
        logger.info("In KodiGroup[{}], in sunset()".format(self.kgroup_id))

        if self.state == STATE_PLAYING:  # if Kodi is playing any file, start up
            self.onAVStarted()
        elif self.state == STATE_PAUSED:
            self.onPlayBackPaused()
        else:
            # if not playing and sunset happens, probably should do nothing.
            logger.debug("In KodiGroup[{}], in sunset(). playback stopped, doing nothing. ".format(self.kgroup_id))

    def playback_type(self):
        if self.isPlayingVideo():
            media_type = VIDEO
        elif self.isPlayingAudio():
            media_type = AUDIO
        else:
            media_type = None
        return media_type

    def check_active_time(self):
        logger.debug(
            "Schedule: {}, daylightDiable: {}, daylight: {}, start_time: {}, end_time: {}".format(
                globals.enable_schedule,
                globals.daylight_disable,
                globals.daylight,
                globals.start_time,
                globals.end_time))

        if globals.daylight_disable and globals.daylight:
            logger.debug("Disabled by daylight")
            return False

        if globals.enable_schedule:
            start = kodiHue.convertTime(globals.start_time)
            end = kodiHue.convertTime(globals.end_time)
            now = datetime.datetime.now().time()
            if (now > start) and (now < end):
                logger.debug("Enabled by schedule")
                return True
            logger.debug("Disabled by schedule")
            return False
        logger.debug("Schedule not enabled")
        return True

    def check_video_activation(self, info_tag):
        logger.debug("InfoTag: {}".format(info_tag))
        try:
            duration = info_tag.getDuration() / 60  # returns seconds, convert to minutes
            media_type = info_tag.getMediaType()
            file_name = info_tag.getFile()
            logger.debug(
                "InfoTag contents: duration: {}, media_type: {}, file: {}".format(duration, media_type, file_name))
        except AttributeError:
            logger.exception("Can't read info_tag")
            return False
        logger.debug(
            "Video Activation settings({}): minDuration: {}, Movie: {}, Episode: {}, MusicVideo: {}, Other: {}".
                format(self.kgroup_id, globals.video_minimum_duration, globals.video_enable_movie,
                       globals.video_enable_episode,
                       globals.video_enable_music_video, globals.video_enable_other))
        logger.debug("Video Activation ({}): Duration: {}, media_type: {}".format(self.kgroup_id, duration, media_type))
        if duration > globals.video_minimum_duration and ((globals.video_enable_movie and media_type == "movie") or (
                globals.video_enable_episode and media_type == "episode") or (
                                                                  globals.video_enable_music_video and media_type == "MusicVideo")) or globals.video_enable_other:
            logger.debug("Video activation: True")
            return True
        logger.debug("Video activation: False")
        return False
