# -*- coding: utf-8 -*-
from threading import Thread, Event

import xbmc
from PIL import Image

from resources.lib import kodiHue
from . import ImageProcess
from . import KodiGroup
from . import globals
from .KodiGroup import VIDEO, STATE_STOPPED, STATE_PAUSED, STATE_PLAYING
from .globals import logger
from .qhue import QhueException
from .rgbxy import Converter, ColorHelper  # https://github.com/benknight/hue-python-rgb-converter
from .rgbxy import GamutA, GamutB, GamutC


class AmbiGroup(KodiGroup.KodiGroup):
    def onAVStarted(self):
        logger.info(
            "Ambilight AV Started. Group enabled: {} , isPlayingVideo: {}, isPlayingAudio: {}, self.media_type: {},self.playback_type(): {}".format(
                self.enabled, self.isPlayingVideo(), self.isPlayingAudio(), self.mediaType, self.playback_type()))
        logger.info(
            "Ambilight Settings: Interval: {}, transition_time: {}".format(self.update_interval, self.transition_time))
        # logger.info("Ambilight Settings: force_on: {}, setBrightness: {}, Brightness: {}, MinimumDistance: {}".format(self.force_on,self.setBrightness,self.brightness,self.minimumDistance))
        self.state = STATE_PLAYING

        if self.isPlayingVideo():
            self.videoInfoTag = self.getVideoInfoTag()
            if self.enabled and self.check_active_time() and self.check_video_activation(self.videoInfoTag):

                if self.force_on:
                    for L in self.ambi_lights:
                        try:
                            self.bridge.lights[L].state(on=True)
                        except QhueException as e:
                            logger.debug("Ambi: Initial Hue call fail: {}".format(e))

                self.ambi_running.set()
                ambi_loop_thread = Thread(target=self._ambi_loop, name="_ambi_Loop")
                ambi_loop_thread.daemon = True
                ambi_loop_thread.start()

    def onPlayBackStopped(self):
        logger.info("In ambi_group[{}], onPlaybackStopped()".format(self.kgroup_id))
        self.state = STATE_STOPPED
        self.ambi_running.clear()

    def onPlayBackPaused(self):
        logger.info("In ambi_group[{}], onPlaybackPaused()".format(self.kgroup_id))
        self.state = STATE_PAUSED
        self.ambi_running.clear()

    def load_settings(self):
        logger.debug("AmbiGroup Load settings")

        self.enabled = globals.ADDON.getSettingBool("group{}_enabled".format(self.kgroup_id))

        self.transition_time = globals.ADDON.getSettingInt("group{}_transition_time".format(
            self.kgroup_id)) / 100  # This is given as a multiple of 100ms and defaults to 4 (400ms). For example, setting transitiontime:10 will make the transition last 1 second.
        self.force_on = globals.ADDON.getSettingBool("group{}_force_on".format(self.kgroup_id))

        self.min_bri = globals.ADDON.getSettingInt(
            "group{}_min_brightness".format(self.kgroup_id)) * 255 / 100  # convert percentage to value 1-254
        self.max_bri = globals.ADDON.getSettingInt(
            "group{}_max_brightness".format(self.kgroup_id)) * 255 / 100  # convert percentage to value 1-254

        self.saturation = globals.ADDON.getSettingNumber("group{}_saturation".format(self.kgroup_id))

        self.capture_size = globals.ADDON.getSettingInt("group{}_capture_size".format(self.kgroup_id))

        self.update_interval = globals.ADDON.getSettingInt(
            "group{}_interval".format(self.kgroup_id)) / 1000  # convert MS to seconds
        if self.update_interval == 0:
            self.update_interval = 0.002

        self.ambi_lights = {}
        light_ids = globals.ADDON.getSetting("group{}_Lights".format(self.kgroup_id)).split(",")
        index = 0
        for L in light_ids:
            gamut = kodiHue.get_light_gamut(self.bridge, L)
            light = {L: {'gamut': gamut, 'prevxy': (0, 0), "index": index}}
            self.ambi_lights.update(light)
            index = index + 1

    def setup(self, monitor, bridge, kgroup_id, flash=False):
        try:
            self.ambi_running
        except AttributeError:
            self.ambi_running = Event()

        super(AmbiGroup, self).setup(bridge, kgroup_id, flash, VIDEO)
        self.monitor = monitor

        self.imageProcess = ImageProcess.ImageProcess()

        self.converterA = Converter(GamutA)
        self.converterB = Converter(GamutB)
        self.converterC = Converter(GamutC)
        self.helper = ColorHelper(GamutC)

    def _ambi_loop(self):

        cap = xbmc.RenderCapture()
        logger.debug("_ambiLoop started")

        aspect_ratio = cap.getAspectRatio()

        self.captureSizeY = int(self.capture_size / aspect_ratio)
        expected_capture_size = self.capture_size * self.captureSizeY * 4  # size * 4 bytes I guess
        logger.debug(
            "aspect_ratio: {}, CaptureSize: ({},{}), expected_capture_size: {}".format(aspect_ratio, self.capture_size,
                                                                                       self.captureSizeY,
                                                                                       expected_capture_size))

        for L in self.ambi_lights:
            self.ambi_lights[L].update(prevxy=(0.0001, 0.0001))

        try:
            while not self.monitor.abortRequested() and self.ambi_running.is_set():  # loop until kodi tells add-on to stop or video playing flag is unset.
                try:
                    cap.capture(self.capture_size, self.captureSizeY)  # async capture request to underlying OS
                    cap_image = cap.getImage()  # timeout to wait for OS in ms, default 1000
                    # logger.debug("CapSize: {}".format(len(cap_image)))
                    if cap_image is None or len(cap_image) < expected_capture_size:
                        logger.error("cap_image is none or < expected: {}, expected: {}".format(len(cap_image),
                                                                                                expected_capture_size))
                        self.monitor.waitForAbort(0.25)  # pause before trying again
                        continue  # no image captured, try again next iteration
                    image = Image.frombuffer("RGBA", (self.capture_size, self.captureSizeY), buffer(cap_image), "raw",
                                             "BGRA")
                except ValueError:
                    logger.error("cap_image: {}".format(len(cap_image)))
                    logger.exception("Value Error")
                    self.monitor.waitForAbort(0.25)
                    continue  # returned capture is  smaller than expected when player stopping. give up this loop.
                except Exception as ex:
                    logger.warning("Capture exception", exc_info=1)
                    self.monitor.waitForAbort(0.25)
                    continue

                colors = self.imageProcess.img_avg(image, self.min_bri, self.max_bri, self.saturation)
                for L in self.ambi_lights:
                    x = Thread(target=self._update_hue_rgb, name="updateHue", args=(
                        colors['rgb'][0], colors['rgb'][1], colors['rgb'][2], L, self.transition_time, colors['bri']))
                    x.daemon = True
                    x.start()
                self.monitor.waitForAbort(self.update_interval)  # seconds
            average_process_time = kodiHue.perf_average(globals.process_times)
            logger.info("Average process time: {}".format(average_process_time))
            self.capture_size = globals.ADDON.setSettingString("average_process_time",
                                                               "{}".format(average_process_time))

        except Exception as ex:
            logger.exception("Exception in _ambiLoop")
        logger.debug("_ambiLoop stopped")

    def _update_hue_rgb(self, r, g, b, light, transition_time, bri):
        gamut = self.ambi_lights[light].get('gamut')
        prevxy = self.ambi_lights[light].get('prevxy')

        if gamut == "A":
            converter = self.converterA
        elif gamut == "B":
            converter = self.converterB
        elif gamut == "C":
            converter = self.converterC

        xy = converter.rgb_to_xy(r, g, b)
        xy = round(xy[0], 3), round(xy[1],
                                    3)  # Hue has a max precision of 4 decimal points, but three is plenty, lower is not noticable.

        try:
            self.bridge.lights[light].state(xy=xy, bri=bri, transitiontime=transition_time)
            self.ambi_lights[light].update(prevxy=xy)
        except QhueException as ex:
            logger.warn(ex)
        except KeyError:
            logger.exception("Ambi: KeyError")

    def _update_hue_xy(self, xy, light, transition_time):
        prevxy = self.ambi_lights[light].get('prevxy')

        # xy=(round(xy[0],3),round(xy[1],3)) #Hue has a max precision of 4 decimal points.

        # distance=self.helper.get_distance_between_two_points(XYPoint(xy[0],xy[1]),XYPoint(prevxy[0],prevxy[1]))#only update hue if XY changed enough
        # if distance > self.minimumDistance:
        try:
            self.bridge.lights[light].state(xy=xy, transitiontime=transition_time)
            self.ambi_lights[light].update(prevxy=xy)
        except QhueException as ex:
            logger.warn(ex)
        except KeyError:
            logger.exception("Ambi: KeyError")
