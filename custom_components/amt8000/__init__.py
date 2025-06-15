"""The AMT-8000 integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall, callback

from .const import DOMAIN
from .isec2.client import Client as ISecClient # Importar el cliente
from .coordinator import AmtCoordinator # Importar el coordinador

LOGGER = logging.getLogger(__name__)

# Agregamos 'sensor' y 'binary_sensor' a la lista de plataformas
PLATFORMS: list[str] = ["alarm_control_panel", "sensor", "binary_sensor"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up AMT-8000 from a config entry."""

    # Creamos el cliente y el coordinador una sola vez
    isec_client = ISecClient(entry.data["host"], entry.data["port"])
    coordinator = AmtCoordinator(hass, isec_client, entry.data["password"], entry) # Pasamos 'entry' al coordinador
    
    # Realizamos la primera actualización de datos para asegurar que haya algo antes de que se carguen las entidades
    await coordinator.async_config_entry_first_refresh()

    # Guardamos la instancia del coordinador en hass.data para que otras plataformas puedan acceder a ella
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        # Puedes guardar aquí otros datos de la configuración si es necesario,
        # pero el coordinador ya tiene el cliente y la contraseña.
        "host": entry.data["host"],
        "port": entry.data["port"],
        "password": entry.data["password"],
    }

    # Ahora forwardeamos la configuración a todas las plataformas
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok

