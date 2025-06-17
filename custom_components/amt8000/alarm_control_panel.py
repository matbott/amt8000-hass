"""Defines the alarm control panel for amt-8000."""

from datetime import timedelta
import logging
from typing import Any, Optional

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.alarm_control_panel import (
    AlarmControlPanelEntity,
    AlarmControlPanelEntityFeature,
    AlarmControlPanelState,
    CodeFormat,
)
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
)
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN
from .coordinator import AmtCoordinator
from .isec2.client import Client as ISecClient, CommunicationError

LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0
SCAN_INTERVAL = timedelta(seconds=30)

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the AMT-8000 alarm control panel."""
    data = hass.data[DOMAIN][config_entry.entry_id]
    coordinator: AmtCoordinator = data["coordinator"]
    config = data["config"]

    LOGGER.info("Setting up AMT-8000 alarm control panel...")
    
    # Crear la entidad del panel de alarma
    alarm_panel = AmtAlarmPanel(
        coordinator=coordinator,
        password=config["password"],
        host=config["host"]
    )
    
    async_add_entities([alarm_panel], update_before_add=True)
    LOGGER.info("AMT-8000 alarm control panel setup completed")


class AmtAlarmPanel(CoordinatorEntity, AlarmControlPanelEntity):
    """Define an AMT-8000 Alarm Panel."""

    _attr_supported_features = (
        AlarmControlPanelEntityFeature.ARM_AWAY
        | AlarmControlPanelEntityFeature.ARM_HOME
        | AlarmControlPanelEntityFeature.TRIGGER
    )
    _attr_has_entity_name = True
    _attr_name = "Alarm Panel"
    #_attr_code_format = None  # No se requiere código para operar
    _attr_code_format = CodeFormat.NUMBER
    _attr_code_arm_required = True

   # def requires_code_to_arm(self) -> bool:
   #     """Indicar que no se requiere código para armar."""
   #     return False

    #def requires_code_to_disarm(self) -> bool:
    #    """Indicar que no se requiere código para desarmar."""
    #    return False
    
    def __init__(self, coordinator: AmtCoordinator, password: str, host: str) -> None:
        """Initialize the alarm panel."""
        super().__init__(coordinator)
        self._password = password
        self._host = host
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_alarm_panel"
        self._attr_state = None
        self._last_known_state = None
        
        # Inicializar el estado basado en los datos del coordinador
        self._update_state()

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        panel_data = self.coordinator.panel_data
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.config_entry.entry_id)},
            name="AMT-8000 Alarm Panel",
            manufacturer="Intelbras",
            model=panel_data.get("model", "AMT-8000"),
            sw_version=panel_data.get("version", "Unknown"),
            configuration_url=f"http://{self._host}",
        )

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.coordinator.last_update_success and self.coordinator.panel_data is not None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        panel_data = self.coordinator.panel_data
        if not panel_data:
            return {}
            
        return {
            "battery_status": panel_data.get("batteryStatus", "unknown"),
            "tamper": panel_data.get("tamper", False),
            "zones_firing": panel_data.get("zonesFiring", False),
            "zones_closed": panel_data.get("zonesClosed", False),
            "model": panel_data.get("model", "AMT-8000"),
            "version": panel_data.get("version", "Unknown"),
            "paired_zones": len(self.coordinator.zones_data),
        }

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._update_state()
        self.async_write_ha_state()

    def _update_state(self) -> None:
        """Update the alarm panel state based on coordinator data."""
        panel_data = self.coordinator.panel_data
        
        if not panel_data:
            self._attr_state = None
            return

        # Determinar el estado basado en los datos del panel
        if panel_data.get("inAlarm", False):
            self._attr_state = AlarmControlPanelState.TRIGGERED
        elif panel_data.get("armed", False):
            self._attr_state = AlarmControlPanelState.ARMED_AWAY
        elif panel_data.get("partiallyArmed", False) or panel_data.get("armedStay", False):
            self._attr_state = AlarmControlPanelState.ARMED_HOME
        elif panel_data.get("disarmed", False):
            self._attr_state = AlarmControlPanelState.DISARMED
        else:
            # Estado indeterminado - mantener el último estado conocido si existe
            if self._last_known_state is not None:
                self._attr_state = self._last_known_state
            else:
                self._attr_state = AlarmControlPanelState.DISARMED  # Estado por defecto

        # Guardar el último estado conocido válido
        if self._attr_state is not None:
            self._last_known_state = self._attr_state

    async def _execute_command(self, command_func, command_name: str) -> bool:
        """Execute a command on the alarm panel."""
        client = None
        try:
            # Crear una nueva instancia del cliente para el comando
            client = ISecClient(
                host=self.coordinator.config_entry.data["host"],
                port=self.coordinator.config_entry.data["port"]
            )
            
            # Conectar y autenticar
            client.connect()
            client.auth(self._password)
            
            # Ejecutar el comando
            LOGGER.debug(f"Executing {command_name} command")
            result = command_func(client)
            
            # Verificar el resultado
            if result:
                LOGGER.info(f"{command_name} command executed successfully")
                # Forzar actualización inmediata del coordinador
                await self.coordinator.async_request_refresh()
                return True
            else:
                LOGGER.warning(f"{command_name} command failed: {result}")
                return False
                
        except CommunicationError as err:
            LOGGER.error(f"Communication error during {command_name}: %s", err)
            raise HomeAssistantError(f"Failed to communicate with AMT-8000: {err}") from err
            
        except Exception as err:
            LOGGER.error(f"Unexpected error during {command_name}: %s", err)
            raise HomeAssistantError(f"Unexpected error during {command_name}: {err}") from err
            
        finally:
            # Siempre cerrar la conexión
            if client is not None:
                try:
                    client.close()
                except Exception as err:
                    LOGGER.debug(f"Error closing client connection: %s", err)

    async def async_alarm_disarm(self, code: str = None) -> None:
        """Send disarm command."""
        def disarm_func(client):
            return client.disarm_system(0)
        
        success = await self._execute_command(disarm_func, "disarm")
        if not success:
            raise HomeAssistantError("Failed to disarm alarm system")

    async def async_alarm_arm_away(self, code: str = None) -> None:
        """Send arm away command."""
        def arm_away_func(client):
            return client.arm_system(0)
        
        success = await self._execute_command(arm_away_func, "arm_away")
        if not success:
            raise HomeAssistantError("Failed to arm alarm system (away)")

    async def async_alarm_arm_home(self, code: str = None) -> None:
        """Send arm home command."""
        def arm_home_func(client):
            # Nota: Verifica que este sea el comando correcto para arm_home en tu protocolo
            return client.arm_system(1)
        
        success = await self._execute_command(arm_home_func, "arm_home")
        if not success:
            raise HomeAssistantError("Failed to arm alarm system (home)")

    async def async_alarm_trigger(self, code: str = None) -> None:
        """Send alarm trigger command."""
        def trigger_func(client):
            return client.panic(1)
        
        success = await self._execute_command(trigger_func, "trigger")
        if not success:
            raise HomeAssistantError("Failed to trigger alarm")

    # Métodos adicionales para funcionalidades específicas del AMT-8000
    async def async_get_panel_status(self) -> dict[str, Any]:
        """Get detailed panel status."""
        return self.coordinator.panel_data

    async def async_get_zones_status(self) -> dict[str, Any]:
        """Get zones status."""
        return self.coordinator.zones_data

    async def async_refresh_data(self) -> None:
        """Manually refresh panel data."""
        await self.coordinator.async_request_refresh()

    @property
    def state(self) -> AlarmControlPanelState | None:
        """Return the state of the alarm control panel."""
        return self._attr_state
