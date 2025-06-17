import asyncio
import logging
from datetime import timedelta
from typing import Any, Dict

from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry

from .isec2.client import Client as ISecClient, CommunicationError

LOGGER = logging.getLogger(__name__)


class AmtCoordinator(DataUpdateCoordinator):
    """Coordinate the AMT-8000 status updates."""

    def __init__(
        self, 
        hass: HomeAssistant, 
        client: ISecClient, 
        password: str, 
        config_entry: ConfigEntry
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            LOGGER,
            name="AMT-8000",
            update_interval=timedelta(seconds=30),
        )
        self.client = client
        self.password = password
        self.config_entry = config_entry
        self._authenticated = False
        self._paired_zones: Dict[str, bool] = {}
        self._connection_active = False

    async def _async_update_data(self) -> Dict[str, Any]:
        """Fetch data from AMT-8000."""
        try:
            # Conectar y autenticar si es necesario
            if not self._connection_active:
                await self._async_ensure_connection()

            # Obtener zonas emparejadas si no las tenemos
            if not self._paired_zones:
                await self._async_get_paired_zones()

            # Obtener estado del sistema
            status = await self._async_get_status()
            
            return self._process_status_data(status)

        except CommunicationError as err:
            LOGGER.warning("Communication error with AMT-8000: %s", err)
            self._reset_connection()
            raise UpdateFailed(f"Communication failed: {err}")
            
        except Exception as err:
            LOGGER.error("Unexpected error fetching AMT-8000 data: %s", err)
            self._reset_connection()
            raise UpdateFailed(f"Update failed: {err}")

    async def _async_ensure_connection(self) -> None:
        """Ensure connection and authentication."""
        try:
            await asyncio.to_thread(self._connect_and_auth)
            self._connection_active = True
            self._authenticated = True
            LOGGER.debug("Connection established with AMT-8000")
        except Exception as err:
            self._reset_connection()
            raise CommunicationError(f"Connection failed: {err}")

    def _connect_and_auth(self) -> None:
        """Connect and authenticate (sync method for thread)."""
        self.client.connect()
        self.client.auth(self.password)

    async def _async_get_paired_zones(self) -> None:
        """Get paired zones information."""
        try:
            LOGGER.info("Retrieving paired zones...")
            paired_zones = await asyncio.to_thread(self.client.get_paired_sensors)
            self._paired_zones = paired_zones or {}
            LOGGER.info(f"Found {len(self._paired_zones)} paired zones")
        except Exception as err:
            LOGGER.warning(f"Failed to get paired zones: {err}")
            self._paired_zones = {}

    async def _async_get_status(self) -> Dict[str, Any]:
        """Get status from AMT-8000."""
        try:
            return await asyncio.to_thread(self.client.status)
        except Exception as err:
            raise CommunicationError(f"Failed to get status: {err}")

    def _process_status_data(self, status: Dict[str, Any]) -> Dict[str, Any]:
        """Process raw status data into structured format."""
        # Extraer datos del panel
        panel_data = {
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
        }

        # Extraer datos de zonas emparejadas
        zones_data = {}
        raw_zones = status.get("zones", {})
        
        for zone_id, is_paired in self._paired_zones.items():
            if is_paired:
                zones_data[zone_id] = raw_zones.get(zone_id, "normal")

        return {
            "panel_data": panel_data,
            "zones_data": zones_data,
        }

    def _reset_connection(self) -> None:
        """Reset connection state."""
        self._connection_active = False
        self._authenticated = False
        try:
            self.client.close()
        except Exception:
            pass  # Ignore cleanup errors

    async def async_refresh_zones(self) -> None:
        """Manually refresh paired zones information."""
        try:
            LOGGER.info("Refreshing paired zones...")
            await self._async_ensure_connection()
            await self._async_get_paired_zones()
            # Trigger data refresh
            await self.async_refresh()
            LOGGER.info("Paired zones refreshed successfully")
        except Exception as err:
            LOGGER.error(f"Failed to refresh paired zones: {err}")
            raise

    @property
    def panel_data(self) -> Dict[str, Any]:
        """Get panel data from last update."""
        if not self.data:
            return {}
        return self.data.get("panel_data", {})

    @property
    def zones_data(self) -> Dict[str, Any]:
        """Get zones data from last update."""
        if not self.data:
            return {}
        return self.data.get("zones_data", {})

    @property
    def paired_zones(self) -> Dict[str, bool]:
        """Get paired zones dictionary."""
        return self._paired_zones.copy()

    async def async_will_remove_from_hass(self) -> None:
        """Clean up when coordinator is removed."""
        self._reset_connection()
        LOGGER.debug("AMT-8000 coordinator cleaned up")
