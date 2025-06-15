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
    data = hass.data[DOMAIN][config_entry.entry_id]
    isec_client = ISecClient(data["host"], data["port"])
    coordinator = AmtCoordinator(hass, isec_client, data["password"])
    LOGGER.info('setting up...')
    # coordinator.async_config_entry_first_refresh() # Se recomienda usar esto para la primera actualización
                                                    # en lugar de iniciar con el estado None.
                                                    # Si da problemas de inicio, puedes descomentarlo.
    sensors = [AmtAlarmPanel(coordinator, isec_client, data['password'])]
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
        self.status = None # Al inicio, el estado es None. Se actualiza con el coordinador.
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
        # La entidad estará disponible si el coordinador tiene datos.
        return self.status is not None and self.coordinator.last_update_success

    @property
    def state(self) -> str:
        """Return the state of the entity."""
        if self.status is None:
            return "unknown"

        if self.status.get('siren') is True: # Usar .get() para mayor robustez
            return "triggered"

        # Asegúrate de que 'status' exista y sea un string antes de usar .startswith
        current_status = self.status.get("status")
        if current_status and current_status.startswith("armed_"):
          self._is_on = True
        else:
          self._is_on = False # Importante: si no está armado, _is_on debe ser False

        return current_status if current_status else "unknown"

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return the state attributes."""
        if self.status is None:
            return None
        
        # Mapeamos los datos decodificados del coordinador a atributos de la entidad.
        # Esto incluye todos los campos que tu build_status ya decodifica.
        return {
            "model": self.status.get("model", "unknown"),
            "version": self.status.get("version", "unknown"),
            "zones_firing": self.status.get("zonesFiring", False),
            "zones_closed": self.status.get("zonesClosed", False),
            "siren_active": self.status.get("siren", False), # Renombrado para claridad
            "battery_status": self.status.get("batteryStatus", "unknown"),
            "tamper_detected": self.status.get("tamper", False),
            # Puedes añadir más atributos aquí si descubres más información del protocolo
        }

    # Los métodos de control como _arm_away, _disarm, _trigger_alarm
    # se mantienen igual, ya que ellos ya usan client.connect/auth/close.
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
        # Se actualiza directamente desde el estado decodificado
        return self._is_on

    # Los métodos turn_on y turn_off ya llaman a arm_away y disarm respectivamente
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

