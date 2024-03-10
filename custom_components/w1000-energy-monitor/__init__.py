"""
    Support for W1000 energy portal
    
    Thanks to https://github.com/amargo for the login session ideas
    Thanks to https://github.com/wrobi for historical data (+A/-A statistics)
    
"""
import logging

import aiohttp
import voluptuous as vol
import unicodedata

from homeassistant.core import callback, HomeAssistant
from homeassistant.helpers import discovery
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.event import async_track_utc_time_change
from homeassistant.const import (
    CONF_SCAN_INTERVAL,
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
import json
from os.path import exists

_LOGGER = logging.getLogger(__name__)

DOMAIN = "w1000-energy-monitor"

CONF_ENDPOINT = "url"
CONF_USERNAME = "login_user"
CONF_PASSWORD = "login_pass"
CONF_REPORTS = "reports"

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Required(CONF_USERNAME): cv.string,
                vol.Required(CONF_PASSWORD): cv.string,
                vol.Required(CONF_REPORTS): cv.string,
                vol.Optional(CONF_ENDPOINT, default="https://energia.eon-hungaria.hu/W1000"): cv.string,
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)


async def async_setup(hass, config):
    monitor = w1k_Portal(hass, config[DOMAIN][CONF_USERNAME], config[DOMAIN][CONF_PASSWORD],
                         config[DOMAIN][CONF_ENDPOINT], config[DOMAIN][CONF_REPORTS])
    hass.data[DOMAIN] = monitor

    now = dt_util.utcnow()
    
    async_track_utc_time_change(
        hass,
        monitor.update,
        hour=[6, 7, 9, now.hour],
        minute=now.minute,
        second=now.second
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
        self.reports = [x.strip() for x in reports.split(",")]
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
            
            _LOGGER.debug("resp status http "+str(status))
            match = re.findall(r'W1000.start\((.+)sessionTimeout', content.replace("\n", " "))
            
            if not status == 200:
                _LOGGER.error("Login failed.")
                _LOGGER.debug("HTML page: "+content)
                _LOGGER.debug("Index page was: "+index_content)
                return False
                
            if len(match) == 0:
                _LOGGER.error("could not find session data. invalid or locked account?")
                _LOGGER.debug("HTML page: "+content)
                return False
            
            respob = yaml.safe_load(match[0]+"}")
            self.currentUser = respob['currentUser']
            self.workareas = respob['workareas']
            self.lastlogin = datetime.utcnow()
            
            for workarea in self.workareas:
                for window in workarea['windows']:
                    _LOGGER.debug("found report "+window['name']+" in workarea "+workarea['name'])

            return True
            
        except Exception as ex:
            availability = 'Offline'
            _LOGGER.exception("exception at login")
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
                    return await self.read_reportid(int(window['reportid']), reportname)
        
        _LOGGER.error("report "+reportname+" not found")
        return [None]

    async def read_reportid(self, reportid: int, reportname: str, ssl=True):
        now = datetime.utcnow()
        hass = self._hass

        loginerror = False
        if not self.lastlogin or self.lastlogin + timedelta(hours=1) < datetime.utcnow():
            loginerror = not await self.login()

        if loginerror:
            return None
            
        since = (now + timedelta(days=-2)).astimezone().strftime("%Y-%m-%dT23:00:00%z")
        until = (now + timedelta(days=0)).astimezone().strftime("%Y-%m-%dT%H:00:00%z")
        
        params = {
            "page": 1,
            "perPage": 96*2,
            "reportId": reportid,
            "since": since,
            "until": until,
            "_": (now - timedelta(hours=3)).strftime("%s557")
        }
        
        session = self.mysession()
        
        test = False    # TODO remove in the future
        
        file = 'w1000_'+reportname+'.json'
        if test and exists(file):
            jsonResponse = json.load(open(file))
            _LOGGER.debug(file+' loaded')
            status = 200
        else:
            async with session.get(
                url=self.profile_data_url, params=params, ssl=ssl
            ) as resp:
                jsonResponse = await resp.json()
                jsonResponse = sorted(jsonResponse, key=lambda k: k['name'], reverse=True)
            status = resp.status

            if status == 200 and test:
                with open(file, 'w', encoding='utf-8') as f:
                    json.dump(jsonResponse, f, ensure_ascii=True, indent=4)
                _LOGGER.debug(file+' saved')

        if status == 200:
            unit = None
            lasttime = None
            lastvalue = None
            ret = []
            sensorname = f'sensor.w1000_'+(
                ''.join(ch for ch in unicodedata.normalize('NFKD', reportname) if not unicodedata.combining(ch)))
            statistic_id = sensorname
            statistics = []
            metadata = []
            haveReport_A = False
            for curve in jsonResponse:
                unit = curve['unit']
                name = curve['name']
                hourly_sum = None
                for data in curve['data']:
                    value = data['value']
                    dt = datetime.fromisoformat(data['time']+"+02:00").astimezone()  # TODO: needs to calculate DST
                    if curve['data'].index(data) == 0:  # first element in list will be the starting data
                        if '1.8.0' in name and value > 0:
                            self.start_values['consumption'] = value
                        if '2.8.0' in name and value > 0:
                            self.start_values['production'] = value
                        if name.endswith("A"):
                            value = 0
                            hourly_sum = None
                            haveReport_A = True
                            if name.endswith("+A"):
                                dailycurve = '1.8.0'
                                hourly_sum = self.start_values['consumption']
                            if name.endswith("-A"):
                                dailycurve = '2.8.0'
                                hourly_sum = self.start_values['production']
                            if hourly_sum is None:
                                _LOGGER.warning(f"{dailycurve} curve is missing. Please add it to your report '{reportname}'")
                            if curve['period'] != 60:
                                _LOGGER.warning('Please set the period value to 60 min in curve settings')
                    if haveReport_A:
                        if hourly_sum is not None:
                            hourly_sum += value
                            statistics.append(
                                StatisticData(
                                    start=dt,
                                    # state=round(value,3),
                                    state=round(hourly_sum, 3),
                                    sum=round(hourly_sum, 3)
                                )
                            )
                            if data['time'] > lasttime:
                                lasttime = data['time']
                                lastvalue = round(hourly_sum, 3)
                    else:
                        if value > 0:
                            lasttime = data['time']
                            lastvalue = round(value, 3)

                if len(statistics) > 0:
                    metadata = StatisticMetaData(
                        has_mean=False,
                        has_sum=True,
                        name="w1000 "+reportname,
                        source='recorder',
                        statistic_id=statistic_id,
                        unit_of_measurement=curve['unit'],
                    )
                    # lastvalue = None
                    _LOGGER.debug("import statistic: "+statistic_id+" count: "+str(len(statistics)))
                
                    try:
                        async_import_statistics(self._hass, metadata, statistics)
                    except Exception as ex:
                        _LOGGER.exception("exception at async_import_statistics '"+statistic_id+"': "+str(ex))

                ret.append({
                    'curve': curve['name'],
                    'last_value': lastvalue,
                    'unit': curve['unit'],
                    'last_time': lasttime
                })

        else:
            _LOGGER.error("error http "+str(status))
            print(jsonResponse)

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
                if '.8.' in dta['curve']:
                    state_class = 'total_increasing'
                else:
                    state_class = 'total'
                
                out[report] = {
                    'state': dta['last_value'],
                    'unit': dta['unit'],
                    'attributes': {
                        'curve': dta['curve'],
                        'generated': dta['last_time'],
                        'state_class': state_class,
                    }
                }
                if dta['unit'].endswith('W') or dta['unit'].endswith('Var'):
                    out[report]['attributes']['device_class'] = 'power'
                if dta['unit'].endswith('Wh') or dta['unit'].endswith('Varh'):
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
