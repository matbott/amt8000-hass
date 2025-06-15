"""Platform for sensor integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity # Importar SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity # Importar CoordinatorEntity

from .const import DOMAIN
from .coordinator import AmtCoordinator

LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensor platform."""
    coordinator: AmtCoordinator = hass.data[DOMAIN][config_entry.entry_id]['coordinator'] # Asume que el coordinador se guarda así
    
    # Si el coordinador no está en entry.data, se debe modificar __init__.py o coordinator.py
    # para que sea accesible. La integración actual lo hace directamente en coordinator.py
    # y lo pasa a alarm_control_panel.
    # Necesitamos acceder a la instancia del coordinador desde aquí.
    # Una forma segura es que en __init__.py lo guardes en hass.data[DOMAIN][entry.entry_id]['coordinator']
    # Por ahora, asumo que el coordinador se pasa directamente como data['coordinator']
    
    # Si tu coordinador se inicializa como antes, necesitamos una pequeña modificación en __init__.py
    # para que sea accesible aquí. La forma actual de tu init no lo guarda directamente.
    # Vamos a asumir que el coordinador es el que se pasa en el setup_entry en alarm_control_panel.py
    # Si el coordinador ya está disponible en hass.data[DOMAIN][config_entry.entry_id]['coordinator'] (por ejemplo, si lo añades en __init__.py),
    # puedes usarlo directamente.

    # Una forma de asegurar que el coordinador esté accesible para todos los sensores:
    # Modificar __init__.py para guardar la instancia del coordinador.
    # Ver la sección de "Notas Importantes" al final para esta modificación.
    
    # Por ahora, para que funcione con tu estructura actual (donde el coordinador se crea en cada plataforma):
    # Esto es menos eficiente si el coordinador ya se creó en alarm_control_panel.
    # Si el coordinador es compartido, el objeto debe ser el mismo.
    # Modificación para compartir el coordinador:
    isec_client = coordinator.isec_client # Reusa el cliente del coordinador
    password = coordinator.password
    
    entities: list[SensorEntity] = [
        AmtBatteryStatusSensor(coordinator),
    ]
    async_add_entities(entities)


class AmtBatteryStatusSensor(CoordinatorEntity, SensorEntity):
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

