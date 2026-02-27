from datetime import date, timedelta
import logging
import asyncio

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import UpdateFailed

from .const import DOMAIN, DEFAULT_SCAN_INTERVAL
from .exceptions import GMPError

_LOGGER = logging.getLogger(__name__)

class GMPCoordinator(DataUpdateCoordinator):
    def __init__(self, hass: HomeAssistant, client, account_id: str):
        super().__init__(
            hass,
            logger=_LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )

        self.client = client
        self.account_id = account_id
        self.selected_date: date = date.today()

    def set_selected_date(self, new_date: date) -> None:
        self.selected_date = new_date

    async def _async_update_data(self):
        try:
            usage_summary, status = await asyncio.gather(
                self.client.async_get_usage_summary(self.account_id),
                self.client.async_get_account_status(self.account_id),
            )

            optional_results = await asyncio.gather(
                self.client.async_get_monthly_usage(self.account_id),
                self.client.async_get_daily_usage(self.account_id),
                self.client.async_get_hourly_for_day(self.account_id, self.selected_date),
                self.client.async_get_ev_energy_daily(self.account_id),
                return_exceptions=True,
            )

            monthly, daily, selected_hourly, ev_daily = optional_results
            errors: dict[str, str] = {}

            if isinstance(monthly, Exception):
                errors["monthly"] = str(monthly)
                _LOGGER.warning("GMP monthly fetch failed: %s", monthly)
                monthly = {}
            if isinstance(daily, Exception):
                errors["daily"] = str(daily)
                _LOGGER.warning("GMP daily fetch failed: %s", daily)
                daily = {}
            if isinstance(selected_hourly, Exception):
                errors["selected_hourly"] = str(selected_hourly)
                _LOGGER.warning("GMP selected-hourly fetch failed: %s", selected_hourly)
                selected_hourly = {}
            if isinstance(ev_daily, Exception):
                errors["ev_daily"] = str(ev_daily)
                _LOGGER.warning("GMP EV daily fetch failed: %s", ev_daily)
                ev_daily = {}

            return {
                **usage_summary,
                "status": status,
                "monthly": monthly,
                "daily": daily,
                "selected_date": self.selected_date.isoformat(),
                "selected_hourly": selected_hourly,
                "ev_daily": ev_daily,
                "errors": errors,
            }
        except GMPError as err:
            raise UpdateFailed(str(err)) from err
        