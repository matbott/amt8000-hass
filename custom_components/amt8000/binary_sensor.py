"""Platform for binary sensor integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity
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
    """Set up the binary sensor platform."""
    # Accedemos al coordinador que ya fue creado y guardado en hass.data por __init__.py
    coordinator: AmtCoordinator = hass.data[DOMAIN][config_entry.entry_id]['coordinator']
    
    LOGGER.info('setting up binary sensor entities...')
    entities: list[BinarySensorEntity] = [
        AmtZonesClosedSensor(coordinator),
        AmtSirenSensor(coordinator),
        AmtTamperSensor(coordinator),
    ]
    async_add_entities(entities)


class AmtZonesClosedSensor(CoordinatorEntity, BinarySensorEntity):
    # ... (el resto de la clase es el mismo) ...
    """Representation of an AMT-8000 Zones Closed Sensor."""

    def __init__(self, coordinator: AmtCoordinator) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self._attr_name = "AMT-8000 All Zones Closed"
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_zones_closed"
        self._attr_device_class = "safety" # Opcional: una clase de dispositivo apropiada
        self._is_on = None

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._is_on = self.coordinator.data.get("zonesClosed")
        self.async_write_ha_state()

    @property
    def is_on(self) -> bool | None:
        """Return true if the binary sensor is on."""
        return self._is_on

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self.coordinator.last_update_success and self._is_on is not None
    
    @property
    def device_info(self) -> dict[str, Any]:
        """Return device information."""
        return {
            "identifiers": {(DOMAIN, self.coordinator.config_entry.entry_id)},
            "name": "AMT-8000 Alarm Panel",
            "manufacturer": "Intelbras",
            "model": self.coordinator.data.get("model", "AMT-8000"),
            "sw_version": self.coordinator.data.get("version", "Unknown"),
        }


class AmtSirenSensor(CoordinatorEntity, BinarySensorEntity):
    # ... (el resto de la clase es el mismo) ...
    """Representation of an AMT-8000 Siren Sensor."""

    def __init__(self, coordinator: AmtCoordinator) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self._attr_name = "AMT-8000 Siren Active"
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_siren_active"
        self._attr_device_class = "siren" # Clase de dispositivo para sirenas
        self._is_on = None

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._is_on = self.coordinator.data.get("siren")
        self.async_write_ha_state()

    @property
    def is_on(self) -> bool | None:
        """Return true if the binary sensor is on."""
        return self._is_on

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self.coordinator.last_update_success and self._is_on is not None
    
    @property
    def device_info(self) -> dict[str, Any]:
        """Return device information."""
        return {
            "identifiers": {(DOMAIN, self.coordinator.config_entry.entry_id)},
            "name": "AMT-8000 Alarm Panel",
            "manufacturer": "Intelbras",
            "model": self.coordinator.data.get("model", "AMT-8000"),
            "sw_version": self.coordinator.data.get("version", "Unknown"),
        }


class AmtTamperSensor(CoordinatorEntity, BinarySensorEntity):
    # ... (el resto de la clase es el mismo) ...
    """Representation of an AMT-8000 Tamper Sensor."""

    def __init__(self, coordinator: AmtCoordinator) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self._attr_name = "AMT-8000 Tamper Detected"
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_tamper_detected"
        self._attr_device_class = "problem" # Opcional: para indicar un problema
        self._is_on = None

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._is_on = self.coordinator.data.get("tamper")
        self.async_write_ha_state()

    @property
    def is_on(self) -> bool | None:
        """Return true if the binary sensor is on."""
        return self._is_on

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self.coordinator.last_update_success and self._is_on is not None
    
    @property
    def device_info(self) -> dict[str, Any]:
        """Return device information."""
        return {
            "identifiers": {(DOMAIN, self.coordinator.config_entry.entry_id)},
            "name": "AMT-8000 Alarm Panel",
            "manufacturer": "Intelbras",
            "model": self.coordinator.data.get("model", "AMT-8000"),
            "sw_version": self.coordinator.data.get("version", "Unknown"),
        }

