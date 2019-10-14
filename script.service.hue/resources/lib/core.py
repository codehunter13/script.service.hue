# -*- coding: utf-8 -*-

import sys
from logging import getLogger

import xbmcgui
from requests.exceptions import ConnectionError

# noinspection PyUnresolvedReferences
from resources.lib.language import get_string as _
from . import AmbiGroup
from . import globals
from . import kodiHue

logger = getLogger(globals.ADDONID)


def menu():
    monitor = kodiHue.HueMonitor()

    if len(sys.argv) > 1:
        args = sys.argv[1]
    else:
        args = ""
    logger.info("menu started, version: {}, Arguments: {}".format(globals.ADDON.getAddonInfo("version"), args))

    if args == "discover":
        logger.debug("Started with Discovery")
        bridge_discovered = kodiHue.bridge_discover(monitor)
        if bridge_discovered:
            bridge = kodiHue.connect_bridge(monitor, silent=True)
            if bridge:
                logger.debug("Found bridge. Running model check & starting service.")
                kodiHue.check_bridge_model(bridge)
                globals.ADDON.openSettings()
                service()

    elif args == "create_hue_scene":
        logger.debug("Started with {}".format(args))
        bridge = kodiHue.connect_bridge(monitor, silent=True)  # don't rediscover, proceed silently
        if bridge is not None:
            kodiHue.create_hue_scene(bridge)
        else:
            logger.debug("No bridge found. create_hue_scene cancelled.")
            xbmcgui.Dialog().notification(_("Hue Service"), _("Check Hue Bridge configuration"))

    elif args == "delete_hue_scene":
        logger.debug("Started with {}".format(args))

        bridge = kodiHue.connect_bridge(monitor, silent=True)  # don't rediscover, proceed silently
        if bridge is not None:
            kodiHue.delete_hue_scene(bridge)
        else:
            logger.debug("No bridge found. delete_hue_scene cancelled.")
            xbmcgui.Dialog().notification(_("Hue Service"), _("Check Hue Bridge configuration"))

    elif args == "sceneSelect":  # sceneSelect=kgroup,action  / sceneSelect=0,play
        kgroup = sys.argv[2]
        action = sys.argv[3]
        logger.debug("Started with {}, kgroup: {}, kaction: {}".format(args, kgroup, action))

        bridge = kodiHue.connect_bridge(monitor, silent=True)  # don't rediscover, proceed silently
        if bridge is not None:
            kodiHue.configure_scene(bridge, kgroup, action)
        else:
            logger.debug("No bridge found. sceneSelect cancelled.")
            xbmcgui.Dialog().notification(_("Hue Service"), _("Check Hue Bridge configuration"))

    elif args == "ambiLightSelect":  # ambiLightSelect=kgroup_id
        kgroup = sys.argv[2]
        logger.debug("Started with {}, kgroup_id: {}".format(args, kgroup))

        bridge = kodiHue.connect_bridge(monitor, silent=True)  # don't rediscover, proceed silently
        if bridge is not None:
            kodiHue.configure_ambi_lights(bridge, kgroup)
        else:
            logger.debug("No bridge found. scene ambi lights cancelled.")
            xbmcgui.Dialog().notification(_("Hue Service"), _("Check Hue Bridge configuration"))
    else:
        globals.ADDON.openSettings()
        return


def service():
    logger.info("service started, version: {}".format(globals.ADDON.getAddonInfo("version")))
    kodiHue.load_settings()
    monitor = kodiHue.HueMonitor()

    bridge = kodiHue.connect_bridge(monitor, silent=globals.disable_connection_message)

    if bridge is not None:
        globals.settings_changed = False
        globals.daylight = kodiHue.get_daylight(bridge)

        kgroups = kodiHue.setup_groups(bridge, globals.initial_flash)
        if globals.ambi_enabled:
            ambi_group = AmbiGroup.AmbiGroup()
            ambi_group.setup(monitor, bridge, kgroup_id=3, flash=globals.initial_flash)

        connection_retries = 0
        timer = 60  # Run loop once on first run
        # #Ready to go! Start running until Kodi exit.
        logger.debug("Main service loop starting")
        while globals.connected and not monitor.abortRequested():

            if globals.settings_changed:
                kgroups = kodiHue.setup_groups(bridge, globals.reload_flash)
                if globals.ambi_enabled:
                    ambi_group.setup(monitor, bridge, kgroup_id=3, flash=globals.reload_flash)
                globals.settings_changed = False

            if timer > 59:
                timer = 0
                try:
                    if connection_retries > 0:
                        bridge = kodiHue.connect_bridge(monitor, silent=True)
                        if bridge is not None:
                            previous_daylight = kodiHue.get_daylight(bridge)
                            connection_retries = 0
                    else:
                        previous_daylight = kodiHue.get_daylight(bridge)

                except ConnectionError as error:
                    connection_retries = connection_retries + 1
                    if connection_retries <= 5:
                        logger.error("Bridge Connection Error. Attempt: {}/5 : {}".format(connection_retries, error))
                        xbmcgui.Dialog().notification(_("Hue Service"), _("Connection lost. Trying again in 2 minutes"))
                        timer = -60

                    else:
                        logger.error(
                            "Bridge Connection Error. Attempt: {}/5. Shutting down : {}".format(connection_retries,
                                                                                                error))
                        xbmcgui.Dialog().notification(_("Hue Service"),
                                                      _("Connection lost. Check settings. Shutting down"))
                        globals.connected = False
                except Exception:
                    logger.exception("Get daylight exception")

                if globals.daylight != previous_daylight:
                    logger.debug(
                        "Daylight change! current: {}, previous: {}".format(globals.daylight, previous_daylight))

                    globals.daylight = kodiHue.get_daylight(bridge)
                    if not globals.daylight:
                        kodiHue.sunset(bridge, kgroups, ambi_group)

            timer += 1
            monitor.waitForAbort(1)
        logger.debug("Process exiting...")
        return
    logger.debug("No connected bridge, exiting...")
    return
