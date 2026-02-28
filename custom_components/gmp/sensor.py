from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN


def _strip_usage_values(values: list[dict[str, Any]]) -> list[dict[str, Any]]:
    allowed = {"date", "consumed", "consumedTotal"}
    stripped: list[dict[str, Any]] = []
    for item in values:
        if not isinstance(item, dict):
            continue
        stripped.append({k: item.get(k) for k in allowed if k in item})
    return stripped


def _first_interval(data: dict[str, Any] | None) -> dict[str, Any] | None:

    intervals = (data or {}).get("intervals") or []
    if not isinstance(intervals, list) or not intervals:
        return None

    for item in intervals:
        if isinstance(item, dict):
            return item
    return None


def _usage_values(data: dict[str, Any] | None) -> list[dict[str, Any]]:

    if not data:
        return []

    interval = _first_interval(data)
    if interval and isinstance(interval.get("values"), list):
        return [v for v in interval.get("values") if isinstance(v, dict)]

    if isinstance(data.get("values"), list):
        return [v for v in data.get("values") if isinstance(v, dict)]

    nested = data.get("data")
    if isinstance(nested, dict):
        return _usage_values(nested)

    # Last resort: find the first list[dict] that looks like usage values.
    for value in data.values():
        if isinstance(value, dict):
            values = _usage_values(value)
            if values:
                return values
        if isinstance(value, list) and value and all(isinstance(v, dict) for v in value):
            if any(
                isinstance(v, dict) and ("consumed" in v or "consumedTotal" in v or "date" in v)
                for v in value
            ):
                return value

    return []


def _usage_start_end(data: dict[str, Any] | None) -> tuple[Any, Any]:
    interval = _first_interval(data)
    if not interval:
        return None, None
    return interval.get("start"), interval.get("end")


def _latest_numeric(values: list[dict[str, Any]], key: str) -> float | None:

    for item in reversed(values):
        if not isinstance(item, dict):
            continue
        val = item.get(key)
        if isinstance(val, (int, float)):
            return float(val)
    return None


def _latest_numeric_any(values: list[dict[str, Any]], keys: tuple[str, ...]) -> float | None:

    for item in reversed(values):
        if not isinstance(item, dict):
            continue
        for key in keys:
            val = item.get(key)
            if isinstance(val, (int, float)):
                return float(val)
    return None


def _power_status(status: dict[str, Any] | None) -> str | None:

    if not status:
        return None
    if bool(status.get("meterOff")):
        return "off"
    if bool(status.get("partialMeterOff")):
        return "partial"
    return "on"

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
):
    coordinator = hass.data[DOMAIN][entry.entry_id]

    async_add_entities(
        [
            GMPTodayEnergySensor(coordinator),
            GMPLastHourEnergySensor(coordinator),
            GMPAccountStatusSensor(coordinator),
            GMPPowerStatusSensor(coordinator),
            GMPMonthlyUsageSensor(coordinator),
            GMPSelectedDayTotalSensor(coordinator),
            GMPEVEnergyPeriodConsumptionSensor(coordinator),
            GMPEVEnergyPeriodCostSensor(coordinator),
            GMPEVSelectedDayConsumptionSensor(coordinator),
            GMPEVSelectedDayCostSensor(coordinator),
        ]
    )

class GMPBaseSensor(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator, name, unique):
        super().__init__(coordinator)
        self._attr_name = name
        self._attr_unique_id = unique
        self._attr_has_entity_name = True

class GMPTodayEnergySensor(GMPBaseSensor):
    def __init__(self, coordinator):
        super().__init__(
            coordinator,
            "GMP Energy Today",
            f"{coordinator.account_id}_energy_today",
        )
        self._attr_native_unit_of_measurement = "kWh"
        self._attr_device_class = SensorDeviceClass.ENERGY

    @property
    def native_value(self):
        return self.coordinator.data.get("today_total")

    @property
    def extra_state_attributes(self):
        hourly = self.coordinator.data.get("hourly_values") or []
        return {
            "hourly": _strip_usage_values(hourly)
        }

class GMPLastHourEnergySensor(GMPBaseSensor):
    def __init__(self, coordinator):
        super().__init__(
            coordinator,
            "GMP Last Hour Usage",
            f"{coordinator.account_id}_last_hour_usage",
        )
        self._attr_native_unit_of_measurement = "kWh"
        self._attr_device_class = SensorDeviceClass.ENERGY

    @property
    def native_value(self):
        return self.coordinator.data.get("last_hour_kwh")


class GMPAccountStatusSensor(GMPBaseSensor):
    def __init__(self, coordinator):
        super().__init__(
            coordinator,
            "GMP Account Status",
            f"{coordinator.account_id}_status",
        )

    @property
    def native_value(self) -> str | None:
        status: dict[str, Any] | None = self.coordinator.data.get("status")
        if not status:
            return None
        return "active" if status.get("active") else "inactive"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        status = self.coordinator.data.get("status") or {}
        return {
            **status,
            "power_status": _power_status(status),
        }


class GMPPowerStatusSensor(GMPBaseSensor):
    def __init__(self, coordinator):
        super().__init__(
            coordinator,
            "GMP Power Status",
            f"{coordinator.account_id}_power_status",
        )

    @property
    def native_value(self) -> str | None:
        status: dict[str, Any] | None = self.coordinator.data.get("status")
        return _power_status(status)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return self.coordinator.data.get("status") or {}


class GMPDailyUsageSensor(GMPBaseSensor):
    def __init__(self, coordinator):
        super().__init__(
            coordinator,
            "GMP Daily Usage",
            f"{coordinator.account_id}_daily_usage",
        )
        self._attr_native_unit_of_measurement = "kWh"
        self._attr_device_class = SensorDeviceClass.ENERGY

    @property
    def native_value(self) -> float | None:
        daily: dict[str, Any] | None = self.coordinator.data.get("daily")
        values = _usage_values(daily)
        if not values:
            return None
        return _latest_numeric_any(values, ("consumed", "consumedTotal"))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        daily: dict[str, Any] | None = self.coordinator.data.get("daily")
        start, end = _usage_start_end(daily)
        values = _usage_values(daily)
        return {
            "start": start,
            "end": end,
            "values": _strip_usage_values(values),
        }


class GMPMonthlyUsageSensor(GMPBaseSensor):
    def __init__(self, coordinator):
        super().__init__(
            coordinator,
            "GMP Monthly Usage",
            f"{coordinator.account_id}_monthly_usage",
        )
        self._attr_native_unit_of_measurement = "kWh"
        self._attr_device_class = SensorDeviceClass.ENERGY

    @property
    def native_value(self) -> float | None:
        monthly: dict[str, Any] | None = self.coordinator.data.get("monthly")
        values = _usage_values(monthly)
        if not values:
            return None
        return _latest_numeric_any(values, ("consumed", "consumedTotal"))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        monthly: dict[str, Any] | None = self.coordinator.data.get("monthly")
        start, end = _usage_start_end(monthly)
        values = _usage_values(monthly)
        errors = self.coordinator.data.get("errors") or {}
        return {
            "start": start,
            "end": end,
            "values": _strip_usage_values(values),
            "fetch_error": errors.get("monthly"),
        }


class GMPSelectedDayTotalSensor(GMPBaseSensor):
    def __init__(self, coordinator):
        super().__init__(
            coordinator,
            "GMP Selected Day Total",
            f"{coordinator.account_id}_selected_day_total",
        )
        self._attr_native_unit_of_measurement = "kWh"
        self._attr_device_class = SensorDeviceClass.ENERGY

    @property
    def native_value(self) -> float | None:
        selected: dict[str, Any] | None = self.coordinator.data.get("selected_hourly")
        values = _usage_values(selected)
        if not values:
            return None
        total = 0.0
        seen_any = False
        for item in values:
            consumed = item.get("consumed")
            if isinstance(consumed, (int, float)):
                total += float(consumed)
                seen_any = True
        if seen_any:
            return round(total, 2)

        # Fallback: Some responses only include cumulative totals.
        consumed_total = _latest_numeric_any(values, ("consumedTotal",))
        return round(consumed_total, 2) if consumed_total is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        selected: dict[str, Any] | None = self.coordinator.data.get("selected_hourly")
        values = _usage_values(selected)
        errors = self.coordinator.data.get("errors") or {}
        return {
            "selected_date": self.coordinator.data.get("selected_date"),
            "values": _strip_usage_values(values),
            "fetch_error": errors.get("selected_hourly"),
        }


def _ev_interval(data: dict[str, Any] | None) -> dict[str, Any] | None:
    intervals = (data or {}).get("intervals") or []
    if not intervals:
        return None
    first = intervals[0]
    return first if isinstance(first, dict) else None


def _ev_selected_day_value(
    ev_daily: dict[str, Any] | None, selected_date: str | None
) -> dict[str, Any] | None:
    interval = _ev_interval(ev_daily)
    if not interval or not selected_date:
        return None

    for item in interval.get("values") or []:
        if not isinstance(item, dict):
            continue
        item_date = item.get("date")
        if isinstance(item_date, str) and item_date[:10] == selected_date:
            return item
    return None


class GMPEVEnergyPeriodConsumptionSensor(GMPBaseSensor):
    def __init__(self, coordinator):
        super().__init__(
            coordinator,
            "GMP EV Charging Consumption",
            f"{coordinator.account_id}_ev_total_consumption",
        )
        self._attr_native_unit_of_measurement = "kWh"
        self._attr_device_class = SensorDeviceClass.ENERGY

    @property
    def native_value(self) -> float | None:
        ev_daily: dict[str, Any] | None = self.coordinator.data.get("ev_daily")
        interval = _ev_interval(ev_daily)
        if not interval:
            return None
        total = interval.get("totalConsumption")
        return float(total) if isinstance(total, (int, float)) else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        ev_daily: dict[str, Any] | None = self.coordinator.data.get("ev_daily")
        interval = _ev_interval(ev_daily) or {}
        rates = (ev_daily or {}).get("rates")
        return {
            "start": interval.get("start"),
            "end": interval.get("end"),
            "totalCost": interval.get("totalCost"),
            "totalSavings": interval.get("totalSavings"),
            "totalChargeTime": interval.get("totalChargeTime"),
            "totalOnPeakConsumption": interval.get("totalOnPeakConsumption"),
            "totalOffPeakConsumption": interval.get("totalOffPeakConsumption"),
            "totalOnPeakCost": interval.get("totalOnPeakCost"),
            "totalOffPeakCost": interval.get("totalOffPeakCost"),
            "rates": rates,
        }


class GMPEVEnergyPeriodCostSensor(GMPBaseSensor):
    def __init__(self, coordinator):
        super().__init__(
            coordinator,
            "GMP EV Charging Cost",
            f"{coordinator.account_id}_ev_total_cost",
        )
        self._attr_native_unit_of_measurement = coordinator.hass.config.currency
        self._attr_device_class = SensorDeviceClass.MONETARY

    @property
    def native_value(self) -> float | None:
        ev_daily: dict[str, Any] | None = self.coordinator.data.get("ev_daily")
        interval = _ev_interval(ev_daily)
        if not interval:
            return None
        total = interval.get("totalCost")
        return float(total) if isinstance(total, (int, float)) else None


class GMPEVSelectedDayConsumptionSensor(GMPBaseSensor):
    def __init__(self, coordinator):
        super().__init__(
            coordinator,
            "GMP EV Selected Day Consumption",
            f"{coordinator.account_id}_ev_selected_day_consumption",
        )
        self._attr_native_unit_of_measurement = "kWh"
        self._attr_device_class = SensorDeviceClass.ENERGY

    @property
    def native_value(self) -> float | None:
        ev_daily: dict[str, Any] | None = self.coordinator.data.get("ev_daily")
        selected_date: str | None = self.coordinator.data.get("selected_date")
        item = _ev_selected_day_value(ev_daily, selected_date)
        if not item:
            return None
        consumed = item.get("consumed")
        return float(consumed) if isinstance(consumed, (int, float)) else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        ev_daily: dict[str, Any] | None = self.coordinator.data.get("ev_daily")
        selected_date: str | None = self.coordinator.data.get("selected_date")
        item = _ev_selected_day_value(ev_daily, selected_date) or {}
        return {
            "selected_date": selected_date,
            "cost": item.get("cost"),
            "savings": item.get("savings"),
            "duration": item.get("duration"),
            "onPeakConsumed": item.get("onPeakConsumed"),
            "offPeakConsumed": item.get("offPeakConsumed"),
            "onPeakCost": item.get("onPeakCost"),
            "offPeakCost": item.get("offPeakCost"),
            "onPeakDuration": item.get("onPeakDuration"),
            "offPeakDuration": item.get("offPeakDuration"),
        }


class GMPEVSelectedDayCostSensor(GMPBaseSensor):
    def __init__(self, coordinator):
        super().__init__(
            coordinator,
            "GMP EV Selected Day Cost",
            f"{coordinator.account_id}_ev_selected_day_cost",
        )
        self._attr_native_unit_of_measurement = coordinator.hass.config.currency
        self._attr_device_class = SensorDeviceClass.MONETARY

    @property
    def native_value(self) -> float | None:
        ev_daily: dict[str, Any] | None = self.coordinator.data.get("ev_daily")
        selected_date: str | None = self.coordinator.data.get("selected_date")
        item = _ev_selected_day_value(ev_daily, selected_date)
        if not item:
            return None
        cost = item.get("cost")
        return float(cost) if isinstance(cost, (int, float)) else None
