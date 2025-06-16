"""Defines the alarm control panel for amt-8000."""

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
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
)

from .const import DOMAIN
from .coordinator import AmtCoordinator
from .isec2.client import Client as ISecClient, CommunicationError # Importar CommunicationError también

LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0
SCAN_INTERVAL = timedelta(seconds=10) # Puedes ajustar esto si sigues viendo errores de conexión

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the AMT-8000 alarm control panel."""
    data = hass.data[DOMAIN][config_entry.entry_id]
    config = data["config"]
    coordinator: AmtCoordinator = data["coordinator"]

    LOGGER.info('setting up alarm control panel...')
    
    # IMPORTANTE: Pasamos el cliente del coordinador, ya que el coordinador gestiona la conexión.
    # Esto asume que el coordinador mantiene una conexión activa o la gestiona de forma inteligente.
    # Si el coordinador cierra la conexión después de cada status update, entonces las acciones
    # sí necesitarían re-conectar. Pero el objetivo del coordinador es mantenerla o reabrirla eficientemente.
    sensors = [AmtAlarmPanel(coordinator, coordinator.client, config["password"], config["host"])]
    async_add_entities(sensors)


class AmtAlarmPanel(CoordinatorEntity, AlarmControlPanelEntity):
    """Define a Amt Alarm Panel."""

    _attr_supported_features = (
          AlarmControlPanelEntityFeature.ARM_AWAY
        | AlarmControlPanelEntityFeature.TRIGGER
        | AlarmControlPanelEntityFeature.ARM_HOME # Si el modo "parcialmente armado" es ARM_HOME
    )
    _attr_has_entity_name = True
    _attr_name = "Alarm Panel"

    def __init__(self, coordinator: AmtCoordinator, isec_client: ISecClient, password: str, host: str) -> None:
        """Initialize the alarm panel."""
        super().__init__(coordinator)
        # Usamos el cliente del coordinador. Esperamos que el coordinador lo maneje.
        self.isec_client = isec_client 
        self.password = password
        self._host = host

        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_alarm_panel"
        self._attr_state = None # Cambiado de UNKNOWN a None

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.config_entry.entry_id)},
            name="AMT-8000 Alarm Panel",
            manufacturer="Intelbras",
            model=self.coordinator.data.get("panel", {}).get("model", "AMT-8000"),
            sw_version=self.coordinator.data.get("panel", {}).get("version", "Unknown"),
            via_device=(DOMAIN, self._host),
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        current_status = self.coordinator.data.get("panel", {})
        
        if current_status.get("inAlarm"):
            self._attr_state = AlarmControlPanelState.ALARMING
        elif current_status.get("armed"):
            self._attr_state = AlarmControlPanelState.ARMED_AWAY
        elif current_status.get("partiallyArmed"):
            self._attr_state = AlarmControlPanelState.ARMED_HOME 
        elif current_status.get("disarmed"):
            self._attr_state = AlarmControlPanelState.DISARMED
        else:
            # Si no hay un estado claro, el coordinador puede estar en un estado de error
            # o el panel no reporta un estado específico. Dejamoslo como None o UNKNOWN si es posible.
            # Home Assistant debería mostrarlo como "Desconocido" o "No disponible"
            self._attr_state = None 

        self.async_write_ha_state()

    @property
    def code_format(self) -> None:
        """Return one of the alarm code formats."""
        return None

    # Refactorizamos las funciones de comando para usar el cliente del coordinador
    async def _execute_command(self, command_func, success_message, error_message):
        try:
            # Intentamos usar la conexión existente del coordinador
            # Si el coordinador cierra la conexión después de cada actualización,
            # este bloque podría necesitar ser ajustado para manejar eso,
            # pero la idea es evitar re-conectar y re-autenticar aquí si no es necesario.
            # Idealmente, el cliente del coordinador debería tener un método para
            # reabrir la conexión si está cerrada.
            
            # Para tu caso actual (cliente se conecta/cierra en cada llamada),
            # mantenemos la conexión/autenticación aquí.
            # PERO, envolvemos en try-finally para asegurar el cierre.
            
            self.isec_client.connect() # Conectar antes de cada comando
            self.isec_client.auth(self.password) # Autenticar antes de cada comando
            result = command_func()
            
            if result == success_message:
                LOGGER.debug(f"{success_message} successfully.")
                await self.coordinator.async_request_refresh() # Forzar actualización
                return True
            else:
                LOGGER.warning(f"{error_message}: {result}")
                return False
        except CommunicationError as e:
            LOGGER.error(f"Communication error during {error_message}: %s", e)
            return False
        except Exception as e:
            LOGGER.error(f"Error during {error_message}: %s", e)
            return False
        finally:
            # Asegurarse de cerrar la conexión si se abrió aquí
            if hasattr(self.isec_client, 'client') and self.isec_client.client is not None:
                try:
                    self.isec_client.close()
                except CommunicationError:
                    pass # Ignore if already closed or error during close
                except Exception as e:
                    LOGGER.debug("Error closing client connection after command: %s", str(e))

    async def async_alarm_disarm(self, code=None) -> None:
        """Send disarm command."""
        await self._execute_command(
            lambda: self.isec_client.disarm_system(0),
            "disarmed",
            "Disarm command failed"
        )

    async def async_alarm_arm_away(self, code=None) -> None:
        """Send arm away command."""
        await self._execute_command(
            lambda: self.isec_client.arm_system(0),
            "armed",
            "Arm away command failed"
        )
    
    # Si 'partiallyArmed' es para ARM_HOME, entonces añadir este
    async def async_alarm_arm_home(self, code=None) -> None:
        """Send arm home command (if your panel supports it separately)."""
        # Asume que el arm_system con un argumento diferente (ej. 1) es para arm_home
        # DEBES CONFIRMAR QUÉ COMANDO ES PARA ARM_HOME EN TU PROTOCOLO AMT
        await self._execute_command(
            lambda: self.isec_client.arm_system(1), # <--- ESTO ES UN EJEMPLO, VERIFICA EL COMANDO REAL
            "armed_home", # O el resultado que el panel devuelva
            "Arm home command failed"
        )


    async def async_alarm_trigger(self, code=None) -> None:
        """Send alarm trigger command."""
        await self._execute_command(
            lambda: self.isec_client.panic(1),
            "triggered",
            "Trigger alarm command failed"
        )
    
    # Eliminadas las propiedades is_on, turn_on, turn_off ya que no aplican directamente a AlarmControlPanelEntity
    # y los comandos de alarma ya manejan el estado.

    @property
    def state(self) -> str | None:
        """Return the state of the alarm control panel."""
        return self._attr_state
