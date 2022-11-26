"""
    Support for W1000 energy portal
    
    Thanks to https://github.com/amargo/ for the login session ideas
    
"""
import logging

import aiohttp
import voluptuous as vol

from homeassistant.core import callback, HomeAssistant
from homeassistant.helpers import discovery
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.event import async_track_utc_time_change
from homeassistant.const import (
    CONF_SCAN_INTERVAL,
    ENERGY_KILO_WATT_HOUR
)
import homeassistant.util.dt as dt_util

from bs4 import BeautifulSoup
import requests, yaml, re
from datetime import datetime, timedelta, timezone

from homeassistant.components.recorder.models import StatisticData, StatisticMetaData
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    get_last_statistics,
    async_import_statistics
)

_LOGGER = logging.getLogger(__name__)

DOMAIN = "w1000-energy-monitor"

CONF_ENDPOINT = "url"
CONF_USERNAME = "login_user"
CONF_PASSWORD = "login_pass"
CONF_REPORTS = "reports"
CONF_INTERVAL = "scan_interval"

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Required(CONF_USERNAME): cv.string,
                vol.Required(CONF_PASSWORD): cv.string,
                vol.Required(CONF_REPORTS): cv.string,
                vol.Optional(CONF_INTERVAL, default=60): cv.positive_int, # minutes
                vol.Optional(CONF_ENDPOINT, default="https://energia.eon-hungaria.hu/W1000"): cv.string,
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)

async def async_setup(hass, config):
    scan_interval = config[DOMAIN][CONF_INTERVAL]

    monitor = w1k_Portal(hass, config[DOMAIN][CONF_USERNAME], config[DOMAIN][CONF_PASSWORD], config[DOMAIN][CONF_ENDPOINT], config[DOMAIN][CONF_REPORTS] )
    hass.data[DOMAIN] = monitor

    now = dt_util.utcnow()
    async_track_utc_time_change(
        hass,
        monitor.update,
        minute=range(now.minute % scan_interval, 60, scan_interval),
        second=now.second,
    )

    hass.async_create_task(
        discovery.async_load_platform(hass, "sensor", DOMAIN, {}, config)
    )

    return True



class w1k_API:

    def __init__(self, username, password, endpoint, reports):

        self.username = username
        self.password = password
        self.account_url = endpoint+"/Account/Login"
        self.profile_data_url = endpoint + "/ProfileData/ProfileData"
        self.lastlogin = None
        self.reports = [ x.strip() for x in reports.split(",") ]
        self.session = None
        self.start_values = {'consumption': None, 'production': None}

    async def request_data(self, ssl=True):
        
        ret = {}
        for report in self.reports:
            _LOGGER.debug("reading report "+report)
            retitem = await self.read_reportname(report)
            ret[report] = retitem[0]
        
        return ret
        

    def mysession(self):
        if self.session:
            return self.session
    
        jar = aiohttp.CookieJar(unsafe=True)
        self.session = aiohttp.ClientSession(cookie_jar=jar)
        return self.session

    async def login(self, ssl=False):
        try:
            session = self.mysession()
            async with session.get(
                url=self.account_url, ssl=ssl
            ) as resp:
                content = (await resp.content.read()).decode("utf8")
                status = resp.status
            
            index_content = BeautifulSoup(content, "html.parser")
            dome = index_content.select('#pg-login input[name=__RequestVerificationToken]')[0]
            self.request_verification_token = dome.get("value")

            payload = {
                "__RequestVerificationToken": self.request_verification_token,
                "UserName": self.username,
                "Password": self.password,
            }
            
            header = {}
#            header["User-Agent"] =  "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/106.0.0.0 Safari/537.36"
#            header["Referer"] = self.account_url

            async with session.post(
                url=self.account_url, data=payload, ssl=ssl
            ) as resp:
                content = (await resp.content.read()).decode("utf8")
                status = resp.status
            
            _LOGGER.debug("resp status http "+str(status) )
            match = re.findall( r'W1000.start\((.+)sessionTimeout', content.replace("\n", " ") )
            
            if not status == 200:
                _LOGGER.error("Login failed.")
                _LOGGER.debug("HTML page: "+content)
                _LOGGER.debug("Index page was: "+index_content)
                return False
                
            if len(match)==0:
                _LOGGER.error("could not find session data. invalid or locked account?")
                _LOGGER.debug("HTML page: "+content)
                return False
            
            respob = yaml.safe_load(match[0]+"}")
            self.currentUser = respob['currentUser']
            self.workareas = respob['workareas']
            self.lastlogin = datetime.utcnow()
            
            for workarea in self.workareas:
                for window in workarea['windows']:
                    _LOGGER.debug("found report "+window['name']+" in workarea "+workarea['name'] )

            return True
            
        except Exception as ex:
            availability = 'Offline'
            _LOGGER.error("exception at login")
            print(datetime.now(), "Error retrive data from {0}.".format(str(ex)))
            
    
    
    async def read_reportname(self, reportname: str):
        loginerror = False
        if not self.lastlogin or self.lastlogin + timedelta(minutes=10) < datetime.utcnow():
            loginerror = not await self.login()
        
        if loginerror:
            return [None]
        
        for workarea in self.workareas:
            for window in workarea['windows']:
                if window['name'] == reportname:
                    return await self.read_reportid( int(window['reportid']), reportname )
        
        _LOGGER.error("report "+reportname+" not found")
        return [None]
        

    async def read_reportid(self, reportid: int, reportname: str, ssl=True):
        now = datetime.utcnow()

        loginerror = False
        if not self.lastlogin or self.lastlogin + timedelta(hours=1) < datetime.utcnow():
            loginerror = not await self.login()
        
        if loginerror:
            return None
            
        since = (now + timedelta(days=-2)).strftime("%Y-%m-%dT00:00:00")    #change this '-2' if you want a larger time window
        until = (now + timedelta(days=0 )).strftime("%Y-%m-%dT%H:00:00")
        
        params = {
            "page": 1,"perPage": 96*3,                                      #also you have to change '*3' (this could be in config)
            "reportId": reportid,
            "since": since,
            "until": until,
            "_": (now - timedelta(hours=3)).strftime("%s557")
        }
        
        session = self.mysession()
        
        async with session.get(
            url=self.profile_data_url, data=params, ssl=ssl
        ) as resp:
            jsonResponse = await resp.json()
            status = resp.status
        
        if status == 200:
            lastvalue = None
            unit = None
            lasttime = None
            ret = []
            statistic_id = f"sensor.w1000_{reportname}"
            statistics = []
            delta_values = False
            for window in jsonResponse:
                unit = window['unit']
                hourly_sum = None
                for data in window['data']:
                    value = data['value']
                    if value > 0:
                        lastvalue = round(value,1)
                        lasttime = data['time']
                    if window['data'].index(data) == 1:                                 #first element in list will be the starting data
                        if window['name'].find(":1.8.0") > 0:                           #we will add the delta values, separately for consumption and production
                            if self.start_values['consumption'] is None:
                                self.start_values['consumption'] = value
                        if window['name'].find(":2.8.0") > 0:
                            if self.start_values['production'] is None:
                                self.start_values['production'] = value
                        if window['name'].find("+A") > 0:
                            delta_values = True
                            if self.start_values['consumption'] is not None:
                                hourly_sum = self.start_values['consumption']
                        if window['name'].find("-A") > 0:
                            delta_values = True
                            if self.start_values['production'] is not None:
                                hourly_sum = self.start_values['production']
                        dt=datetime.fromisoformat(data['time']+"+02:00").astimezone()   #TODO: needs to calculate DST
                        if delta_values:                                                #only delta values has to be cummulated
                            if dt.minute == 0:
                                if hourly_sum is not None:
                                    if hourly_sum > 0:
                                        statistics.append(
                                            StatisticData(
                                                start=dt,
                                                state=round(hourly_sum,3),
                                                sum=round(hourly_sum,3)
                                            )
                                        )
                                        #_LOGGER.debug(f"data: {dt} {hourly_sum}")
                                        hourly_sum += value
                                else:
                                    hourly_sum = value
                            else:
                                if hourly_sum is None:
                                    hourly_sum = value
                                else:
                                    hourly_sum += value
                        else:
                            statistics.append(
                                StatisticData(
                                    start=dt,
                                    state=round(value,1),
                                    sum=round(value,1)
                                )
                            )

                ret.append( {'curve':window['name'], 'last_value':lastvalue, 'unit':window['unit'], 'last_time':lasttime} )
                metadata = StatisticMetaData(
                    has_mean=False,
                    has_sum=True,
                    name="w1000_"+reportname,
                    source='recorder',
                    statistic_id=statistic_id,
                    unit_of_measurement=ENERGY_KILO_WATT_HOUR,
                )
                _LOGGER.debug("import statistic: "+statistic_id+" count: "+str(len(statistics)))
                async_import_statistics(self._hass, metadata, statistics)
        else:
            _LOGGER.error("error http "+str(status) )
            print( jsonResponse )

        return ret








class w1k_Portal(w1k_API):

    def __init__(self, hass, username, password, endpoint, reports):
        super().__init__(username, password, endpoint, reports)
        self._hass = hass
        self._data = {}
        self._update_listeners = []

    def get_data(self, name):
        return self._data.get(name)

    async def update(self, *args):
        json = await self.request_data()
        self._data = self._prepare_data(json)
        self._notify_listeners()

    def _prepare_data(self, json):
        out = {}
        for report in json:
            dta = json[report]
            if dta and 'curve' in dta:
                out[report] = { 'state': dta['last_value'], 'unit':dta['unit'], 'attributes':{
                    'curve':dta['curve'],
                    'generated':dta['last_time'],
                    'state_class': 'measurement',
                }}
                if dta['unit'].endswith('W'):
                    out[report]['attributes']['device_class'] = 'power'
                if dta['unit'].endswith('Wh'):
                    out[report]['attributes']['device_class'] = 'energy'
        return out

    def add_update_listener(self, listener):
        self._update_listeners.append(listener)
        _LOGGER.debug(f"registered sensor: {listener.entity_id}")
        listener.update_callback()


    def _notify_listeners(self):
        for listener in self._update_listeners:
            listener.update_callback()
        _LOGGER.debug("Notifying all listeners")
