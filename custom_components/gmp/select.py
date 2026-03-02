from __future__ import annotations

from datetime import date, timedelta

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([GMPHourlyDaySelect(coordinator)])


class GMPHourlyDaySelect(CoordinatorEntity, SelectEntity):
    def __init__(self, coordinator) -> None:
        super().__init__(coordinator)
        self._attr_has_entity_name = True
        self._attr_name = "GMP Hourly Day"
        self._attr_unique_id = f"{coordinator.account_id}_hourly_day"

        self._current = coordinator.selected_date.isoformat()

    @property
    def options(self) -> list[str]:
        today = date.today()
        return [(today - timedelta(days=offset)).isoformat() for offset in range(0, 31)]

    @property
    def current_option(self) -> str | None:
        selected = self.coordinator.data.get("selected_date")
        return selected or self._current

    async def async_select_option(self, option: str) -> None:
        self._current = option
        try:
            new_date = date.fromisoformat(option)
        except ValueError:
            return

        self.coordinator.set_selected_date(new_date)
        await self.coordinator.async_request_refresh()
