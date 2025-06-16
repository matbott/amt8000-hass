from datetime import timedelta, datetime
from typing import Any, Dict, Optional

from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry

from .isec2.client import Client as ISecClient, CommunicationError

import logging

LOGGER = logging.getLogger(__name__)

class AmtCoordinator(DataUpdateCoordinator):
    """Coordinate the amt status update."""

    def __init__(self, hass: HomeAssistant, client: ISecClient, password: str, config_entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            LOGGER,
            name="AMT-8000 Data Polling",
            update_interval=timedelta(seconds=30),  # Intervalo menos agresivo para evitar sobrecarga
        )
        self.client = client
        self.password = password
        self.config_entry = config_entry
        self.data = {}
        self.paired_zones: Dict[str, bool] = {}
        self.next_update = datetime.now()
        self.stored_status: Optional[Dict[str, Any]] = None
        self.attempt = 0
        self.last_log_time = datetime.now()
        self.max_retries = 5  # Límite máximo de reintentos
        
        # Configurar nivel de logging
        LOGGER.setLevel(logging.INFO)

    async def _async_update_data(self) -> Dict[str, Any]:
        """Fetch data from AMT-8000."""
        
        # Implementar rate limiting para evitar muchas conexiones
        if datetime.now() < self.next_update:
            if self.stored_status is not None:
                return self.stored_status
            # Si no hay datos almacenados, continuar con la actualización

        try:
            # Conectar y autenticar
            await self._async_connect_and_auth()

            # Obtener zonas emparejadas si es necesario
            if not self.paired_zones:
                await self._async_get_paired_zones()

            # Obtener estado del panel
            status = await self._async_get_status()
            
            # Procesar datos
            processed_data = self._process_status_data(status)
            
            # Actualizar datos almacenados y resetear contadores
            self.stored_status = processed_data
            self.attempt = 0
            self.next_update = datetime.now()

            return processed_data

        except CommunicationError as err:
            LOGGER.error("Communication error with AMT-8000: %s", err)
            return await self._handle_communication_error()
            
        except Exception as err:
            LOGGER.error("Unexpected error fetching AMT-8000 data: %s", err)
            return await self._handle_unexpected_error()
            
        finally:
            await self._async_cleanup_connection()

    async def _async_connect_and_auth(self) -> None:
        """Connect and authenticate with the AMT-8000."""
        try:
            self.client.connect()
            self.client.auth(self.password)
        except Exception as err:
            raise CommunicationError(f"Failed to connect/authenticate: {err}")

    async def _async_get_paired_zones(self) -> None:
        """Get paired zones information."""
        try:
            LOGGER.info("Retrieving paired zones...")
            self.paired_zones = self.client.get_paired_sensors()
            LOGGER.info(f"Found paired zones: {list(self.paired_zones.keys())}")
        except Exception as err:
            LOGGER.warning(f"Failed to get paired zones: {err}")
            # Continuar sin zonas emparejadas si falla
            self.paired_zones = {}

    async def _async_get_status(self) -> Dict[str, Any]:
        """Get status from AMT-8000."""
        try:
            return self.client.status()
        except Exception as err:
            raise CommunicationError(f"Failed to get status: {err}")

    def _process_status_data(self, status: Dict[str, Any]) -> Dict[str, Any]:
        """Process raw status data into structured format."""
        processed_data = {
            "panel": {
                "armed": status.get("armed", False),
                "partiallyArmed": status.get("partiallyArmed", False),
                "disarmed": status.get("disarmed", False),
                "inAlarm": status.get("inAlarm", False),
                "armedStay": status.get("armedStay", False),
                "zonesFiring": status.get("zonesFiring", False),
                "zonesClosed": status.get("zonesClosed", False),
                "batteryStatus": status.get("batteryStatus", "unknown"),
                "tamper": status.get("tamper", False),
                "model": status.get("model", "AMT-8000"),
                "version": status.get("version", "Unknown"),
            },
            "zones": {},
        }

        # Procesar solo zonas emparejadas
        zones_data = status.get("zones", {})
        for zone_id, is_paired in self.paired_zones.items():
            if is_paired and zone_id in zones_data:
                processed_data["zones"][zone_id] = zones_data[zone_id]
            elif is_paired:
                # Zona emparejada pero sin datos - establecer estado por defecto
                processed_data["zones"][zone_id] = "normal"

        return processed_data

    async def _handle_communication_error(self) -> Optional[Dict[str, Any]]:
        """Handle communication errors with exponential backoff."""
        self.attempt = min(self.attempt + 1, self.max_retries)
        
        if self.attempt >= self.max_retries:
            LOGGER.error("Maximum retry attempts reached for AMT-8000 communication")
            # Resetear después de alcanzar el máximo
            self.attempt = 0
            backoff_seconds = 300  # 5 minutos de espera
        else:
            backoff_seconds = min(2 ** self.attempt, 60)  # Máximo 60 segundos
        
        self.next_update = datetime.now() + timedelta(seconds=backoff_seconds)
        LOGGER.info(f"Next retry in {backoff_seconds} seconds (attempt {self.attempt}/{self.max_retries})")
        
        # Devolver datos almacenados si existen
        if self.stored_status is not None:
            return self.stored_status
        
        # Si no hay datos almacenados, lanzar excepción para que Home Assistant lo maneje
        raise UpdateFailed(f"Failed to communicate with AMT-8000 after {self.attempt} attempts")

    async def _handle_unexpected_error(self) -> Optional[Dict[str, Any]]:
        """Handle unexpected errors."""
        self.attempt = min(self.attempt + 1, self.max_retries)
        backoff_seconds = min(2 ** self.attempt, 120)  # Máximo 2 minutos para errores inesperados
        
        self.next_update = datetime.now() + timedelta(seconds=backoff_seconds)
        LOGGER.info(f"Next retry in {backoff_seconds} seconds due to unexpected error")
        
        if self.stored_status is not None:
            return self.stored_status
            
        raise UpdateFailed("Unexpected error occurred while fetching AMT-8000 data")

    async def _async_cleanup_connection(self) -> None:
        """Clean up connection resources."""
        try:
            if (self.client and 
                hasattr(self.client, 'client') and 
                self.client.client is not None):
                self.client.close()
        except Exception as e:
            # Solo log en debug para errores de limpieza
            LOGGER.debug("Error closing client connection: %s", str(e))

    async def async_refresh_zones(self) -> None:
        """Manually refresh paired zones information."""
        try:
            LOGGER.info("Manually refreshing paired zones...")
            await self._async_connect_and_auth()
            await self._async_get_paired_zones()
            LOGGER.info("Paired zones refreshed successfully")
        except Exception as err:
            LOGGER.error(f"Failed to refresh paired zones: {err}")
        finally:
            await self._async_cleanup_connection()

    @property
    def panel_data(self) -> Dict[str, Any]:
        """Get panel data from stored status."""
        if self.stored_status is None:
            return {}
        return self.stored_status.get("panel", {})

    @property
    def zones_data(self) -> Dict[str, Any]:
        """Get zones data from stored status."""
        if self.stored_status is None:
            return {}
        return self.stored_status.get("zones", {})
