"""Defines the alarm control panel for amt-8000.""" # Título más preciso

from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.alarm_control_panel import (
    AlarmControlPanelEntity,
    AlarmControlPanelEntityFeature,
    AlarmControlPanelState,
)
from homeassistant.helpers.device_registry import DeviceInfo # <-- Asegúrate de que esto esté importado
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
)


from .const import DOMAIN
from .coordinator import AmtCoordinator
from .isec2.client import Client as ISecClient # Mantener esta importación para las acciones

LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0
SCAN_INTERVAL = timedelta(seconds=10)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the AMT-8000 alarm control panel."""
    # Accedemos al coordinador y config que ya fueron creados y guardados en hass.data por __init__.py
    data = hass.data[DOMAIN][config_entry.entry_id]
    config = data["config"] # Obtener la configuración (host, port, password)
    coordinator: AmtCoordinator = data["coordinator"] # Obtener la instancia del coordinador

    # El isec_client para las acciones de armado/desarmado/pánico.
    # Podríamos usar coordinator.client, pero tu estructura actual crea y cierra
    # un cliente para cada acción. Mantendré esa lógica por ahora,
    # aunque lo ideal sería centralizar la conexión en el coordinador.
    isec_client_for_actions = ISecClient(config["host"], config["port"])
    password = config["password"] # Obtener la contraseña desde la config

    LOGGER.info('setting up alarm control panel...')
    
    # Pasa el 'host' desde la configuración para el DeviceInfo
    sensors = [AmtAlarmPanel(coordinator, isec_client_for_actions, password, config["host"])]
    async_add_entities(sensors)


class AmtAlarmPanel(CoordinatorEntity, AlarmControlPanelEntity):
    """Define a Amt Alarm Panel."""

    _attr_supported_features = (
          AlarmControlPanelEntityFeature.ARM_AWAY
        | AlarmControlPanelEntityFeature.TRIGGER
    )
    _attr_has_entity_name = True # Permite que HA use el nombre por defecto o el que definamos en __init__
    _attr_name = "Alarm Panel" # Nombre de la entidad. Home Assistant lo generará como "AMT-8000 Alarm Panel"

    def __init__(self, coordinator: AmtCoordinator, isec_client: ISecClient, password: str, host: str) -> None:
        """Initialize the alarm panel."""
        super().__init__(coordinator)
        self.isec_client = isec_client
        self.password = password
        self._host = host # Guardar host para DeviceInfo

        # Usamos el entry_id del coordinador para asegurar un unique_id único para el panel
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_alarm_panel"

        # Inicializa _attr_state. Esto se actualizará con los datos del coordinador.
        self._attr_state = AlarmControlPanelState.UNKNOWN

        # Aquí no hay _is_on, usaremos self._attr_state directamente
        # No necesitas _is_on si el estado se deriva del coordinador

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        # Define el dispositivo principal al que se asociarán todas las entidades de la integración
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.config_entry.entry_id)}, # ID único del dispositivo
            name="AMT-8000 Alarm Panel", # Nombre visible del dispositivo en Home Assistant
            manufacturer="Intelbras",
            model=self.coordinator.data.get("panel", {}).get("model", "AMT-8000"), # Obtener del coordinador
            sw_version=self.coordinator.data.get("panel", {}).get("version", "Unknown"), # Obtener del coordinador
            via_device=(DOMAIN, self._host), # Opcional: Puede agrupar dispositivos por el host si hay varios paneles
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        # El coordinador ya obtiene los datos, solo necesitamos mapearlos al estado del panel de alarma
        current_status = self.coordinator.data.get("panel", {})
        
        # Mapea los estados de la alarma
        if current_status.get("inAlarm"):
            self._attr_state = AlarmControlPanelState.ALARMING
        elif current_status.get("armed"):
            self._attr_state = AlarmControlPanelState.ARMED_AWAY
        elif current_status.get("partiallyArmed"):
             # Esto podría ser ARMED_HOME o ARMED_NIGHT dependiendo de tu preferencia
            self._attr_state = AlarmControlPanelState.ARMED_HOME # O ARMED_NIGHT
        elif current_status.get("disarmed"):
            self._attr_state = AlarmControlPanelState.DISARMED
        else:
            self._attr_state = AlarmControlPanelState.UNKNOWN

        # Asegúrate de que el estado se actualice en Home Assistant
        self.async_write_ha_state()

    @property
    def code_format(self) -> None:
        """Return one of the alarm code formats."""
        # La alarma no usa código en las acciones directas del protocolo
        return None

    def _disarm(self) -> str:
        """Internal disarm command (synchronous)."""
        try:
            self.isec_client.connect()
            self.isec_client.auth(self.password)
            result = self.isec_client.disarm_system(0)
            LOGGER.debug("Disarm result: %s", result)
            return result
        except Exception as e:
            LOGGER.error("Error during disarm: %s", e)
            return "error"
        finally:
            if hasattr(self.isec_client, 'client') and self.isec_client.client is not None:
                self.isec_client.close()

    async def async_alarm_disarm(self, code=None) -> None:
        """Send disarm command."""
        # Ejecuta la función síncrona en el pool de threads de Home Assistant
        result = await self.hass.async_add_executor_job(self._disarm)
        if result == "disarmed":
            await self.coordinator.async_request_refresh() # Forzar una actualización de estado

    def _arm_away(self) -> str:
        """Internal arm away command (synchronous)."""
        try:
            self.isec_client.connect()
            self.isec_client.auth(self.password)
            result = self.isec_client.arm_system(0)
            LOGGER.debug("Arm away result: %s", result)
            return result
        except Exception as e:
            LOGGER.error("Error during arm away: %s", e)
            return "error"
        finally:
            if hasattr(self.isec_client, 'client') and self.isec_client.client is not None:
                self.isec_client.close()

    async def async_alarm_arm_away(self, code=None) -> None:
        """Send arm away command."""
        result = await self.hass.async_add_executor_job(self._arm_away)
        if result == "armed":
            await self.coordinator.async_request_refresh() # Forzar una actualización de estado

    def _trigger_alarm(self) -> str:
        """Internal alarm trigger command (synchronous)."""
        try:
            self.isec_client.connect()
            self.isec_client.auth(self.password)
            result = self.isec_client.panic(1)
            LOGGER.debug("Trigger alarm result: %s", result)
            return result
        except Exception as e:
            LOGGER.error("Error during alarm trigger: %s", e)
            return "error"
        finally:
            if hasattr(self.isec_client, 'client') and self.isec_client.client is not None:
                self.isec_client.close()

    async def async_alarm_trigger(self, code=None) -> None:
        """Send alarm trigger command."""
        result = await self.hass.async_add_executor_job(self._trigger_alarm)
        if result == "triggered":
            await self.coordinator.async_request_refresh() # Forzar una actualización de estado

    # Los siguientes métodos turn_on/turn_off/is_on son más apropiados para un switch o luz.
    # Para un panel de alarma, se usan los métodos alarm_arm_away, alarm_disarm, etc.
    # Si Home Assistant los usa internamente, deberían llamar a las funciones _arm_away / _disarm correspondientes.
    # Voy a remover _is_on y reemplazar turn_on/turn_off por llamadas a los métodos de alarma.

    @property
    def state(self) -> str | None:
        """Return the state of the alarm control panel."""
        return self._attr_state
