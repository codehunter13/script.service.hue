# -*- coding: utf-8 -*-

import sys
from logging import getLogger
from requests.exceptions import ConnectionError

import xbmcgui

from . import globals
from . import kodiHue
from . import kodiutils
from .language import get_string as _

logger = getLogger(globals.ADDONID)

def menu():

    monitor = kodiHue.HueMonitor()

    if len(sys.argv) >1:
        args = sys.argv[1]
    else: 
        args = ""

    logger.info("menu started, version: {}, Arguments: {}".format(globals.ADDON.getAddonInfo('version'), args))

    if args == "discover":
        logger.debug("Started with Discovery")
        bridge = kodiHue.bridgeDiscover(monitor)
        if bridge is not None:
            logger.debug("Found bridge, starting service.")
            service() #restart service


    elif args == "createHueScene":
        logger.debug("Started with {}".format(args))
        bridge = kodiHue.connectBridge(monitor, silent=True)  # don't rediscover, proceed silently
        if bridge is not None:
            kodiHue.createHueScene(bridge)
        else:
            logger.debug("No bridge found. createHueScene cancelled.")
            xbmcgui.Dialog().notification(_("Hue Service"), _("Check Hue Bridge configuration"))

    elif args == "deleteHueScene":
        logger.debug("Started with {}".format(args))

        bridge = kodiHue.connectBridge(monitor, silent=True)  # don't rediscover, proceed silently
        if bridge is not None:
            kodiHue.deleteHueScene(bridge)
        else:
            logger.debug("No bridge found. deleteHueScene cancelled.")
            xbmcgui.Dialog().notification(_("Hue Service"), _("Check Hue Bridge configuration"))

    elif args == "sceneSelect": # sceneSelect=kgroup,action  / sceneSelect=0,play
            kgroup = sys.argv[2]
            action = sys.argv[3]
            logger.debug("Started with {}, kgroup: {}, kaction: {}".format(args, kgroup, action))

            bridge = kodiHue.connectBridge(monitor, silent=True)  # don't rediscover, proceed silently
            if bridge is not None:
                kodiHue.configureScene(bridge, kgroup, action)

                #TODO: save selection
            else:
                logger.debug("No bridge found. sceneSelect cancelled.")
                xbmcgui.Dialog().notification(_("Hue Service"), _("Check Hue Bridge configuration"))    

    else:
        globals.ADDON.openSettings()
        return


def service():
    logger.info("service started, version: {}".format(globals.ADDON.getAddonInfo('version')))

    monitor = kodiHue.HueMonitor()

    initialFlash = kodiutils.get_setting_as_bool("initialFlash")
    globals.forceOnSunset = kodiutils.get_setting_as_bool("forceOnSunset")
    globals.daylightDisable = kodiutils.get_setting_as_bool("daylightDisable")

    bridge = kodiHue.connectBridge(monitor,silent=False)

    if bridge is not None:
        globals.settingsChanged = False
        globals.daylight = kodiHue.getDaylight(bridge)
        kgroups = kodiHue.setupGroups(bridge,initialFlash)
        
        connectionRetries = 0
        timer = 60 #Run loop once on first run
        # #Ready to go! Start running until Kodi exit.
        logger.debug('Main service loop starting')
        while globals.connected and not monitor.abortRequested():
            
               
            if globals.settingsChanged:
                reloadFlash = kodiutils.get_setting_as_bool("reloadFlash")
                globals.forceOnSunset = kodiutils.get_setting_as_bool("forceOnSunset")
                globals.daylightDisable = kodiutils.get_setting_as_bool("daylightDisable")

                kgroups = kodiHue.setupGroups(bridge, reloadFlash)
                globals.settingsChanged = False


            if timer > 59: #run this loop once per minute.
                timer = 0
                try:
                    if connectionRetries > 0:
                        bridge = kodiHue.connectBridge(monitor,silent=True)
                        if bridge is not None:
                            previousDaylight = kodiHue.getDaylight(bridge)
                            connectionRetries = 0
                    else:
                        previousDaylight = kodiHue.getDaylight(bridge)
                        
                except ConnectionError as error:
                    connectionRetries = connectionRetries + 1
                    if connectionRetries <= 5:
                        logger.error('Bridge Connection Error. Attempt: {}/5 : {}'.format(connectionRetries, error))
                        xbmcgui.Dialog().notification(_("Hue Service"), _("Connection lost. Trying again in 2 minutes"))
                        timer = -60 #set timer to negative 1 minute
                        
                    else:
                        logger.error('Bridge Connection Error. Attempt: {}/5. Shutting down : {}'.format(connectionRetries, error))
                        xbmcgui.Dialog().notification(_("Hue Service"), _("Connection lost. Check settings. Shutting down"))
                        globals.connected = False
                except Exception as error:
                    logger.error('Get daylight exception: {}'.format(error))


                if globals.daylight != previousDaylight :
                    logger.debug('Daylight change! current: {}, previous: {}'.format(globals.daylight, previousDaylight))
                    
                    globals.daylight = kodiHue.getDaylight(bridge)
                    if not globals.daylight:
                        kodiHue.sunset(bridge,kgroups)
                        
            timer = timer + 1
            monitor.waitForAbort(1)
        logger.debug('Process exiting...')
        return

    else:
        logger.debug('No connected bridge, exiting...')
        return
