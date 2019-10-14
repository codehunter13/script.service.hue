import datetime
from logging import getLogger
from socket import getfqdn

import requests
import xbmc
import xbmcgui

from resources.lib.qhue.qhue import QhueException
from . import KodiGroup
from . import globals
from . import qhue
from .language import get_string as _

logger = getLogger(globals.ADDONID)


def load_settings():
    logger.debug("Loading settings")
    globals.reload_flash = globals.ADDON.getSettingBool("reload_flash")
    globals.initial_flash = globals.ADDON.getSettingBool("initial_flash")

    globals.force_on_sunset = globals.ADDON.getSettingBool("force_on_sunset")
    globals.daylight_disable = globals.ADDON.getSettingBool("daylight_disable")

    globals.enable_schedule = globals.ADDON.getSettingBool("enable_schedule")
    globals.start_time = globals.ADDON.getSetting("start_time")  # string HH:MM
    globals.end_time = globals.ADDON.getSetting("end_time")  # string HH:MM
    globals.disable_connection_message = globals.ADDON.getSettingBool("disable_connection_message")

    globals.video_minimum_duration = globals.ADDON.getSettingInt(
        "video_MinimumDuration")  # Setting in Minutes. Kodi library uses seconds, needs to be converted.
    globals.video_enable_movie = globals.ADDON.getSettingBool("video_Movie")
    globals.video_enable_music_video = globals.ADDON.getSettingBool("video_MusicVideo")
    globals.video_enable_episode = globals.ADDON.getSettingBool("video_Episode")
    globals.video_enable_other = globals.ADDON.getSettingBool("video_Other")

    globals.ambi_enabled = globals.ADDON.getSettingBool("group3_enabled")

    validate_schedule()


def setup_groups(bridge, flash=False):
    logger.debug("in setup_groups()")
    kgroups = []

    if globals.ADDON.getSettingBool("group0_enabled"):  # VIDEO Group
        kgroups.append(KodiGroup.KodiGroup())
        kgroups[0].setup(bridge, 0, flash, KodiGroup.VIDEO)

    if globals.ADDON.getSettingBool("group1_enabled"):  # Audio Group
        kgroups.append(KodiGroup.KodiGroup())
        kgroups[1].setup(bridge, 1, flash, KodiGroup.AUDIO)

    return kgroups


def create_hue_scene(bridge):
    logger.debug("In kodiHue create_hue_scene")
    scenes = bridge.scenes

    xbmcgui.Dialog().ok(_("Create New Scene"), _("Adjust lights to desired state in the Hue App to save as new scene."),
                        _("Set a fade time in seconds, or set to 0 seconds for an instant transition."))

    scene_name = xbmcgui.Dialog().input(_("Scene Name"))

    if scene_name:
        transition_time = xbmcgui.Dialog().numeric(0, _("Fade Time (Seconds)"), defaultt="10")
        selected = select_hue_lights(bridge)

        if selected:
            res = scenes(lights=selected, name=scene_name, recycle=False, type='LightScene', http_method='post',
                         transitiontime=int(
                             transition_time) * 10)  # Hue API transition time is in 100msec. *10 to convert to seconds.
            logger.debug("In kodiHue create_hue_scene. Res: {}".format(res))
            if res[0]["success"]:
                xbmcgui.Dialog().ok(_("Create New Scene"), _("Scene successfully created!"),
                                    _("You may now assign your Scene to player actions."))
            #   xbmcgui.Dialog().notification(_("Hue Service"), _("Scene Created"))
            else:
                xbmcgui.Dialog().ok(_("Error"), _("Error: Scene not created."))


def delete_hue_scene(bridge):
    logger.debug("In kodiHue delete_hue_scene")
    scene = select_hue_scene(bridge)
    if scene is not None:
        confirm = xbmcgui.Dialog().yesno(_("Delete Hue Scene"), _("Are you sure you want to delete this scene: "),
                                         str(scene[1]))
    if scene and confirm:
        scenes = bridge.scenes
        res = scenes[scene[0]](http_method='delete')
        logger.debug("In kodiHue createHueGroup. Res: {}".format(res))
        if res[0]["success"]:
            xbmcgui.Dialog().notification(_("Hue Service"), _("Scene deleted"))
        else:
            xbmcgui.Dialog().notification(_("Hue Service"), _("ERROR: Scene not created"))


def _discover_nupnp():
    logger.debug("In kodiHue discover_nupnp()")
    try:
        # ssl chain on new URL seems to be fixed
        # req = requests.get('https://www.meethue.com/api/nupnp')
        req = requests.get('https://discovery.meethue.com/')
    except requests.exceptions.ConnectionError as e:
        logger.info("Nupnp failed: {}".format(e))
        return None

    res = req.json()
    bridge_ip = None
    if res:
        bridge_ip = res[0]["internalipaddress"]
    return bridge_ip


def _discover_ssdp():
    from . import ssdp
    from urlparse import urlsplit

    ssdp_list = ssdp.discover("ssdp:all", timeout=5, mx=3)
    logger.debug("ssdp_list: {}".format(ssdp_list))

    bridges = [u for u in ssdp_list if 'IpBridge' in u.server]
    if bridges:
        ip = urlsplit(bridges[0].location).hostname
        logger.debug("ip: {}".format(ip))
        return ip
    return None


def bridge_discover(monitor):
    logger.debug("Start bridge_discover")
    # Create new config if none exists. Returns success or fail as bool
    globals.ADDON.setSettingString("bridge_ip", "")
    globals.ADDON.setSettingString("bridge_user", "")
    globals.connected = False

    progress_bar = xbmcgui.DialogProgress()
    progress_bar.create(_('Searching for bridge...'))
    progress_bar.update(5, _("Discovery started"))

    complete = False
    while not progress_bar.iscanceled() and not complete:

        progress_bar.update(10, _("N-UPnP discovery..."))
        bridge_ip = _discover_nupnp()
        if not bridge_ip:
            progress_bar.update(20, _("UPnP discovery..."))
            bridge_ip = _discover_ssdp()

        if connection_test(bridge_ip):
            progress_bar.update(100, _("Found bridge: ") + bridge_ip)
            monitor.waitForAbort(1)

            bridge_user = create_user(monitor, bridge_ip, progress_bar)

            if bridge_user:
                logger.debug("User created: {}".format(bridge_user))
                progress_bar.update(90, _("User Found!"), _("Saving settings"))

                globals.ADDON.setSettingString("bridge_ip", bridge_ip)
                globals.ADDON.setSettingString("bridge_user", bridge_user)
                complete = True
                globals.connected = True
                progress_bar.update(100, _("Complete!"))
                monitor.waitForAbort(5)
                progress_bar.close()
                logger.debug("Bridge discovery complete")
                return True
            else:
                logger.debug("User not created, received: {}".format(bridge_user))
                progress_bar.update(100, _("User not found"), _("Check your bridge and network"))
                monitor.waitForAbort(5)
                complete = True

                progress_bar.close()

        else:
            progress_bar.update(100, _("Bridge not found"), _("Check your bridge and network"))
            logger.debug("Bridge not found, check your bridge and network")
            monitor.waitForAbort(5)
            complete = True
            progress_bar.close()

    if progress_bar.iscanceled():
        logger.debug("Bridge discovery cancelled by user")
        progress_bar.update(100, _("Cancelled"))
        complete = True
        progress_bar.close()


def connection_test(bridge_ip):
    logger.debug("Connection Test IP: {}".format(bridge_ip))
    b = qhue.qhue.Resource("http://{}/api".format(bridge_ip))
    try:
        apiversion = b.config()['apiversion']
    except (requests.exceptions.ConnectionError, qhue.QhueException) as error:
        logger.debug("Connection test failed.  {}".format(error))
        return False

    # TODO: compare API version properly, ensure api version >= 1.28
    if apiversion:
        logger.info("Bridge Found! Hue API version: {}".format(apiversion))
        return True
    logger.debug("in ConnectionTest():  Connected! Bridge too old: {}".format(apiversion))
    notification(_("Hue Service"), _("Bridge API: {}, update your bridge".format(apiversion)),
                 icon=xbmcgui.NOTIFICATION_ERROR)
    return False


def user_test(bridge_ip, bridge_user):
    logger.debug("in ConnectionTest() Attempt initial connection")
    b = qhue.Bridge(bridge_ip, bridge_user, timeout=globals.QHUE_TIMEOUT)
    try:
        zigbeechan = b.config()['zigbeechannel']
    except (requests.exceptions.ConnectionError, qhue.QhueException):
        return False

    if zigbeechan:
        logger.info("Hue User Authorized. Bridge Zigbee Channel: {}".format(zigbeechan))
        return True
    return False


def discover_bridge_ip():
    # discover hue bridge IP silently for non-interactive discovery / bridge IP change.
    logger.debug("In discover_bridge_ip")
    bridge_ip = _discover_nupnp()
    if connection_test(bridge_ip):
        return bridge_ip

    bridge_ip = _discover_ssdp()
    if connection_test(bridge_ip):
        return bridge_ip
    return False


def create_user(monitor, bridge_ip, progress_bar=False):
    logger.debug("In create_user")
    # device = 'kodi#'+getfqdn()
    data = '{{"devicetype": "kodi#{}"}}'.format(
        getfqdn())  # Create a devicetype named kodi#localhostname. Eg: kodi#LibreELEC

    req = requests
    res = 'link button not pressed'
    timeout = 0
    progress = 0
    if progress_bar:
        progress_bar.update(progress, _("Press link button on bridge"),
                            _("Waiting for 90 seconds..."))  # press link button on bridge

    while 'link button not pressed' in res and timeout <= 90 and not monitor.abortRequested() and not progress_bar.iscanceled():
        logger.debug("In create_user: abortRquested: {}, timer: {}".format(str(monitor.abortRequested()), timeout))

        if progress_bar:
            progress_bar.update(progress, _("Press link button on bridge"))  # press link button on bridge

        req = requests.post('http://{}/api'.format(bridge_ip), data=data)
        res = req.text
        monitor.waitForAbort(1)
        timeout = timeout + 1
        progress = progress + 1

    res = req.json()
    logger.debug("json response: {}, content: {}".format(res, req.content))

    try:
        username = res[0]['success']['username']
        return username
    except Exception:
        logger.exception("Username exception")
        return False


def configure_scene(bridge, k_group_id, action):
    scene = select_hue_scene(bridge)
    if scene is not None:
        # group0_startSceneID
        globals.ADDON.setSettingString("group{}_{}SceneID".format(k_group_id, action), scene[0])
        globals.ADDON.setSettingString("group{}_{}SceneName".format(k_group_id, action), scene[1])
        globals.ADDON.openSettings()


def configure_ambi_lights(bridge, k_group_id):
    lights = select_hue_lights(bridge)
    light_names = []
    color_lights = []
    if lights is not None:
        for L in lights:
            # gamut = get_light_gamut(bridge, l)
            # if gamut == "A" or gamut== "B" or gamut == "C": #defaults to C if unknown model
            light_names.append(_get_light_name(bridge, L))
            color_lights.append(L)

        globals.ADDON.setSettingString("group{}_Lights".format(k_group_id), ','.join(color_lights))
        globals.ADDON.setSettingString("group{}_LightNames".format(k_group_id), ','.join(light_names))
        globals.ADDON.openSettings()


def _get_light_name(bridge, l):
    try:
        name = bridge.lights()[l]['name']
    except Exception:
        logger.exception("getLightName Exception")
        return None

    if name is None:
        return None
    return name


def select_hue_lights(bridge):
    logger.debug("In select_hue_lights{}")
    hue_lights = bridge.lights()

    xbmc.executebuiltin('ActivateWindow(busydialognocancel)')
    items = []
    index = []
    light_ids = []

    for light in hue_lights:
        h_light = hue_lights[light]
        h_light_name = h_light['name']

        # logger.debug("In selectHueGroup: {}, {}".format(hgroup,name))
        index.append(light)
        items.append(xbmcgui.ListItem(label=h_light_name))

    xbmc.executebuiltin('Dialog.Close(busydialognocancel)')
    selected = xbmcgui.Dialog().multiselect(_("Select Hue Lights..."), items)
    if selected:
        # id = index[selected]
        for s in selected:
            light_ids.append(index[s])

    logger.debug("light_ids: {}".format(light_ids))

    if light_ids:
        return light_ids
    return None


def select_hue_scene(bridge):
    logger.debug("In select_hue_scene{}")
    hue_scenes = bridge.scenes()

    xbmc.executebuiltin('ActivateWindow(busydialognocancel)')
    items = []
    index = []
    selected_id = -1

    for scene in hue_scenes:

        h_scene = hue_scenes[scene]
        h_scene_name = h_scene['name']

        if h_scene['version'] == 2 and h_scene["recycle"] is False and h_scene["type"] == "LightScene":
            index.append(scene)
            items.append(xbmcgui.ListItem(label=h_scene_name))

    xbmc.executebuiltin('Dialog.Close(busydialognocancel)')
    selected = xbmcgui.Dialog().select("Select Hue scene...", items)
    if selected > -1:
        selected_id = index[selected]
        h_scene_name = hue_scenes[selected_id]['name']
        logger.debug("In select_hue_scene: selected: {}".format(selected))

    if selected > -1:
        return selected_id, h_scene_name
    return None


def get_daylight(bridge):
    return bridge.sensors['1']()['state']['daylight']


def sunset(bridge, kgroups, ambi_group):
    logger.info("Applying sunset scenes")

    for g in kgroups:
        logger.debug("in sunset() g: {}, kgroup_id: {}".format(g, g.kgroupID))
        if globals.ADDON.getSettingBool("group{}_enabled".format(g.kgroupID)):
            g.sunset()
    if globals.ADDON.getSettingBool("group3_enabled"):
        ambi_group.sunset()
    return


def connect_bridge(monitor, silent=False):
    bridge_ip = globals.ADDON.getSettingString("bridge_ip")
    bridge_user = globals.ADDON.getSettingString("bridge_user")
    logger.debug("in Connect() with settings: bridge_ip: {}, bridge_user: {}".format(bridge_ip, bridge_user))

    if bridge_ip and bridge_user:
        if connection_test(bridge_ip):
            logger.debug("in Connect(): Bridge responding to connection test.")
        else:
            logger.debug("in Connect(): Bridge not responding to connection test, attempt finding a new bridge IP.")
            bridge_ip = discover_bridge_ip(monitor)
            if bridge_ip:
                logger.debug("in Connect(): New IP found: {}. Saving".format(bridge_ip))
                globals.ADDON.setSettingString("bridge_ip", bridge_ip)

        if bridge_ip:
            logger.debug("in Connect(): Checking User")
            if user_test(bridge_ip, bridge_user):
                bridge = qhue.Bridge(bridge_ip, bridge_user, timeout=globals.QHUE_TIMEOUT)
                globals.connected = True
                logger.info("Successfully connected to Hue Bridge: {}".format(bridge_ip))
                if not silent:
                    notification(_("Hue Service"), _("Hue connected"), icon=xbmcgui.NOTIFICATION_INFO)
                return bridge
        else:
            logger.debug("Bridge not responding")
            notification(_("Hue Service"), _("Bridge connection failed"), icon=xbmcgui.NOTIFICATION_ERROR)
            globals.connected = False
            return None

    else:
        logger.debug("Bridge not configured")
        notification(_("Hue Service"), _("Bridge not configured"), icon=xbmcgui.NOTIFICATION_ERROR)
        globals.connected = False
        return None


def validate_schedule():
    logger.debug("Validate schedule. Schedule Enabled: {}".format(globals.enable_schedule))
    if globals.enable_schedule:
        try:
            convert_time(globals.startTime)
            convert_time(globals.endTime)
            logger.debug("Time looks valid")
        except ValueError as e:
            logger.error("Invalid time settings: {}".format(e))
            notification(_("Hue Service"), _("Invalid start or end time, schedule disabled"),
                         icon=xbmcgui.NOTIFICATION_ERROR)
            globals.ADDON.setSettingBool("EnableSchedule", False)
            globals.enable_schedule = False


def get_light_gamut(bridge, l):
    try:
        gamut = bridge.lights()[l]['capabilities']['control']['colorgamuttype']
        logger.debug("Light: {}, gamut: {}".format(l, gamut))
    except Exception:
        logger.exception("Can't get gamut for light, defaulting to Gamut C: {}".format(l))
        return "C"
    if gamut == "A" or gamut == "B" or gamut == "C":
        return gamut
    return "C"  # default to C if unknown gamut type


def check_bridge_model(bridge):
    try:
        bridge_config = bridge.config()
        model = bridge_config["modelid"]
    except QhueException:
        logger.exception("Exception: check_bridge_model")
        return None
    if model == "BSB002":
        logger.debug("Bridge model OK: {}".format(model))
        return True
    logger.error("Unsupported bridge model: {}".format(model))
    xbmcgui.Dialog().ok(_("Unsupported Hue Bridge"), _(
        "Hue Bridge V1 (Round) is unsupported. Hue Bridge V2 (Square) is required for certain features."))
    return None


def convert_time(time):
    hour = int(time.split(":")[0])
    minute = int(time.split(":")[1])
    return datetime.time(hour, minute)


def notification(header, message, time=5000, icon=globals.ADDON.getAddonInfo('icon'), sound=True):
    xbmcgui.Dialog().notification(header, message, icon, time, sound)


def perf_average(process_times):
    process_times = list(process_times)  # deque is mutating during iteration for some reason, so copy to list.
    size = len(process_times)
    total = 0
    for x in process_times:
        total += x
    average_process_time = int(total / size * 1000)
    return "{} ms".format(average_process_time)


class HueMonitor(xbmc.Monitor):
    def __init__(self):
        super(xbmc.Monitor, self).__init__()

    def onSettingsChanged(self):
        logger.info("Settings changed")
        # self.waitForAbort(1)
        load_settings()
        globals.settings_changed = True
