"""Defines the sensors for amt-8000."""
from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.alarm_control_panel import AlarmControlPanelEntity, AlarmControlPanelEntityFeature

from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
)


from .const import DOMAIN
from .coordinator import AmtCoordinator
from .isec2.client import Client as ISecClient


LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0
SCAN_INTERVAL = timedelta(seconds=10)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the entries for amt-8000."""
    # Accedemos al coordinador que ya fue creado y guardado en hass.data por __init__.py
    coordinator: AmtCoordinator = hass.data[DOMAIN][config_entry.entry_id]['coordinator']
    isec_client = coordinator.isec_client # Obtenemos el cliente del coordinador
    password = coordinator.password # Obtenemos la contraseña del coordinador
    
    LOGGER.info('setting up alarm control panel...')
    sensors = [AmtAlarmPanel(coordinator, isec_client, password)]
    async_add_entities(sensors)


class AmtAlarmPanel(CoordinatorEntity, AlarmControlPanelEntity):
    """Define a Amt Alarm Panel."""

    _attr_supported_features = (
          AlarmControlPanelEntityFeature.ARM_AWAY
        # | AlarmControlPanelEntityFeature.ARM_NIGHT
        # | AlarmControlPanelEntityFeature.ARM_HOME
        | AlarmControlPanelEntityFeature.TRIGGER
    )

    def __init__(self, coordinator, isec_client: ISecClient, password):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.status = None
        self.isec_client = isec_client
        self.password = password
        self._is_on = False

    @callback
    def _handle_coordinator_update(self) -> None:
        """Update the stored value on coordinator updates."""
        self.status = self.coordinator.data
        self.async_write_ha_state()

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        return "AMT-8000"

    @property
    def unique_id(self) -> str | None:
        """Return a unique ID."""
        return "amt8000.control_panel"

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self.status is not None and self.coordinator.last_update_success

    @property
    def state(self) -> str:
        """Return the state of the entity."""
        if self.status is None:
            return "unknown"

        if self.status.get('siren') is True:
            return "triggered"

        current_status = self.status.get("status")
        if current_status and current_status.startswith("armed_"):
          self._is_on = True
        else:
          self._is_on = False

        return current_status if current_status else "unknown"

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return the state attributes."""
        if self.status is None:
            return None
        
        return {
            "model": self.status.get("model", "unknown"),
            "version": self.status.get("version", "unknown"),
            "zones_firing": self.status.get("zonesFiring", False),
            "zones_closed": self.status.get("zonesClosed", False),
            "siren_active": self.status.get("siren", False),
            "battery_status": self.status.get("batteryStatus", "unknown"),
            "tamper_detected": self.status.get("tamper", False),
        }

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device information."""
        # Esta es la parte clave para agrupar las entidades bajo un dispositivo
        return {
            "identifiers": {(DOMAIN, self.coordinator.config_entry.entry_id)}, # Identificador único para el dispositivo
            "name": "AMT-8000 Alarm Panel", # Nombre del dispositivo
            "manufacturer": "Intelbras",
            "model": self.coordinator.data.get("model", "AMT-8000"),
            "sw_version": self.coordinator.data.get("version", "Unknown"),
        }

    def _arm_away(self):
        """Arm AMT in away mode"""
        self.isec_client.connect()
        self.isec_client.auth(self.password)
        result = self.isec_client.arm_system(0)
        self.isec_client.close()
        if result == "armed":
            return 'armed_away'

    def _disarm(self):
        """Arm AMT in away mode"""
        self.isec_client.connect()
        self.isec_client.auth(self.password)
        result = self.isec_client.disarm_system(0)
        self.isec_client.close()
        if result == "disarmed":
            return 'disarmed'


    def _trigger_alarm(self):
        """Trigger Alarm"""
        self.isec_client.connect()
        self.isec_client.auth(self.password)
        result = self.isec_client.panic(1)
        self.isec_client.close()
        if result == "triggered":
            return "triggered"


    def alarm_disarm(self, code=None) -> None:
        """Send disarm command."""
        self._disarm()

    async def async_alarm_disarm(self, code=None) -> None:
        """Send disarm command."""
        await self.hass.async_add_executor_job(self._disarm)

    def alarm_arm_away(self, code=None) -> None:
        """Send arm away command."""
        self._arm_away()

    async def async_alarm_arm_away(self, code=None) -> None:
        """Send arm away command."""
        await self.hass.async_add_executor_job(self._arm_away)

    def alarm_trigger(self, code=None) -> None:
        """Send alarm trigger command."""
        self._trigger_alarm()

    async def async_alarm_trigger(self, code=None) -> None:
        """Send alarm trigger command."""
        await self.hass.async_add_executor_job(self._trigger_alarm)

    @property
    def is_on(self) -> bool | None:
        """Return True if entity is on."""
        return self._is_on

    def turn_on(self, **kwargs: Any) -> None:
        self._arm_away()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the entity on."""
        await self.hass.async_add_executor_job(self._arm_away)

    def turn_off(self, **kwargs: Any) -> None:
        """Turn the entity off."""
        self._disarm()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the entity off."""
        await self.hass.async_add_executor_job(self._disarm)

