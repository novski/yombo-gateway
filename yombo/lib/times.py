# This file was created by Yombo for use with Yombo Python gateway automation
# software.  Details can be found at https://yombo.net
"""

.. note::

  For more information see: `Times @ Module Development <https://yombo.net/docs/modules/times/>`_

Sets up various times and events for: dusk, dawn, sunrise, sunset. Also send event messages when a status change
changes.  It also configures many State items such as times_light, times_dark, times_dawn, times_dusk

This library uses the python Ephem module to provide many astronomy computations, such as which objects are
above or below the horizon (saturn, moon, sun, etc), and then they will transition next.

    **Usage**:

    .. code-block:: python

       times = self._Libraries['Times']
       moonrise = times.item_rise(dayOffset=1, item='Moon') # 1 - we want the next moon rise

.. todo::

  Polar region debug (some strange glitches like nowNight message when it is polar day (I think we need variables for
  polar day and night begin/end)

.. moduleauthor:: Mitch Schwenk <mitch-gw@yombo.net>

:copyright: Copyright 2012-2016 by Yombo.
:license: LICENSE for details.
"""
# Import python libraries
import ephem
from time import time
from calendar import timegm as CalTimegm
from datetime import datetime, timedelta

# Import twisted libraries
from twisted.internet import reactor

# Import Yombo libraries
from yombo.core.exceptions import YomboTimeError, YomboHookStopProcessing
from yombo.core.library import YomboLibrary
from yombo.core.log import get_logger
from yombo.utils import is_one_zero, global_invoke_all
import arrow

logger = get_logger('library.times')

class Times(YomboLibrary, object):
    """
    Provides light/dark/dusk/dawn status, times, and events. Also provides various rise/set of the sun, moon, and all
    things heavenly.
    """
    def _init_(self, PatchEnvironment = False):
        """
        Setup various common objects, setup frame work if isday/night/dark/twilight.
        :param loader: A pointer to the L{Loader<yombo.lib.loader.Loader>}
        library.
        :type loader: Instance of Loader
        """
        if PatchEnvironment: self.runned_for_tests()

        # These are used below
        # self.isTwilight = None
        # self.isLight = None
        # self.isDark = None
        # self.isDay = None
        # self.isNight = None
        # self.isDawn = None
        # self.isDusk = None
        # self.nextSunrise = None
        # self.nextSunset = None
        # self.nextMoonrise = None
        # self.nextMoonset = None

        self.time_ajust = 150.0

        self.obs = ephem.Observer()
        self.obs.lat = str(self._Configs.get('location', 'latitude', 0))
        self.obs.lon = str(self._Configs.get('location', 'longitude', 0))
        self.obs.elevation = int(self._Configs.get('location', 'elevation', 800))

        self.obsTwilight = ephem.Observer()
        self.obsTwilight.horizon = str(self._Configs.get('times', 'twilighthorizon', '-6')) # civil = -6, nautical = -12, astronomical = -18
        self.obsTwilight.lat = str(self._Configs.get('location', 'latitude', 0))
        self.obsTwilight.lon = str(self._Configs.get('location', 'longitude', 0))
        self.obsTwilight.elevation = int(self._Configs.get('location', 'elevation', 800))

        self.CLnowLight = None
        self.CLnowDark = None
        self.CLnowDay = None
        self.CLnowNight = None
        self.CLnowNotDawn = None
        self.CLnowNotDusk = None
        self.CLnowDawn = None
        self.CLnowDusk = None

        self.is_now_init = True
        self._setup_light_dark_events()
        self._setup_day_night_events()
        self._setup_next_twilight_events() # needs to be called before setupNextDawnDuskEvent
        self._setup_next_dawn_dusk_event()
        self._setup_moon_events()
        self.is_now_init = False

    @property
    def isTwilight(self):
        return self.__isTwilight

    @isTwilight.setter
    def isTwilight(self, val):
        self._States.set('is.twilight', val, 'bool')
        self.__isTwilight = val
        self._Statistics.datapoint("lib.times.is_twilight", is_one_zero(val))

    @property
    def isLight(self):
        return self.__isLight

    @isLight.setter
    def isLight(self, val):
        self._States.set('is.light', val, 'bool')
        self.__isLight = val
        self._Statistics.datapoint("lib.times.is_light", is_one_zero(val))

    @property
    def isDark(self):
        return self.__isDark

    @isDark.setter
    def isDark(self, val):
        self._States.set('is.dark', val, 'bool')
        self.__isDark = val
        self._Statistics.datapoint("lib.times.is_dark", is_one_zero(val))

    @property
    def isDay(self):
        return self.__isDay

    @isDay.setter
    def isDay(self, val):
        self._States.set('is.day', val, 'bool')
        self.__isDay = val
        self._Statistics.datapoint("lib.times.is_day", is_one_zero(val))

    @property
    def isNight(self):
        return self.__isNight

    @isNight.setter
    def isNight(self, val):
        self._States.set('is.night', val, 'bool')
        self.__isNight = val
        self._Statistics.datapoint("lib.times.is_night", is_one_zero(val))

    @property
    def isDawn(self):
        return self.__isDawn

    @isDawn.setter
    def isDawn(self, val):
        self._States.set('is.dawn', val, 'bool')
        self.__isDawn = val
        self._Statistics.datapoint("lib.times.is_dawn", is_one_zero(val))

    @property
    def isDusk(self):
        return self.__isDusk

    @isDusk.setter
    def isDusk(self, val):
        self._States.set('is.dusk', val, 'bool')
        self.__isDusk = val
        self._Statistics.datapoint("lib.times.is_dusk", is_one_zero(val))

    @property
    def nextSunrise(self):
        return self.__nextSunrise

    @nextSunrise.setter
    def nextSunrise(self, val):
        if '__nextSunrise' in locals():
            if val != self.__nextSunrise:
                self._States.set('next.sunrise', int(round(val)), 'epoch')
                self.__nextSunrise = val
        else:
            self.__nextSunrise = val
            self._States.set('next.sunrise', int(round(val)), 'epoch')

    @property
    def nextSunset(self, val):
        return self.__nextSunset

    @nextSunset.setter
    def nextSunset(self, val):
        if '__nextSunset' in locals():
            if val != self.__nextSunset:
                self._States.set('next.sunset', int(round(val)), 'epoch')
                self.__nextSunset = val
        else:
            self._States.set('next.sunset', int(round(val)), 'epoch')
            self.__nextSunset = val

    @property
    def nextMoonrise(self):
        return self.__moonRise

    @nextMoonrise.setter
    def nextMoonrise(self, val):
        if '__moonRise' in locals():
            if val != self.__moonRise:
                self._States.set('next.moonrise', int(round(val)), 'epoch')
                self.__moonRise = val
        else:
            self._States.set('next.moonrise', int(round(val)), 'epoch')
            self.__moonRise = val

    @property
    def nextMoonset(self):
        return self.__moonSet

    @nextMoonset.setter
    def nextMoonset(self, val):
        if '__moonSet' in locals():
            if val != self.__moonSet:
                self._States.set('next.moonset', int(round(val)), 'epoch')
                self.__moonSet = val
        else:
            self._States.set('next.moonset', int(round(val)), 'epoch')
            self.__moonSet = val

    def _load_(self):
        """
        Nothing to do.
        """
        pass

    def _start_(self):
        """
        Nothing to do.
        """
        pass

    def _unload_(self):
        """
        Nothing to do.
        """
        pass

    def _stop_(self):
        """
        Nothing to do.
        """
        pass

    def _setup_moon_events(self):
        """
        Setup events to be called when moon rise/set needs to change.
        Two callLater's are setup: one to send a broadcast event of the change
        the second callLater is to come back to this function and redo it all.
        This is different than day/night since it accounts for twilight.
        """
        self.CLnowMoonRise = None
        self.CLnowMoonSet = None

        nextMoonrise = self.item_rise(item='Moon')
        nextMoonset = self.item_set(item='Moon')
        self.nextMoonrise = nextMoonrise
        self.nextMoonset = nextMoonset

        if self.item_visible(item='Moon'):
            self.CLnowMoonEvents = reactor.callLater(self.nextMoonset+1.1, self.send_event_hook, 'now_moonset')
            reactor.callLater(self.nextMoonset+1, self._setup_moon_events)
        else:
            self.CLnowMoonEvents = reactor.callLater(self.nextMoonrise+1.1, self.send_event_hook, 'now_moonrise')
            reactor.callLater(self.nextMoonrise+1, self._setup_moon_events)

    def _setup_light_dark_events(self):
        """
        Setup events to be called when isLight and isDark needs to change.
        Two callLater's are setup: one to send a broadcast event of the change
        the second callLater is to come back to this function and redo it all.
        This is different than day/night since it accounts for twilight.
        """
        self._CalcDayNight()
        self._CalcLightDark() # setup isLight & isDark
        #logger.info("islight: %s", self.isLight)

        setTime = 0
        if self.isLight:
            setTime = self.sunset_twilight() - time()
            #print "%d = %d - %d" % (setTime, self.sunset_twilight(),time())
            self.CLnowDark = reactor.callLater(setTime+1.1, self.send_event_hook, 'now_dark')
            #print "self.CLnowDark = reactor.callLater(setTime, self.send_event_hook, 'nowDark')"
        else:
            setTime = self.sunrise_twilight() - time()
            #print "setTime = self.sunrise_twilight()"
            #print "%d = %d - %d" % (setTime, self.sunrise_twilight(),time())
            self.CLnowLight = reactor.callLater(setTime+1.1, self.send_event_hook, 'now_light')

        #set a callLater to redo islight/dark, and setup next broadcast.
        reactor.callLater(setTime+1, self._setup_light_dark_events)

    def _setup_day_night_events(self):
        """
        Setup events to be called when isDay and isNight needs to change.
        Two callLater's are setup: one to send a broadcast event of the change
        the second callLater is to come back to this function and redo it all.
        This is different than light/dark since this doesn't account
        for twilight.
        """
        self._CalcDayNight()
        if self.isDay:
            setTime = self.sunset() - time()
            logger.debug("NowNight event in: {setTime}", setTime=setTime)
            self.CLnowNight = reactor.callLater(setTime+1.1, self.send_event_hook, 'now_night')
        else:
            setTime = self.sunrise() -time()
            logger.debug("NowDay event in: {setTime}", setTime=setTime)
            self.CLnowDay = reactor.callLater(setTime+1.1, self.send_event_hook, 'now_day')

        #set a callLater to redo isday/night, and setup next broadcast.
        reactor.callLater(setTime+1, self._setup_day_night_events)

    ###  This function is not complete.  Need to calculate when the next
    ###  twilight period is. I just copied setupDayNightEvents to here for now.
    # When fixed, remove self._CalcTwilight() from def_setup_next_dawn_dusk_event
    def _setup_next_twilight_events(self):
        """
        Setup events to be called when isTwilight needs to change.
        Two callLater's are setup: one to send a broadcast event of the change
        the second callLater is to come back to this function and redo it all.
        This is different than light/dark since this doesn't account
        for twilight.
        """
        pass  ## we are out of service for now..
        self._CalcDayNight()
        self._CalcTwilight()  #is it twilight right now?
        if self.isTwilight:
            setTime = self.sunset_twilight() - time()
            riseTime = self.sunrise() - time()
            twTime = min (setTime, riseTime)
            logger.debug("nowNotTwilight event in: {twTime}", twTime=twTime)
            self.CLnowNotTwilight = reactor.callLater(twTime+1.1, self.send_event_hook, 'now_not_twilight')
        else:
            setTime = self.sunset() - time()
            riseTime = self.sunrise_twilight() - time()
            twTime = min(setTime, riseTime)
            logger.debug("nowTwilight event in: {twTime}", twTime=twTime)
            self.CLnowTwilight = reactor.callLater(twTime+1.1, self.send_event_hook, 'now_twilight')

        reactor.callLater(twTime+1, self._setup_next_twilight_events)

    def _setup_next_dawn_dusk_event(self):
        """
        Setup events to be called when it's either dawn, notdawn, dusk,
        and notdusk.
        Two callLater's are setup: one to send a broadcast event of the change
        the second callLater is to come back to this function and redo it all.
        """
        self.CLnowNotst = None
        self.CLnowNotDusk = None
        self.CLnowDawn = None
        self.CLnowDusk = None
        if self.is_now_init is False:
            self._CalcTwilight()  #is it twilight right now?

        sunrise = self.sunrise_twilight() # for today
        sunset = self.sunset()  # for today
        self.nextSunrise = sunrise
        self.nextSunset = sunset

        sunrise_end = self.sunrise() # for today
        sunset_end = self.sunset_twilight()  # for today
        logger.debug("_setup_next_dawn_dusk_event - Sunset: {sunset}", sunset=sunset)
        #print "t = %s" % datetime.fromtimestamp(time())
        curtime = time()
        # First, determine we are closer to sunrise or sunset
        secsRise = sunrise - curtime#here
        secsSet = sunset - curtime

        secsRiseEnd = sunrise_end - curtime#here
        secsSetEnd = sunset_end - curtime
        if self.isTwilight == True: # It's twilight. Sun is down.
            if secsRiseEnd < secsSetEnd: #  it's dawn right now = twilight + closer to sunrise's end
                self.CLnowNotDawn = reactor.callLater(secsRiseEnd+1.1, self._send_now_not_dawn) # set a timer for no more dawn
                reactor.callLater(secsRiseEnd+1, self._setup_next_dawn_dusk_event)
                if self.is_now_init:
                    self.isDawn = True
                    self.isDusk = False
            else: # else, closer to sunset.
                self.CLnowNotDusk = reactor.callLater(secsSetEnd+1.1, self._send_now_not_dusk) # set a timer for no more dusk
                reactor.callLater(secsSetEnd+1, self._setup_next_dawn_dusk_event)
                if self.is_now_init:
                    self.isDawn = False
                    self.isDusk = True
        else: # it's not twilight, we need to set a time for it to start.
            if secsRise < secsSet: #  it's going to be dawn next = no twilight + closer to sunrise
                self.CLnowDawn = reactor.callLater(secsRise+1.1, self._send_now_dawn) # set a timer for is dawn
                reactor.callLater(secsRise+1, self._setup_next_dawn_dusk_event)
                if self.is_now_init:
                    self.isDawn = False
                    self.isDusk = False
            else: # else, we are closer to sunset!
                self.CLnowDusk = reactor.callLater(secsSet+1.1, self._send_now_dusk) # set a timer for is dusk
                reactor.callLater(secsSet+1, self._setup_next_dawn_dusk_event)
                if self.is_now_init:
                    self.isDawn = False
                    self.isDusk = False
        logger.debug("Start next twilight in: rise begins {secsRise} (set begins {secSet}), stop next twilight: rise ends {secsRiseEnd} (set ends {secSetEnd})",
                     secsRise=secsRise, secsSet=secsSet, secsRiseEnd=secsRiseEnd, secsSetEnd=secsSetEnd)

    def _send_now_dawn(self):
        """
        Called by timer when it's nowDawn.
        """
        self.isDawn = True
        self.send_event_hook('now_dawn')

    def _send_now_not_dawn(self):
        """
        Called by timer when it's nowNotDawn. Calls _setupNextTwlightEvents
        to setup the next twilight cycle for dusk.
        """
        self.isDawn = False
        self.send_event_hook('now_not_dawn')

    def _send_now_dusk(self):
        """
        Called by timer when it's nowDusk.
        """
        self.isDusk = True
        self.send_event_hook('now_dusk')

    def _send_now_not_dusk(self):
        """
        Called by timer when it's nowNotDusk. Calles _setupNextTwlightEvents
        to setup the next twilight cycle for dawn.
        """
        self.isDusk = False
        self.send_event_hook('now_not_dusk')

    def get_future(self, **kwargs):
        """
        Get a time in the future. Can specify years, weeks, months, hours, minutes, seconds
        
        .. code-block:: python

            a_time = self._Times.get_future(weeks=+1, minutes=+3)  # 1 week, 3 minutes into the future
        
        :param kwargs: 
        :return: 
        """
        utc = arrow.utcnow()
        return utc.replace(hours=+2, minutes=+1).timestamp

    def get_next(self, **kwargs):
        """
        Get a time when the next time occurs. For example, if you want when the next 10pm at night is:

            >>> a_time = self._Times.get_next(hour=22)  # The next time it's 10pm
         

        :param kwargs: 
        :return: 
        """
        return datetime.now().replace(**kwargs).strftime('%s')

    def get_future_or_next(self, **kwargs):
        """
        Returns a time of whichever is less of :py:meth:`get_future <get_future>` and :py:meth:`get_next <get_next>`.
        
        This is useful for when you want to turn something on or off, but don't want to wait too long. For example,
        if you request the next time it's 10pm, and it's 10:01pm, you probably don't want to wait 23 hours and 59
        minutes.
        
        .. code-block:: python

            a_time = self._Times.get_future_or_next(hours=5, hour=2200)
            # Return least time of either 5 hour or 10pm.
        

        :param kwargs: 
        :return: 
        """
        vars = {}
        for key, value in kwargs.iteritems():
            if key in ['year', 'month', 'day', 'hour', 'minute', 'second']:
                vars[key] = value
        next_time = self.get_next(**vars)

        vars = {}
        for key, value in kwargs.iteritems():
            if key in ['years', 'months', 'days', 'hours', 'minutes', 'seconds']:
                vars[key] = value
        future_time = self.get_next(**vars)

        if future_time < next_time:
            return future_time
        else:
            return next_time

    def send_event_hook(self, event_msg):
        """
        Generate an "event" message of status type being the time
        event name.

        **Hooks called**:

        * _time_event_ : Sends kwargs: *key* - The name of the state being set. *value* - The new value to set.

        """
        try:
            state_changes = global_invoke_all('_time_event_', **{'value': event_msg})
        except YomboHookStopProcessing:
            logger.warning("Stopping processing 'send_event_hook' due to YomboHookStopProcessing exception.")
            return

    def _CalcTwilight(self):
        """
        Sets the class variable "isTwilight" depending if it's
        twilight right now. This is called everytime gateway starts
        and when the last twilight has ended.

        schematically:

        set - setting time
        rise - rising time
        Tset - setting of obsTwilight
        Trise - rising of obsTwilight
        N(x) - next, e.g. N(rise) -- next rising, N(Tset) -- next setting of obsTwilight

        -->>>----Time flow--->>>>-----

               |TWILIGHT    |     NIGHT         |TWILIG|   DAY        |TWILIGHT|       NIGHT       |TWILIGHT |   DAY        |TWILIGHT  |    NIGHT
               |            |                   |      |              |        |                   |         |              |          |
              set                                     rise           set                                    rise           set
               |---------------------------------------|              |--------------------------------------|              |---------------------------------------
               |      N(set)>N(rise)                   |N(set)<N(rise)|       N(set)>N(rise)                 |N(set)<N(rise)|        N(set)>N(rise)

        --------------------|                   |------------------------------|                   |-----------------------------------|
                          Tset                Trise                           Tset                Trise                               Tset
        N(Tset)<N(Trise)    | N(Tset)>N(Trise)  |  N(Tset)<N(Trise)            | N(TSet)>N(Trise)  |      N(Tset) < N(Trise)           |

        So the TWILIGHT events occur when (N(set)>N(rise) AND  N(Tset)<N(Trise))
        This condition should work on polar day/night also.
        """
        self.obs.date = datetime.utcnow()
        self.obsTwilight.date = datetime.utcnow()

        if self._next_setting(self.obsTwilight,ephem.Sun(),use_center=True) < self._next_rising(self.obsTwilight,ephem.Sun(),use_center=True) \
          and \
          self._next_setting(self.obs,ephem.Sun()) > self._next_rising(self.obs,ephem.Sun()):
            self.isTwilight = True
        else:
            self.isTwilight = False
        #print "istwilight = %s" % self.isTwilight

    def _CalcLightDark(self):
        """
        Sets the isLight and isDark vars.  It's light if the sun is up and it's twilight.
        """
        self.obs.date = datetime.utcnow()
        self.obsTwilight.date = datetime.utcnow()
        #logger.info("isLight: %s < %s", self._previous_rising(self.obsTwilight,ephem.Sun(),use_center=True),
        #            self._previous_setting(self.obsTwilight,ephem.Sun(),use_center=True))

        if self._previous_rising(self.obsTwilight,ephem.Sun(),use_center=True) < self._previous_setting(self.obsTwilight,ephem.Sun(),use_center=True):
            self.isLight = False
            self.isDark = True
        else:
            self.isLight = True
            self.isDark = False

    def _CalcDayNight(self):
        """
        Sets up isDay and isNight. Is day if the sun is not below horizon.
        """
        self.obs.date = self.obsTwilight.date = datetime.utcnow()
        if self._previous_rising(self.obs,ephem.Sun()) < self._previous_setting(self.obs,ephem.Sun()):
            self.isDay = False
            self.isNight = True
        else:
            self.isDay = True
            self.isNight = False

    def next_twilight(self):
        """
        Returns the times of the next twilight. If it's currently twilight, then start will be "0".
        """
        self.obs.date = datetime.utcnow()
        self.obsTwilight.date = datetime.utcnow()
        if self.isDay:
            end = self._next_setting(self.obsTwilight,ephem.Sun(),use_center=True)
            start = self._next_setting(self.obs,ephem.Sun())
        else:
            #if it actually is night (between twilight observer setting and rising)
            if self._previous_rising(self.obsTwilight,ephem.Sun(),use_center=True) < self._previous_setting(self.obsTwilight,ephem.Sun(),use_center=True):
                start = self._next_rising(self.obsTwilight,ephem.Sun(),use_center=True)
                end = self._next_rising(self.obs,ephem.Sun())
            else: #twilight remains
                start = 0
                end = min(self._next_setting(self.obsTwilight,ephem.Sun(),use_center=True),self._next_rising(self.obs,ephem.Sun()))
        if  self.isTwilight == True:
            start = 0
        return {'start' : self._timegm(start), 'end' : self._timegm(end)}

    def item_visible(self, **kwargs):
        """
        Returns a true if the given item is above the horizon.

        **Usage**:

        .. code-block:: python

            saturn_visible = self._Times.item_visible('Saturn') # Is Saturn above the horizon? (True/False)

        :raises YomboTimeError: Raised when function encounters an error.
        :param item: The device UUID or device label to search for.
        :type item: string
        :return: Pointer to array of all devices for requested device type
        :rtype: dict
        """
        if 'item' not in kwargs:
           raise YomboTimeError("item_visible() must have 'item' set.")
        item = kwargs['item']

        try:
            obj = getattr(ephem, item)
        except AttributeError:
            raise YomboTimeError("Couldn't not find PyEphem item: %s" % item)
        self.obs.date = datetime.utcnow()

        #if it is rised and not set, then it is visible
        if self._previous_rising(self.obs,obj()) > self._previous_setting(self.obs,obj()):
            return False
        else:
            return True

    def item_rise(self, **kwargs):
        """
        Returns when an item rises.

        **Usage**:

        .. code-block:: python

            mars_rise = self._Times.item_rise(dayOffset=1, item='Saturn') # the NEXT (1) rising of Mars.

        :raises YomboTimeError: Raised when function encounters an error.
        :param dayOffset: Default=0. How many days in future to find when item rises. 0 = Today, 1=Tomorrow, etc, -1=Yesterday
        :type dayOffset: int
        :param item: Default='Sun'. PyEphem item to search for and return results for.
        :type item: string
        :return: Pointer to array of all devices for requested device type
        :rtype: dict
        """
        if 'item' not in kwargs:
           raise YomboTimeError("item_rise() must have 'item' set.")
        item = kwargs['item']
        dayOffset = 0
        if 'dayOffset' in kwargs:
            dayOffset = kwargs['dayOffset']

        try:
            obj = getattr(ephem, item)
        except AttributeError:
            raise YomboTimeError("Couldn't not find PyEphem item: %s" % item)
        self.obs.date = datetime.utcnow()+timedelta(days=dayOffset)
        temp = self._next_rising(self.obs,obj())
        return self._timegm (temp)
    
    def item_set(self, **kwargs):
        """
        Returns when an item sets.

        **Usage**:

        .. code-block:: python

            pluto_set = self._Times.item_set(dayOffset=0, item='Pluto') # the NEXT (0) setting of Pluto.

        :raises YomboTimeError: Raised when function encounters an error.
        :param dayOffset: Default=0. How many days in future to find when item sets. 0 = Today, 1=Tomorrow, etc, -1=Yesterday
        :type dayOffset: int
        :param item: Default='Sun'. PyEphem item to search for and return results for.
        :type item: string
        :return: Pointer to array of all devices for requested device type
        :rtype: dict
        """
        if 'item' not in kwargs:
           raise YomboTimeError("item_set() must have 'item' set.")
        item = kwargs['item']
        dayOffset = 0
        if 'dayOffset' in kwargs:
            dayOffset = kwargs['dayOffset']

        try:
            obj = getattr(ephem, item)
        except AttributeError:
            raise YomboTimeError("Couldn't not find PyEphem item: %s" % item)
        # we want the date part only, but date.today() isn't UTC.
        dt = datetime.utcnow()+timedelta(days=dayOffset)
        self.obs.date = dt
        temp = self._next_setting(self.obs,obj())
        return self._timegm(temp)

    def sunrise(self, **kwargs):
        """
        Return sunrise, optionaly returns sunrise +/- # days. The offset of "0" would be
        for the next sunrise.
        :param dayOffset: Default=0. How many days to offset. 0 would be next, -1 is today.
        :type dayOffset: int
        :param item: Default='Sun'. PyEphem item to search for and return results for.
        :type item: string
        """
        dayOffset = kwargs.get('dayOffset', 0)
        return self.item_rise(dayOffset=dayOffset, item='Sun')

    def sunset(self, **kwargs):
        """
        Return sunset, optionaly returns sunset +/- # days.

        :param dayOffset: Default=0. How many days to offset. 0 would be next, -1 is today.
        :type dayOffset: int
        :param item: Default='Sun'. PyEphem item to search for and return results for.
        :type item: string
        """
        dayOffset = 0
        if 'dayOffset' in kwargs:
            dayOffset = kwargs['dayOffset']
        return self.item_set(dayOffset=dayOffset, item='Sun')

    def sunrise_twilight(self, **kwargs):
        """
        Return sunrise, optionally returns sunrise +/- # days.

        :param dayOffset: Default=0. How many days to offset. 0 would be next, -1 is today's. But not always, on polar day this would be wrong
        :type dayOffset: int
        :param item: Which item to return information on. Sun, Moon, Mars, Jupiter, etc.
        :type item: string
        """
        dayOffset = 0
        if 'dayOffset' in kwargs:
            dayOffset = kwargs['dayOffset']
        item = 'Sun'
        if 'item' in kwargs:
            item = kwargs['item']

        try:
            obj = getattr(ephem, item)
        except AttributeError:
            raise YomboTimeError("Couldn't not find PyEphem item: %s" % item)
        self.obsTwilight.date = datetime.utcnow()+timedelta(days=dayOffset)
        temp = self._next_rising(self.obsTwilight,obj(),use_center=True)
        return self._timegm(temp)

    def sunset_twilight(self, **kwargs):
        """
        Return sunset, optionaly returns sunset +/- # days.
        """
        dayOffset = 0
        if 'dayOffset' in kwargs:
            dayOffset = kwargs['dayOffset']
        item = 'Sun'
        if 'item' in kwargs:
            item = kwargs['item']

        try:
            obj = getattr(ephem, item)
        except AttributeError:
            obj = getattr(ephem, 'Sun')

        # we want the date part only, but date.today() isn't UTC.
        dt = datetime.utcnow()+timedelta(days=dayOffset)
        self.obsTwilight.date = dt
        temp = self._next_setting(self.obsTwilight,obj(),use_center=True)
        return self._timegm(temp)

    # These wrappers need for polar regions where day might be longer than 24 hours
    def _previous_rising(self, observer, item, use_center=False):
        return self._riset_wrapper(observer,'previous_rising',item,use_center=use_center)

    def _previous_setting(self, observer, item, use_center=False):
        return self._riset_wrapper(observer,'previous_setting',item,use_center=use_center)

    def _next_rising(self, observer, item, use_center=False):
        return self._riset_wrapper(observer,'next_rising',item,use_center=use_center)

    def _next_setting(self, observer, item, use_center=False):
        return self._riset_wrapper(observer,'next_setting',item,use_center=use_center)
    def _riset_wrapper(self, observer, obsf_name, obj,use_center=False):
        save_date = observer.date #we need to save this date to compare with later
        while True:
            try:
                dt = getattr(observer,obsf_name)(obj,use_center=use_center)
                observer.date = save_date
                return dt
            except (ephem.AlwaysUpError,ephem.NeverUpError):
                if (observer.date < save_date - 365) or (observer.date > save_date + 365):
                    print 'Could not find daylight bounds, last checked date ', observer.date, ', first checked ', save_date,' - year checked day by day.'
                    raise #It is not possible to found setting or rising
                continue

    def _timegm (self, dt):
        return CalTimegm(dt.tuple())

#******************************************************************************************************
#************************************ TESTS  **********************************************************
#******************************************************************************************************
    def runned_for_tests(self):
        """
        Patch reactor.callLater to be a simple print for tests
        """
        #        self.call_arr = []
        self.call_dict = {}
        from thread import allocate_lock
        self.mutex = allocate_lock()
        self.uniq = 1
        self.show_messages = True
        def callLaterMy (a,b,c=None):
            assert a>0, "callLater will fail if secondsOffset <= 0 (%s)" % a
            coef = time()
            self.mutex.acquire()
            if (self.show_messages):
                print 'calling reactor.callLater (', a, b, c, ')'
            #            self.call_arr.append((a,b,c))
            if (self.call_dict.has_key(a+coef)):
                self.call_dict[a+coef] = self.call_dict[a+coef] + [(float(a+coef),b,c,self.uniq)]
            else:
                self.call_dict[a+coef] = [(float(a+coef),b,c,self.uniq)]
            if (self.show_messages):
                print ('calling in %s:%s:%s.%s - ' % (int(a/60/60),int(a/60)%60,int(a)%60,int(a*1000)%1000)), datetime.utcnow() + timedelta(seconds=a)
            self.uniq = self.uniq + 1
            self.mutex.release()

        self._reactor_callLater = getattr(reactor,'callLater')
        setattr(reactor, 'callLater', callLaterMy)

        self.year_array = [0]*(365*24)
        self.start_time = time()
        def send_event_hook_my(a):
            #print 'send_event_hook %s on %s' % (a, datetime.fromtimestamp(time()))
            ct = int ((time() - self.start_time) / 60 / 60)
            #print 'send_event_hook %s on %s' % (a, datetime.fromtimestamp(time()))
            if (ct >= (365*24)):
                return
            if (a == 'nowDark'):
                assert (self.year_array[ct] & 1) == 0, "nowDark duplicate"
                self.year_array[ct] = self.year_array[ct] | 1
            if (a == 'nowLight'):
                assert (self.year_array[ct] & 2) == 0, "nowLight duplicate"
                self.year_array[ct] = self.year_array[ct] | 2
            if (a == 'nowNight'):
                assert (self.year_array[ct] & 4) == 0, "nowNight duplicate"
                self.year_array[ct] = self.year_array[ct] | 4
            if (a == 'nowDay'):
                assert (self.year_array[ct] & 8) == 0, "nowDay duplicate"
                self.year_array[ct] = self.year_array[ct] | 8
            if (a == 'nowTwilight'):
                assert (self.year_array[ct] & 16) == 0, "nowTwilight duplicate"
                self.year_array[ct] = self.year_array[ct] | 16
            if (a == 'nowNotTwilight'):
                assert (self.year_array[ct] & 32) == 0, "nowNotTwilight duplicate"
                self.year_array[ct] = self.year_array[ct] | 32
            if (a == 'nowDawn'):
                assert (self.year_array[ct] & 64) == 0, "nowDawn duplicate"
                self.year_array[ct] = self.year_array[ct] | 64
            if (a == 'nowNotDawn'):
                assert (self.year_array[ct] & 128) == 0, "nowNotDawn duplicate"
                self.year_array[ct] = self.year_array[ct] | 128
            if (a == 'nowDusk'):
                assert (self.year_array[ct] & 256) == 0, "nowDusk duplicate"
                self.year_array[ct] = self.year_array[ct] | 256
            if (a == 'nowNotDusk'):
                assert (self.year_array[ct] & 512) == 0, "nowNotDusk duplicate"
                self.year_array[ct] = self.year_array[ct] | 512
        self.send_event_hook_old = getattr(self,'send_event_hook')
        setattr(self, 'send_event_hook', send_event_hook_my)

    def finish_tests(self):
        setattr(reactor, 'callLater', self._reactor_callLater)
        setattr(self, 'send_event_hook', self.send_event_hook_old)

    def run_inner_tests_chk_year(self, set_olddt, set_newdt, lat, lon):
        print '************check year: lat = %s, lon = %s *********************' % (lat,lon)

        globals()['time'] = lambda:t
        self.obs.lat = lat
        self.obs.lon = lon
        self.obsTwilight.lat = lat
        self.obsTwilight.lon = lon

        #        globals()['datetime'] = old_datetime
        set_olddt()
        midnight_utc = datetime.utcnow().date()
        midday_utc = datetime.utcnow().date() + timedelta(hours=12)
        #        globals()['datetime'] = DateTime
        set_newdt()
        t = CalTimegm (midnight_utc.timetuple())

        err = 0
        print 'Year check results (. - ok, X - should be day but night, x - should be night):[', midnight_utc,']',
        for i in range (0,366): #check night is night and day is day
            #midnight
            self._CalcDayNight()
            if (self.isNight): print '.',
            else:
                print 'x',
                err = err + 1
            t = t + 60*60*12
            #midday
            self._CalcDayNight()
            if (self.isDay): print '.',
            else:
                print 'X',
                err = err + 1
            t = t + 60*60*12

        print 'Errors:', err

        # parameters: latm lon, date that day, twilight begin time, sunrise, sunset, twilight end time
    def table_check(self,lat,lon,dt,twb,psr,nss,twe,msg,sun_hor='0'):
        print 'checking table times for ', msg
        print 'lat = %s, lon = %s, dt = %s, twb = %s, psr = %s, nss = %s, twe = %s, horizon correction = %s' % (lat,lon,dt,twb,psr,nss,twe,sun_hor)
        d = lambda x:datetime.strptime(x,'%Y/%m/%d %H:%M:%S')
        t = CalTimegm(d(dt).timetuple())
        globals()['time'] = lambda:t

        #to check tables we should regulate pressure
        self.obs.temp = 0
        self.obs.pressure = 0
        self.obs.lat = lat
        self.obs.lon = lon
        self.obs.horizon = sun_hor
        self.obsTwilight.temp = 0
        self.obsTwilight.pressure = 0
        self.obsTwilight.horizon = '-6'
        self.obsTwilight.lat = lat
        self.obsTwilight.lon = lon

        err_ss = self.sunset () - CalTimegm(d(nss).timetuple())
        err_twe = self.sunset_twilight () - CalTimegm(d(twe).timetuple())
        assert (abs(err_ss) < 120), "time skew is more than 2 minutes for sunset (%s) calculated(lt) = %s should be(lt) = %s" % (msg,datetime.fromtimestamp(self.sunset()),datetime.fromtimestamp(CalTimegm(d(nss).timetuple())))
        assert (abs(err_twe) < 120), "time skew is more than 2 minutes for twilight finish (%s) calculated(lt) = %s should be(lt) = %s" % (msg,
                                                                                                                                           datetime.fromtimestamp(self.sunset_twilight ()),
                                                                                                                                           datetime.fromtimestamp(CalTimegm(d(twe).timetuple())))

        err_sr = CalTimegm(self._previous_rising(self.obs,ephem.Sun()).tuple()) - CalTimegm(d(psr).timetuple())
        err_twb = CalTimegm(self._previous_rising(self.obsTwilight,ephem.Sun(),use_center=True).tuple()) - CalTimegm(d(twb).timetuple())

        assert (abs(err_sr) < 120), "time skew is more than 2 minutes for sunrise (%s)" % msg
        assert (abs(err_twb) < 120), "time skew is more than 2 minutes for twilight start (%s)" % msg
        print 'table check passed'
        self.obs.pressure = 1010
        self.obsTwilight.pressure = 1010
        self.obs.horizon='0'
        self.obs.temp = 15
        self.obsTwilight.temp = 15
    def run_inner_tests(self):
        print self.obs
        print self.obsTwilight
        print 'time()', time()
        print 'sr', self.sunrise()
        print 'ss', self.sunset()
        print 'srt', self.sunrise_twilight()
        print 'sst', self.sunset_twilight()
        assert (self.sunrise()>time()),"next rise after current time"
        assert (self.sunset()>time()),"next set after current time"
        assert (self.sunrise_twilight()>time()),"next twilight rise after current time"
        assert (self.sunset_twilight()>time()),"next twilight set after current time"

        print '************Year check midnights********************'
        old_time=globals()['time']
        old_datetime = globals()['datetime']
        class DateTime(datetime):
            @staticmethod
            def utcnow():
                return datetime.utcfromtimestamp(time())
            @staticmethod
            def now():
                return datetime.fromtimestamp(time())
            def timetuple(self):
                return(self.year, self.month, self.day, self.hour, self.minute, self.second + self.microsecond / 1000000.0)
        globals()['datetime'] = DateTime
        globals()['time'] = lambda:t

        print '************adding day*********************'

        globals()['datetime'] = old_datetime
        t = CalTimegm (datetime.utcnow().timetuple()) + 24*60*60
        globals()['datetime'] = DateTime
        print 'time()', time()
        print 'sr', self.sunrise()
        print 'ss', self.sunset()
        print 'srt', self.sunrise_twilight()
        print 'sst', self.sunset_twilight()

        def _set_dt(dt):
            globals()['datetime'] = dt

        set_olddt = lambda:_set_dt(old_datetime)
        set_newdt = lambda:_set_dt(DateTime)

        #Greenwich ecuator
        self.run_inner_tests_chk_year(set_olddt, set_newdt, '0', '0')

        #Murmansk lat
        self.run_inner_tests_chk_year(set_olddt, set_newdt, '69', '0')

        #near north pole
        #        self.run_inner_tests_chk_year(set_olddt, set_newdt, '89:30', '0')

        #check Atlanta
        self.obs.lat = '33.8'
        self.obs.lon = '-84.4'
        self.obsTwilight.lat = '33.8'
        self.obsTwilight.lon = '-84.4'
        t = CalTimegm (datetime (2009,9,6,17,0).timetuple())

        globals()['time'] = lambda:t #renew closure

        print '************table check********************'

        self.table_check('33.8','-84.4','2009/09/06 17:00:00','2009/09/06 10:50:00','2009/09/06 11:15:00','2009/09/06 23:56:00','2009/09/07 00:21:00','Atlanta','-0:34')
        #        self.table_check('68.95','33.1','2013/08/12 12:00:00','2013/08/11 22:18:13','2013/08/12 00:44:48','2013/08/12 19:03:14','2013/08/12 21:10:48','Murmansk','-0:50')

        print '************callLater check********************'

        self.obs.lat = '33.8'
        self.obs.lon = '-84.4'
        self.obs.pressure = 0
        self.obs.temp = 0
        self.obs.pressure = 0
        self.obs.horizon = '-0:34'
        self.obsTwilight.lat = '33.8'
        self.obsTwilight.lon = '-84.4'
        self.obsTwilight.pressure = 0
        self.obsTwilight.temp = 0
        self.obsTwilight.horizon = '-6:0'
        self.mutex.acquire()
        self.call_dict = {} #reset call array
        self.mutex.release()
        #set some timw point (now will be good enough!)
        globals()['datetime'] = old_datetime
        t = CalTimegm (datetime.utcnow().timetuple())
        globals()['datetime'] = DateTime
        globals()['time'] = lambda:t #renew closure

        self.year_array = [0]*(365*24)

        self.init(self._Loader)

        #        print self.call_arr
        #print self.call_dict

        #iterate callLater events
        old_events = []
        self.start_time = time()

        self.show_messages = False
        for i in range (0,2000):
            self.mutex.acquire()
            #print "On %s iteration there are %s later calls" % (i, len(self.call_dict))
            def prnDict():
                for s in self.call_dict.keys():
                    print 'dict[%s]:' % datetime.fromtimestamp(s)
                    c_l = self.call_dict[s]
                    for (a,b,c,d) in c_l:
                        #print 'check ', c
                        print "%s --- func = %s, param = %s" % (d,b,c)
            #prnDict()
            assert (len(self.call_dict) > 0), 'no more laterCalls on %s iteration' % i
            t_corr_l = list(self.call_dict.keys())
            assert (t_corr_l[0] > 0), "bad value of seconds in laterCall: %s" % t_corr_l[0]

            #check dict (there should not be fully duplicate events (or should?))
            to_call_list = []
            #print 'dict check: ', t_corr_l
            for s in self.call_dict.keys():
                #print 'check second = %s' % s
                c_l = self.call_dict[s]
                to_call_list = to_call_list + c_l
                for (a,b,c,d) in c_l:
                    #print 'check ', c
                    assert ((a,b,c) not in old_events), "laterCall is duplicated:%s,%s,%s (u=%s)" % (a,b,c,d)
                    old_events = old_events + [(a,b,c)]
            self.call_dict = {} #clear call dict

            #print 'dict calls'
            self.mutex.release()
            #call functions on that time
            old_t = t
            for (tm,func,par,u) in to_call_list:
                t = tm
                if par is None:
                    func()
                else:
                    func(par)
            t = old_t

        ya = self.year_array
        print "Year table:"
        print " 0-23 - hour number (utc); for each hour events(sent messages) are shown: R/L - Dark/Light, N/D - Night/Day, W/w - Twilight/NotTwilight, A/a - Dawn/NotDawn, U/u - Dusk/NotDusk."
        print " Upper left corner of table is current hour. "
        print "0     1     2     3     4     5     6     7     8     9    10    11    12    13    14    15    16    17    18    19    20    21    22    23"
        rc = [0]*10
        for li in [ya[i:i+24] for i in range(0,len(ya),24)]:
            for c in li:
                for p in range(0,10):
                    if (c & (1 << p) > 0):
                        rc [p] = rc [p] + 1
                l = ''
                if (c & 1) > 0 : l = l + 'R'
                elif (c & 2) > 0 : l = l + 'L'
                else: l = l + ' '

                if (c & 4) > 0 : l = l + 'N'
                elif (c & 8) > 0 : l = l + 'D'
                else: l = l + ' '

                if (c & 48) == 48: l = l + '+'
                elif (c & 16) > 0 : l = l + 'W'
                elif (c & 32) > 0 : l = l + 'w'
                else: l = l + ' '

                if (c & 192) == 192: l = l + '/'
                elif (c & 64) > 0 : l = l + 'A'
                elif (c & 128) > 0 : l = l + 'a'
                else: l = l + ' '

                if (c & 768) == 768: l = l + '\\'
                elif (c & 256) > 0 : l = l + 'U'
                elif (c & 512) > 0 : l = l + 'u'
                else: l = l + ' '
                print "%s"%l,
            print

        print 'indeces in result count: 0-Dark,1-Light,2-Night,3-Day,4-Twilight,5-NotTwi,6-Dawn,7-NotDawn,8-Dusk,9-NotDusk'
        print 'result count = ', rc
        globals()['time']=old_time
        globals()['datetime'] = old_datetime
        self.finish_tests() #revert reactor.callLater patch