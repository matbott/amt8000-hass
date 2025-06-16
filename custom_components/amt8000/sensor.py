"""Sensors (zones) for the Intelbras AMT-8000-MF."""

from __future__ import annotations

import logging
from typing import Any, Optional

from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorDeviceClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.const import EntityCategory

from .const import DOMAIN
from .coordinator import AmtCoordinator

LOGGER = logging.getLogger(__name__)

# Mapeo de estados de zona del protocolo AMT a estados legibles
ZONE_STATE_MAP = {
    "normal": "seguro",
    "triggered": "disparado",
    "open": "abierto",
    "tamper": "violado",
    "bypassed": "ignorado",
    "low_battery": "bateria_fraca",
    "comm_failure": "falha_comunicacao",
    "fault": "inseguro",
    "alarm": "disparado",
    "trouble": "problema",
}

# Estados críticos que requieren atención inmediata
CRITICAL_STATES = ["triggered", "tamper", "alarm"]

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensor platform."""
    coordinator: AmtCoordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]
    config = hass.data[DOMAIN][config_entry.entry_id]["config"]

    LOGGER.info("Setting up AMT-8000 sensor entities...")

    entities: list[SensorEntity] = []

    # Agregar sensores del panel principal
    entities.extend([
        AmtBatteryStatusSensor(coordinator),
        AmtSystemStatusSensor(coordinator),
        AmtZoneCountSensor(coordinator),
    ])

    # Agregar sensores para cada zona emparejada
    if coordinator.paired_zones:
        for zone_id, is_paired in coordinator.paired_zones.items():
            if is_paired:
                entities.extend([
                    AMTZoneSensor(coordinator, zone_id),
                    AMTZoneBinarySensor(coordinator, zone_id),
                ])
                LOGGER.debug(f"Added sensors for zone {zone_id}")
    else:
        LOGGER.warning("No paired zones found during sensor setup")

    async_add_entities(entities, update_before_add=True)
    LOGGER.info(f"Added {len(entities)} AMT-8000 sensor entities")


class AmtBatteryStatusSensor(CoordinatorEntity, SensorEntity):
    """Representation of an AMT-8000 Battery Status Sensor."""

    _attr_has_entity_name = True
    _attr_name = "Battery Status"
    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:battery"

    def __init__(self, coordinator: AmtCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_battery_status"

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        panel_data = self.coordinator.panel_data
        if panel_data:
            battery_status = panel_data.get("batteryStatus", "unknown")
            self._attr_native_value = self._map_battery_status(battery_status)
            self._attr_icon = self._get_battery_icon(battery_status)
        else:
            self._attr_native_value = None
        self.async_write_ha_state()

    def _map_battery_status(self, status: str) -> str:
        """Map battery status to human readable format."""
        status_map = {
            "ok": "Normal",
            "low": "Baja",
            "critical": "Crítica",
            "unknown": "Desconocido",
            "full": "Completa",
        }
        return status_map.get(status.lower(), status)

    def _get_battery_icon(self, status: str) -> str:
        """Get appropriate battery icon."""
        if status.lower() in ["low", "critical"]:
            return "mdi:battery-alert"
        elif status.lower() in ["ok", "full"]:
            return "mdi:battery"
        else:
            return "mdi:battery-unknown"

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self.coordinator.last_update_success and bool(self.coordinator.panel_data)

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return self._get_device_info()

    def _get_device_info(self) -> DeviceInfo:
        """Get device info for the AMT-8000 panel."""
        panel_data = self.coordinator.panel_data
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.config_entry.entry_id)},
            name="AMT-8000 Alarm Panel",
            manufacturer="Intelbras",
            model=panel_data.get("model", "AMT-8000"),
            sw_version=panel_data.get("version", "Unknown"),
            configuration_url=f"http://{self.coordinator.config_entry.data['host']}",
        )


class AmtSystemStatusSensor(CoordinatorEntity, SensorEntity):
    """Sensor showing overall system status."""

    _attr_has_entity_name = True
    _attr_name = "System Status"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:shield-check"

    def __init__(self, coordinator: AmtCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_system_status"

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        panel_data = self.coordinator.panel_data
        if panel_data:
            self._attr_native_value = self._determine_system_status(panel_data)
            self._attr_icon = self._get_system_icon(panel_data)
        else:
            self._attr_native_value = "Desconectado"
            self._attr_icon = "mdi:shield-off"
        self.async_write_ha_state()

    def _determine_system_status(self, panel_data: dict) -> str:
        """Determine overall system status."""
        if panel_data.get("inAlarm"):
            return "En Alarma"
        elif panel_data.get("tamper"):
            return "Sabotaje"
        elif panel_data.get("armed"):
            return "Armado Total"
        elif panel_data.get("partiallyArmed") or panel_data.get("armedStay"):
            return "Armado Parcial"
        elif panel_data.get("disarmed"):
            return "Desarmado"
        else:
            return "Estado Desconocido"

    def _get_system_icon(self, panel_data: dict) -> str:
        """Get appropriate system icon."""
        if panel_data.get("inAlarm"):
            return "mdi:shield-alert"
        elif panel_data.get("tamper"):
            return "mdi:shield-remove"
        elif panel_data.get("armed"):
            return "mdi:shield-lock"
        elif panel_data.get("partiallyArmed") or panel_data.get("armedStay"):
            return "mdi:shield-half-full"
        elif panel_data.get("disarmed"):
            return "mdi:shield-off"
        else:
            return "mdi:shield-question"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        panel_data = self.coordinator.panel_data
        if not panel_data:
            return {}
        
        return {
            "zones_firing": panel_data.get("zonesFiring", False),
            "zones_closed": panel_data.get("zonesClosed", False),
            "battery_status": panel_data.get("batteryStatus", "unknown"),
            "tamper": panel_data.get("tamper", False),
        }

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return self._get_device_info()

    def _get_device_info(self) -> DeviceInfo:
        """Get device info for the AMT-8000 panel."""
        panel_data = self.coordinator.panel_data
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.config_entry.entry_id)},
            name="AMT-8000 Alarm Panel",
            manufacturer="Intelbras",
            model=panel_data.get("model", "AMT-8000"),
            sw_version=panel_data.get("version", "Unknown"),
            configuration_url=f"http://{self.coordinator.config_entry.data['host']}",
        )


class AmtZoneCountSensor(CoordinatorEntity, SensorEntity):
    """Sensor showing number of paired zones."""

    _attr_has_entity_name = True
    _attr_name = "Paired Zones"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:counter"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: AmtCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_zone_count"

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._attr_native_value = len(self.coordinator.zones_data)
        self.async_write_ha_state()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        zones_data = self.coordinator.zones_data
        active_zones = sum(1 for status in zones_data.values() if status != "normal")
        
        return {
            "total_zones": len(zones_data),
            "active_zones": active_zones,
            "zone_list": list(zones_data.keys()),
        }

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return self._get_device_info()

    def _get_device_info(self) -> DeviceInfo:
        """Get device info for the AMT-8000 panel."""
        panel_data = self.coordinator.panel_data
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.config_entry.entry_id)},
            name="AMT-8000 Alarm Panel",
            manufacturer="Intelbras",
            model=panel_data.get("model", "AMT-8000"),
            sw_version=panel_data.get("version", "Unknown"),
            configuration_url=f"http://{self.coordinator.config_entry.data['host']}",
        )


class AMTZoneSensor(CoordinatorEntity, SensorEntity):
    """Represents a zone (sector) of the AMT-8000."""

    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_icon = "mdi:shield-check"

    def __init__(self, coordinator: AmtCoordinator, zone_id: str) -> None:
        """Initialize the zone sensor."""
        super().__init__(coordinator)
        self._zone_id = zone_id
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_zone_{zone_id}"
        self._attr_name = f"Zone {zone_id}"

    @property
    def native_value(self) -> str | None:
        """Return the state of the sensor."""
        zones_data = self.coordinator.zones_data
        zone_status = zones_data.get(self._zone_id, "normal")
        
        # Manejar estados múltiples (separados por coma)
        if isinstance(zone_status, str) and "," in zone_status:
            problems = zone_status.split(",")
            # Devolver el estado más crítico
            for critical_state in CRITICAL_STATES:
                if critical_state in problems:
                    return ZONE_STATE_MAP.get(critical_state, critical_state)
            # Si no hay estados críticos, devolver el primero mapeado
            for problem in problems:
                if problem in ZONE_STATE_MAP:
                    return ZONE_STATE_MAP[problem]
        
        # Estado simple
        return ZONE_STATE_MAP.get(zone_status, zone_status)

    @property
    def icon(self) -> str:
        """Return the icon for the sensor."""
        zone_status = self.coordinator.zones_data.get(self._zone_id, "normal")
        
        if any(critical in str(zone_status) for critical in CRITICAL_STATES):
            return "mdi:shield-alert"
        elif zone_status == "normal":
            return "mdi:shield-check"
        else:
            return "mdi:shield-half-full"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        zones_data = self.coordinator.zones_data
        zone_status = zones_data.get(self._zone_id, "normal")

        # Convertir estados separados por coma a lista
        if isinstance(zone_status, str) and "," in zone_status:
            problems = zone_status.split(",")
        else:
            problems = [zone_status] if zone_status else ["normal"]

        return {
            "raw_status": zone_status,
            "problems": problems,
            "zone_id": self._zone_id,
            "is_critical": any(critical in str(zone_status) for critical in CRITICAL_STATES),
        }

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return (
            self.coordinator.last_update_success 
            and self._zone_id in self.coordinator.zones_data
        )

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information for this zone sensor."""
        panel_data = self.coordinator.panel_data
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.config_entry.entry_id)},
            name="AMT-8000 Alarm Panel",
            manufacturer="Intelbras",
            model=panel_data.get("model", "AMT-8000"),
            sw_version=panel_data.get("version", "Unknown"),
            configuration_url=f"http://{self.coordinator.config_entry.data['host']}",
        )


class AMTZoneBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Binary sensor for zone alarm state."""

    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.SAFETY

    def __init__(self, coordinator: AmtCoordinator, zone_id: str) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self._zone_id = zone_id
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_zone_{zone_id}_alarm"
        self._attr_name = f"Zone {zone_id} Alarm"

    @property
    def is_on(self) -> bool | None:
        """Return True if the zone is in alarm state."""
        zones_data = self.coordinator.zones_data
        zone_status = zones_data.get(self._zone_id, "normal")
        
        # Considerar zona en alarma si tiene algún estado crítico
        return any(critical in str(zone_status) for critical in CRITICAL_STATES)

    @property
    def icon(self) -> str:
        """Return the icon for the sensor."""
        return "mdi:alarm-light" if self.is_on else "mdi:shield-check"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        zones_data = self.coordinator.zones_data
        zone_status = zones_data.get(self._zone_id, "normal")
        
        return {
            "zone_id": self._zone_id,
            "raw_status": zone_status,
            "alarm_active": self.is_on,
        }

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return (
            self.coordinator.last_update_success 
            and self._zone_id in self.coordinator.zones_data
        )

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information for this zone sensor."""
        panel_data = self.coordinator.panel_data
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.config_entry.entry_id)},
            name="AMT-8000 Alarm Panel",
            manufacturer="Intelbras",
            model=panel_data.get("model", "AMT-8000"),
            sw_version=panel_data.get("version", "Unknown"),
            configuration_url=f"http://{self.coordinator.config_entry.data['host']}",
        )
