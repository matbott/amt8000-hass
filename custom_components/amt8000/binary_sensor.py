# custom_components/amt8000/binary_sensor.py

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorDeviceClass, # Añadimos BinarySensorDeviceClass para tipos más específicos
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import AmtCoordinator

LOGGER = logging.getLogger(__name__)

# Definir el número máximo de zonas que queremos crear
# Ajusta este valor si sabes que tu panel tiene menos de 64 zonas.
MAX_ZONES = 64 

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
        AmtZonesClosedSensor(coordinator), # Entidad existente
        AmtSirenSensor(coordinator),       # Entidad existente
        AmtTamperSensor(coordinator),      # Entidad existente
    ]

    # AÑADIR LAS ENTIDADES DE ZONA INDIVIDUALES
    for i in range(MAX_ZONES):
        entities.append(AmtZoneBinarySensor(coordinator, i + 1)) # Las zonas suelen ser 1-indexadas

    async_add_entities(entities)


class AmtZonesClosedSensor(CoordinatorEntity, BinarySensorEntity):
    """Representation of an AMT-8000 Zones Closed Sensor."""

    def __init__(self, coordinator: AmtCoordinator) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self._attr_name = "AMT-8000 All Zones Closed"
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_zones_closed"
        self._attr_device_class = BinarySensorDeviceClass.SAFETY # Clase de dispositivo apropiada
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
    """Representation of an AMT-8000 Siren Sensor."""

    def __init__(self, coordinator: AmtCoordinator) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self._attr_name = "AMT-8000 Siren Active"
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_siren_active"
        self._attr_device_class = BinarySensorDeviceClass.SIREN # Clase de dispositivo para sirenas
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
    """Representation of an AMT-8000 Tamper Sensor."""

    def __init__(self, coordinator: AmtCoordinator) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self._attr_name = "AMT-8000 Tamper Detected"
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_tamper_detected"
        self._attr_device_class = BinarySensorDeviceClass.PROBLEM # Clase de dispositivo para problemas
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


# NUEVA CLASE PARA LAS ZONAS INDIVIDUALES
class AmtZoneBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Representation of an AMT-8000 Zone Binary Sensor."""

    def __init__(self, coordinator: AmtCoordinator, zone_number: int) -> None:
        """Initialize the zone binary sensor."""
        super().__init__(coordinator)
        self._zone_number = zone_number
        self._attr_name = f"AMT-8000 Zone {zone_number}"
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_zone_{zone_number}"
        # La clase de dispositivo 'opening' es genérica para sensores de apertura/cierre.
        self._attr_device_class = BinarySensorDeviceClass.OPENING 
        self._is_on = None # Para almacenar el estado actual de la zona (True = abierto, False = cerrado)

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        # El coordinador.data ahora contiene la clave 'zones' que es una lista de booleanos.
        # El índice de la lista es (zone_number - 1) ya que las listas son 0-indexadas.
        if (
            self.coordinator.data 
            and "zones" in self.coordinator.data 
            and len(self.coordinator.data["zones"]) >= self._zone_number
        ):
            # True si la zona está abierta/faulted, False si está cerrada
            self._is_on = self.coordinator.data["zones"][self._zone_number - 1]
        else:
            LOGGER.warning(f"Zone {self._zone_number} data not found or invalid in coordinator data.")
            self._is_on = None # Marcar como desconocido si los datos no están disponibles
        self.async_write_ha_state() # Notifica a Home Assistant de un cambio de estado

    @property
    def is_on(self) -> bool | None:
        """Return True if the binary sensor is on (zone is open/faulted)."""
        return self._is_on

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        # El sensor está disponible si el coordinador está disponible y se pudo obtener el estado de la zona
        return self.coordinator.last_update_success and self._is_on is not None

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
