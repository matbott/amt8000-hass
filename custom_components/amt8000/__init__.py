"""The AMT-8000 integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN
from .coordinator import AmtCoordinator
from .isec2.client import Client as ISecClient, CommunicationError

LOGGER = logging.getLogger(__name__)

# Plataformas soportadas por la integración
PLATFORMS: list[str] = ["alarm_control_panel", "sensor", "binary_sensor"] 

async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the AMT-8000 integration."""
    hass.data.setdefault(DOMAIN, {})
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up AMT-8000 from a config entry."""
    
    # Validar que tenemos todos los datos necesarios
    if not all(key in entry.data for key in ["host", "port", "password"]):
        LOGGER.error("Missing required configuration data")
        return False
    
    # Inicializar el dominio en hass.data si no existe
    hass.data.setdefault(DOMAIN, {})
    
    try:
        # Crear la instancia del cliente ISEC
        isec_client = ISecClient(
            host=entry.data["host"], 
            port=entry.data["port"]
        )
        
        # Crear la instancia del coordinador
        coordinator = AmtCoordinator(
            hass=hass,
            client=isec_client,
            password=entry.data["password"],
            config_entry=entry
        )
        
        # Realizar la primera actualización para obtener datos iniciales
        LOGGER.info("Performing initial data refresh for AMT-8000")
        try:
            await coordinator.async_config_entry_first_refresh()
        except Exception as err:
            LOGGER.error("Failed to perform initial refresh: %s", err)
            raise ConfigEntryNotReady(f"Failed to connect to AMT-8000: {err}") from err
        
        # Guardar el coordinador en hass.data
        hass.data[DOMAIN][entry.entry_id] = {
            "coordinator": coordinator,
            "config": entry.data,
        }
        
        # Configurar las plataformas
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        
        # Registrar servicios personalizados
        await _async_setup_services(hass, entry)
        
        LOGGER.info("AMT-8000 integration setup completed successfully")
        return True
        
    except CommunicationError as err:
        LOGGER.error("Communication error during setup: %s", err)
        raise ConfigEntryNotReady(f"Cannot connect to AMT-8000 at {entry.data['host']}:{entry.data['port']}") from err
        
    except Exception as err:
        LOGGER.error("Unexpected error during setup: %s", err)
        return False

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    
    # Descargar las plataformas
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    
    if unload_ok:
        # Limpiar datos almacenados
        coordinator_data = hass.data[DOMAIN].pop(entry.entry_id, None)
        
        # Limpiar el coordinador si existe
        if coordinator_data and "coordinator" in coordinator_data:
            coordinator = coordinator_data["coordinator"]
            # Asegurar que se cierre la conexión
            try:
                if hasattr(coordinator, 'client') and coordinator.client:
                    coordinator.client.close()
            except Exception as err:
                LOGGER.debug("Error closing client during unload: %s", err)
        
        # Desregistrar servicios si no hay más entradas
        if not hass.data[DOMAIN]:
            await _async_unload_services(hass)
        
        LOGGER.info("AMT-8000 integration unloaded successfully")
    
    return unload_ok

async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry."""
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)

async def _async_setup_services(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Set up services for AMT-8000."""
    
    async def async_refresh_zones(call: Any) -> None:
        """Service to refresh paired zones."""
        entry_id = call.data.get("entry_id")
        if not entry_id:
            # Si no se especifica entry_id, usar la primera entrada disponible
            entries = [e for e in hass.config_entries.async_entries(DOMAIN)]
            if entries:
                entry_id = entries[0].entry_id
            else:
                LOGGER.error("No AMT-8000 entries found")
                return
        
        coordinator_data = hass.data[DOMAIN].get(entry_id)
        if not coordinator_data:
            LOGGER.error("AMT-8000 entry not found: %s", entry_id)
            return
        
        coordinator = coordinator_data["coordinator"]
        await coordinator.async_refresh_zones()
        LOGGER.info("Zones refresh completed for entry %s", entry_id)
    
    # Registrar el servicio solo si aún no existe
    if not hass.services.has_service(DOMAIN, "refresh_zones"):
        hass.services.async_register(
            DOMAIN,
            "refresh_zones",
            async_refresh_zones,
            schema=None,  # Podrías agregar un schema de validación aquí
        )

async def _async_unload_services(hass: HomeAssistant) -> None:
    """Unload services when no entries remain."""
    if hass.services.has_service(DOMAIN, "refresh_zones"):
        hass.services.async_remove(DOMAIN, "refresh_zones")

async def async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Migrate old entry."""
    LOGGER.debug("Migrating from version %s", config_entry.version)
    
    if config_entry.version == 1:
        # Ejemplo de migración - ajusta según tus necesidades
        new_data = {**config_entry.data}
        
        # Agregar nuevos campos con valores por defecto si es necesario
        if "timeout" not in new_data:
            new_data["timeout"] = 10
        
        config_entry.version = 2
        hass.config_entries.async_update_entry(config_entry, data=new_data)
    
    LOGGER.info("Migration to version %s successful", config_entry.version)
    return True
