"""Platform for sensor integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import AmtCoordinator

LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensor platform."""
    # Accedemos al coordinador que ya fue creado y guardado en hass.data por __init__.py
    coordinator: AmtCoordinator = hass.data[DOMAIN][config_entry.entry_id]['coordinator']
    
    LOGGER.info('setting up sensor entities...')
    entities: list[SensorEntity] = [
        AmtBatteryStatusSensor(coordinator),
    ]
    async_add_entities(entities)


class AmtBatteryStatusSensor(CoordinatorEntity, SensorEntity):
    # ... (el resto de la clase es el mismo) ...
    """Representation of an AMT-8000 Battery Status Sensor."""

    def __init__(self, coordinator: AmtCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_name = "AMT-8000 Battery Status"
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_battery_status"
        self._attr_icon = "mdi:battery" # Icono para el estado de la batería
        self._current_status = None # Para almacenar el valor actual

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        # El coordinador ya obtiene y procesa los datos en su método _async_update_data
        # y los guarda en coordinator.data.
        # Aquí solo necesitamos extraer el valor específico.
        self._current_status = self.coordinator.data.get("batteryStatus")
        self.async_write_ha_state() # Notifica a Home Assistant de un cambio de estado

    @property
    def native_value(self) -> str | None:
        """Return the state of the sensor (e.g., 'full', 'low')."""
        return self._current_status

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        # El sensor está disponible si el coordinador está disponible y tiene datos
        return self.coordinator.last_update_success and self._current_status is not None

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device information."""
        # Asociar este sensor al mismo dispositivo que el panel de alarma
        return {
            "identifiers": {(DOMAIN, self.coordinator.config_entry.entry_id)},
            "name": "AMT-8000 Alarm Panel",
            "manufacturer": "Intelbras",
            "model": self.coordinator.data.get("model", "AMT-8000"),
            "sw_version": self.coordinator.data.get("version", "Unknown"),
        }
        
