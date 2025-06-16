"""The AMT-8000 integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall, callback

from .const import DOMAIN
from .coordinator import AmtCoordinator # <-- AÑADIDO: Importar el coordinador
from .isec2.client import Client as ISecClient # <-- AÑADIDO: Importar el cliente ISEC


LOGGER = logging.getLogger(__name__)

# AÑADIDO "sensor" a la lista de plataformas
PLATFORMS: list[str] = ["alarm_control_panel", "sensor"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up AMT-8000 from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    # AÑADIDO: Crear la instancia del cliente ISEC
    isec_client = ISecClient(entry.data["host"], entry.data["port"])

    # AÑADIDO: Crear la instancia del coordinador, pasándole la 'entry' completa
    coordinator = AmtCoordinator(hass, isec_client, entry.data["password"], entry)

    # AÑADIDO: Realizar la primera actualización para obtener datos iniciales y las zonas emparejadas
    await coordinator.async_config_entry_first_refresh()

    # MODIFICADO: Guardar el coordinador y la configuración en hass.data
    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "config": entry.data, # Mantener la configuración original también para accesos directos
        # No es necesario guardar isec_client aquí directamente, el coordinador lo tiene.
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
