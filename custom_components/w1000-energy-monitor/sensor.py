"""Support for W1000 portal"""
import logging
import unicodedata

from homeassistant.components.sensor import SensorEntity

from . import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    if discovery_info is None:
        return

    w1kPortal = hass.data[DOMAIN]
    sensors = []
    
    for report in w1kPortal.reports:
        sensors.append(w1kSensor(report, w1kPortal ))

    async_add_entities(sensors)


class w1kSensor(SensorEntity):
    _attr_should_poll = False

    def __init__(self, name, w1k_portal):
        self._name = name
        self._w1k_portal = w1k_portal
        self._icon = "mdi:flash"
        self._attributes = {}

        self._attr_name = f"W1000 {self._name.capitalize()}"
        self._attr_unique_id = f"w1k_{unicodedata.normalize('NFKD',self._name).lower()}"

    @property
    def icon(self):
        return self._icon

    @property
    def extra_state_attributes(self):
        return self._attributes

    async def async_update(self):
        data = self._w1k_portal.get_data(self._name)
        _LOGGER.debug(data)
        
        if data is not None:
            self._attr_native_value = round(float(data.get("state")), 1)
            self._attributes = data.get("attributes")
            self._attr_native_unit_of_measurement = data.get("unit")

    def update_callback(self):
        self.async_schedule_update_ha_state(True)

    async def async_added_to_hass(self):
        self._w1k_portal.add_update_listener(self)
