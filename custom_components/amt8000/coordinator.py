from datetime import timedelta, datetime
from typing import Any

from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
)
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry # Importar ConfigEntry

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
            update_interval=timedelta(seconds=5), # Intervalo de actualización más frecuente
        )
        self.client = client
        self.password = password
        self.config_entry = config_entry # Almacenar la instancia de ConfigEntry
        self.data = {}
        self.paired_zones = {}  # Store paired zones information
        self.next_update = datetime.now()
        self.stored_status = None
        self.attempt = 0
        self.last_log_time = datetime.now()
        # Set coordinator logger to INFO level to suppress debug logs
        LOGGER.setLevel(logging.INFO)

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from AMT-8000."""
        self.attempt += 1

        if(datetime.now() < self.next_update):
           return self.stored_status

        try:
            self.client.connect()
            self.client.auth(self.password)

            # --- NUEVO: Obtener la lista de zonas emparejadas en la primera actualización o si no la tenemos ---
            if not self.paired_zones: # Si aún no se han obtenido las zonas emparejadas
                LOGGER.info("Retrieving paired zones for the first time...")
                self.paired_zones = self.client.get_paired_sensors()
                LOGGER.info(f"Paired zones: {self.paired_zones}")
            # --- FIN NUEVO ---

            status = self.client.status()

            # Asegúrate de que los datos almacenados incluyan la información del panel
            processed_data = {
                "panel": {
                    "armed": status.get("armed", False),
                    "partiallyArmed": status.get("partiallyArmed", False),
                    "disarmed": status.get("disarmed", False),
                    "inAlarm": status.get("inAlarm", False),
                    "armedStay": status.get("armedStay", False),
                    "zonesFiring": status.get("zonesFiring", False),
                    "zonesClosed": status.get("zonesClosed", False), # Mantener como estaba
                    "batteryStatus": status.get("batteryStatus", "unknown"),
                    "tamper": status.get("tamper", False),
                    "model": status.get("model", "AMT-8000"), # Asegúrate de que estos estén en el status
                    "version": status.get("version", "Unknown"), # Asegúrate de que estos estén en el status
                },
                "zones": {},
            }

            # Only process zones that are paired
            for zone_id, is_paired in self.paired_zones.items(): # Iterar sobre self.paired_zones
                if is_paired: # Solo si la zona está realmente emparejada
                    zone_status = status.get("zones", {}).get(zone_id, "normal")
                    processed_data["zones"][zone_id] = zone_status

            self.stored_status = processed_data
            self.attempt = 0
            self.next_update = datetime.now()

            return processed_data

        except CommunicationError as err:
            LOGGER.error("Communication error with AMT-8000: %s", err)
            seconds = 2 ** self.attempt
            time_difference = timedelta(seconds=seconds)
            self.next_update = datetime.now() + time_difference
            LOGGER.info("Next retry after %s seconds due to communication error.", seconds)
            # No raises here, allow previous data to persist if there was any
            return self.stored_status
        except Exception as err:
            LOGGER.error("Error fetching AMT-8000 data: %s", err)
            seconds = 2 ** self.attempt
            time_difference = timedelta(seconds=seconds)
            self.next_update = datetime.now() + time_difference
            LOGGER.info("Next retry after %s seconds due to unexpected error.", seconds)
            return self.stored_status

        finally:
            try:
                if self.client and hasattr(self.client, 'client') and self.client.client is not None:
                    self.client.close()
            except CommunicationError:
                pass
            except Exception as e:
                LOGGER.debug("Error closing client connection: %s", str(e))
