"""Sensors (zones) for the Intelbras AMT-8000-MF."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass, # Asegúrate de que esto esté importado
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.device_registry import DeviceInfo # Asegúrate de que esto esté importado

from .const import DOMAIN
from .coordinator import AmtCoordinator

LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensor platform."""
    coordinator: AmtCoordinator = hass.data[DOMAIN][config_entry.entry_id]['coordinator']
    config = hass.data[DOMAIN][config_entry.entry_id]['config'] # Obtener la configuración

    LOGGER.info('setting up sensor entities...')

    entities: list[SensorEntity] = []

    # Add the Battery Status Sensor
    entities.append(AmtBatteryStatusSensor(coordinator, config_entry.entry_id)) # Pasar entry_id para unique_id

    # Add a sensor for each paired zone
    # Asegúrate de que paired_zones ya está populado en el coordinador
    if coordinator.paired_zones:
        for zone_id, is_paired in coordinator.paired_zones.items():
            if is_paired: # Solo si la zona está realmente emparejada
                entities.append(AMTZoneSensor(coordinator, zone_id, config["host"])) # Pasar host para DeviceInfo

    async_add_entities(entities)


class AmtBatteryStatusSensor(CoordinatorEntity, SensorEntity):
    """Representation of an AMT-8000 Battery Status Sensor."""

    _attr_has_entity_name = True
    _attr_name = "Battery Status" # Nombre más corto para la entidad

    def __init__(self, coordinator: AmtCoordinator, entry_id: str) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        # Usamos el entry_id para el unique_id, garantizando unicidad en HA
        self._attr_unique_id = f"{entry_id}_battery_status"
        self._attr_device_class = SensorDeviceClass.BATTERY # Define la clase de dispositivo
        self._current_status = None

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        # El coordinador ya obtiene y procesa los datos en su método _async_update_data
        # y los guarda en coordinator.data.
        # Aquí solo necesitamos extraer el valor específico.
        self._current_status = self.coordinator.data.get("batteryStatus")
        self.async_write_ha_state()

    @property
    def native_value(self) -> str | None:
        """Return the state of the sensor (e.g., 'full', 'low')."""
        # Mapea los estados de la alarma a algo más amigable si es necesario
        # 'ok' -> 'Full', 'low' -> 'Low', etc.
        # Por ahora, devolvemos el valor tal cual.
        return self._current_status

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self.coordinator.last_update_success and self._current_status is not None

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        # Asocia este sensor al mismo dispositivo que el panel de alarma
        # Usamos el entry_id para el identificador único del dispositivo
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.config_entry.entry_id)},
            name="AMT-8000 Alarm Panel",
            manufacturer="Intelbras",
            model=self.coordinator.data.get("model", "AMT-8000"),
            sw_version=self.coordinator.data.get("version", "Unknown"),
            via_device=(DOMAIN, self.coordinator.config_entry.data["host"]), # Opcional: Para agrupar por host si hay múltiples paneles
        )


class AMTZoneSensor(CoordinatorEntity, SensorEntity):
    """Represents a zone (sector) of the AMT-8000."""

    _attr_should_poll = False
    _attr_has_entity_name = True # Permite que HA genere el nombre automáticamente basado en el name del __init__
    _attr_state_options = [ # Posibles estados que tu sensor puede tomar
        "seguro",
        "disparado",
        "abierto",
        "violado",
        "ignorado",
        "bateria_fraca",
        "falha_comunicacao",
        "inseguro"
    ]
    # No SensorDeviceClass específico para zonas de alarma en este caso, se usa el estado nativo.

    def __init__(self, coordinator: AmtCoordinator, zone_id: str, host: str) -> None:
        """Initialize the zone sensor."""
        super().__init__(coordinator)
        self._zone_id = zone_id
        # Ejemplo de Unique ID. Asegúrate de que sea único.
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_zone_{zone_id}"
        self._attr_name = f"Zone {zone_id}" # Nombre por defecto, el usuario puede cambiarlo en HA
        self._host = host # Guardar host para DeviceInfo si es necesario

    @property
    def native_value(self) -> str | None:
        """Return the state of the sensor."""
        # Obtiene el estado de la zona específica del coordinador
        zone_status = self.coordinator.data.get("zones", {}).get(self._zone_id, "normal")

        # Tu lógica de mapeo de estados de la zona
        if zone_status == "normal":
            return "seguro"

        # Se houver múltiplos problemas, retorna o mais crítico
        if isinstance(zone_status, str):
            problems = zone_status.split(",")

            if "triggered" in problems:
                return "disparado"
            elif "open" in problems:
                return "abierto"
            elif "tamper" in problems:
                return "violado"
            elif "bypassed" in problems:
                return "ignorado"
            elif "low_battery" in problems:
                return "bateria_fraca"
            elif "comm_failure" in problems:
                return "falha_comunicacao"

        return "inseguro" # Estado por defecto si no coincide con ninguno


    @property
    def extra_state_attributes(self) -> dict:
        """Return the state attributes."""
        zone_status = self.coordinator.data.get("zones", {}).get(self._zone_id, "normal")

        # Convert comma-separated status to list for better UI display
        if isinstance(zone_status, str) and "," in zone_status:
            problems = zone_status.split(",")
        else:
            problems = [zone_status]

        return {
            "status": zone_status, # El estado raw del protocolo
            "problems": problems, # La lista de problemas si hay varios
            "zone_id": self._zone_id
        }

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information for this zone sensor."""
        # Asociar cada sensor de zona al mismo dispositivo principal (el panel de alarma)
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.config_entry.entry_id)},
            name="AMT-8000 Alarm Panel",
            manufacturer="Intelbras",
            model=self.coordinator.data.get("model", "AMT-8000"),
            sw_version=self.coordinator.data.get("version", "Unknown"),
            via_device=(DOMAIN, self._host), # Útil si quieres que los sensores aparezcan "debajo" del panel en la vista de dispositivos
        )
