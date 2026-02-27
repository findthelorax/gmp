from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_ACCOUNT_ID,
    CONF_CLIENT_ID,
    CONF_PASSWORD,
    CONF_USERNAME,
    DEFAULT_CLIENT_ID,
    DOMAIN,
)
from .coordinator import GMPCoordinator
from .client import GMPClient

PLATFORMS = ["sensor", "select"]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    hass.data.setdefault(DOMAIN, {})

    session = async_get_clientsession(hass)
    client = GMPClient(
        session=session,
        username=entry.data[CONF_USERNAME],
        password=entry.data[CONF_PASSWORD],
        client_id=entry.data.get(CONF_CLIENT_ID, DEFAULT_CLIENT_ID),
    )

    coordinator = GMPCoordinator(
        hass,
        client,
        entry.data[CONF_ACCOUNT_ID],
    )

    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
