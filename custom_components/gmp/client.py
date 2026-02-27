from __future__ import annotations

from dataclasses import dataclass
import calendar
from datetime import date, datetime, time as dtime, timezone
import base64
import json
import re
import time
from typing import Any, Optional
from urllib.parse import urlencode

import aiohttp

from .exceptions import GMPAuthError, GMPConnectionError

@dataclass(frozen=True)
class GMPTokens:
    access_token: str
    refresh_token: Optional[str]
    expires_at: float

class GMPClient:

    BASE_URL = "https://api.greenmountainpower.com/api/v2"
    GMP_SOURCE = "web"
    TEMP_UNIT = "f"

    def __init__(
        self,
        session: aiohttp.ClientSession,
        username: str,
        password: str,
        client_id: str,
    ):
        self._session = session
        self._username = username
        self._password = password
        self._client_id = client_id

        self._tokens: Optional[GMPTokens] = None

    async def async_login(self) -> None:
        url = f"{self.BASE_URL}/applications/token?remember_me=true"
        data = {
            "username": self._username,
            "password": self._password,
            "client_id": self._client_id,
        }
        headers = {
            "GMP-Source": self.GMP_SOURCE,
            "Content-Type": "application/x-www-form-urlencoded",
        }

        try:
            async with self._session.post(url, data=data, headers=headers) as resp:
                if resp.status in (401, 403):
                    raise GMPAuthError("Invalid credentials")

                resp.raise_for_status()
                result = await resp.json(content_type=None)
        except aiohttp.ClientError as err:
            raise GMPConnectionError(str(err)) from err

        self._tokens = self._parse_tokens(result)

    def _parse_tokens(self, result: dict[str, Any]) -> GMPTokens:
        access_token = result.get("access_token")
        if not access_token:
            raise GMPAuthError("Login response missing access_token")

        refresh_token = result.get("refresh_token")
        expires_in = result.get("expires_in")
        if not isinstance(expires_in, (int, float)):
            raise GMPAuthError("Login response missing expires_in")

        return GMPTokens(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=time.time() + float(expires_in),
        )

    async def async_refresh_token(self) -> None:
        if not self._tokens or not self._tokens.refresh_token:
            await self.async_login()
            return

        url = f"{self.BASE_URL}/applications/token"
        data = {
            "grant_type": "refresh_token",
            "refresh_token": self._tokens.refresh_token,
            "client_id": self._client_id,
        }
        headers = {
            "GMP-Source": self.GMP_SOURCE,
            "Content-Type": "application/x-www-form-urlencoded",
        }

        try:
            async with self._session.post(url, data=data, headers=headers) as resp:
                if resp.status in (401, 403):
                    raise GMPAuthError("Refresh token rejected")
                resp.raise_for_status()
                result = await resp.json(content_type=None)
        except aiohttp.ClientError as err:
            raise GMPConnectionError(str(err)) from err

        self._tokens = self._parse_tokens(result)

    async def async_ensure_token(self) -> None:
        if not self._tokens:
            await self.async_login()
            return

        if time.time() > self._tokens.expires_at - 60:
            await self.async_refresh_token()

    def _auth_headers(self) -> dict[str, str]:
        if not self._tokens:
            return {"GMP-Source": self.GMP_SOURCE}

        return {
            "Authorization": f"Bearer {self._tokens.access_token}",
            "GMP-Source": self.GMP_SOURCE,
        }

    def _with_params(self, base_url: str, params: dict[str, Any]) -> str:

        return f"{base_url}?{urlencode(params)}"

    async def _async_get_json(self, url: str, *, include_auth: bool = True) -> dict[str, Any]:
        await self.async_ensure_token()

        headers = self._auth_headers() if include_auth else {"GMP-Source": self.GMP_SOURCE}

        try:
            async with self._session.get(url, headers=headers) as resp:
                if resp.status in (401, 403) and include_auth:
                    await self.async_refresh_token()
                    async with self._session.get(url, headers=self._auth_headers()) as retry_resp:
                        if retry_resp.status >= 400:
                            body = await retry_resp.text()
                            if retry_resp.status in (401, 403):
                                raise GMPAuthError("Unauthorized")
                            raise GMPConnectionError(
                                f"{retry_resp.status} for {url}: {body[:500]}"
                            )
                        return await retry_resp.json(content_type=None)

                if resp.status >= 400:
                    body = await resp.text()
                    if resp.status in (401, 403):
                        raise GMPAuthError("Unauthorized")
                    raise GMPConnectionError(f"{resp.status} for {url}: {body[:500]}")

                return await resp.json(content_type=None)
        except aiohttp.ClientError as err:
            raise GMPConnectionError(str(err)) from err

    async def async_get_account_status(self, account_id: str) -> dict[str, Any]:
        url = f"{self.BASE_URL}/accounts/{account_id}/status"
        return await self._async_get_json(url)

    def _token_claims(self) -> dict[str, Any] | None:

        if not self._tokens or not isinstance(self._tokens.access_token, str):
            return None

        token = self._tokens.access_token
        parts = token.split(".")
        if len(parts) != 3:
            return None

        payload = parts[1]
        pad = "=" * (-len(payload) % 4)
        try:
            decoded = base64.urlsafe_b64decode(payload + pad)
            data = json.loads(decoded.decode("utf-8"))
        except Exception:
            return None

        return data if isinstance(data, dict) else None

    def _extract_account_ids(self, obj: Any, *, depth: int = 0) -> set[str]:

        if depth > 6:
            return set()

        found: set[str] = set()

        def _maybe_add(value: Any) -> None:
            if isinstance(value, int):
                s = str(value)
            elif isinstance(value, str):
                s = value.strip()
            else:
                return

            if re.fullmatch(r"\d{6,}", s):
                found.add(s)

        if isinstance(obj, dict):
            for key, value in obj.items():
                if key in {"accountId", "account_id", "accountNumber", "account"}:
                    _maybe_add(value)
                found |= self._extract_account_ids(value, depth=depth + 1)
            return found

        if isinstance(obj, list):
            for item in obj:
                if isinstance(item, str) and re.fullmatch(r"\d{6,}", item.strip()):
                    found.add(item.strip())
                found |= self._extract_account_ids(item, depth=depth + 1)
            return found

        return found

    async def async_discover_account_ids(self) -> list[str]:

        await self.async_ensure_token()

        account_ids: set[str] = set()

        try:
            me = await self._async_get_json(f"{self.BASE_URL}/users/current")
            account_ids |= self._extract_account_ids(me)
        except Exception:
            pass

        claims = self._token_claims()
        if claims:
            account_ids |= self._extract_account_ids(claims)

        for path in ("/accounts", "/accounts?active=true"):
            url = f"{self.BASE_URL}{path}"
            try:
                data = await self._async_get_json(url)
            except Exception:
                continue
            account_ids |= self._extract_account_ids(data)

        return sorted(account_ids)

    async def async_get_monthly_usage(self, account_id: str) -> dict[str, Any]:
        base_url = f"{self.BASE_URL}/usage/{account_id}/monthly"

        now = datetime.now().astimezone()
        local_tz = now.tzinfo
        start_year = now.year
        start_month = now.month - 12
        while start_month <= 0:
            start_month += 12
            start_year -= 1

        range_start = datetime(start_year, start_month, 1, 0, 0, 0, tzinfo=local_tz)
        last_day = calendar.monthrange(now.year, now.month)[1]
        range_end = datetime(now.year, now.month, last_day, 23, 59, 59, tzinfo=local_tz)

        range_params_dt = {
            "startDate": range_start.isoformat(),
            "endDate": range_end.isoformat(),
            "temp": self.TEMP_UNIT,
        }
        range_params_date = {
            "startDate": range_start.date().isoformat(),
            "endDate": range_end.date().isoformat(),
            "temp": self.TEMP_UNIT,
        }

        urls = [
            base_url,
            self._with_params(base_url, {"temp": self.TEMP_UNIT}),
            self._with_params(base_url, range_params_date),
            self._with_params(base_url, range_params_dt),
        ]

        last_err: Exception | None = None
        for url in urls:
            for include_auth in (True, False):
                try:
                    return await self._async_get_json(url, include_auth=include_auth)
                except Exception as err:
                    last_err = err
        assert last_err is not None
        raise last_err

    async def async_get_daily_usage(self, account_id: str) -> dict[str, Any]:
        base_url = f"{self.BASE_URL}/usage/{account_id}/daily"
        urls = [self._with_params(base_url, {"temp": self.TEMP_UNIT}), base_url]

        now = datetime.now().astimezone()
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        last_day = calendar.monthrange(month_start.year, month_start.month)[1]
        month_end = month_start.replace(day=last_day, hour=23, minute=59, second=59)

        urls.append(
            self._with_params(
                base_url,
                {
                    "startDate": month_start.date().isoformat(),
                    "endDate": month_end.date().isoformat(),
                    "temp": self.TEMP_UNIT,
                },
            )
        )
        urls.append(
            self._with_params(
                base_url,
                {
                    "startDate": month_start.isoformat(),
                    "endDate": month_end.isoformat(),
                    "temp": self.TEMP_UNIT,
                },
            )
        )

        last_err: Exception | None = None
        for url in urls:
            for include_auth in (True, False):
                try:
                    return await self._async_get_json(url, include_auth=include_auth)
                except Exception as err:
                    last_err = err
        assert last_err is not None
        raise last_err

    async def async_get_hourly_for_day(self, account_id: str, day: date) -> dict[str, Any]:
        local_tz = datetime.now().astimezone().tzinfo
        start = datetime.combine(day, dtime.min).replace(tzinfo=local_tz)
        end = datetime.combine(day, dtime(23, 59, 59)).replace(tzinfo=local_tz)
        return await self.async_get_hourly(account_id, start, end)

    async def async_get_ev_energy_daily(self, account_id: str) -> dict[str, Any]:
        base_url = f"{self.BASE_URL}/device/account/{account_id}/ev/energy/daily"

        now = datetime.now().astimezone()
        local_tz = now.tzinfo
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        last_day = calendar.monthrange(month_start.year, month_start.month)[1]
        month_end = datetime(
            month_start.year,
            month_start.month,
            last_day,
            23,
            59,
            59,
            tzinfo=local_tz,
        )

        urls = [
            self._with_params(
                base_url,
                {"startDate": month_start.date().isoformat(), "endDate": month_end.date().isoformat()},
            ),
            self._with_params(
                base_url,
                {"startDate": month_start.isoformat(), "endDate": month_end.isoformat()},
            ),
            self._with_params(
                base_url,
                {"start": month_start.isoformat(), "end": month_end.isoformat()},
            ),
            self._with_params(
                base_url,
                {"start": month_start.date().isoformat(), "end": month_end.date().isoformat()},
            ),
        ]

        last_err: Exception | None = None
        for url in urls:
            for include_auth in (True, False):
                try:
                    return await self._async_get_json(url, include_auth=include_auth)
                except Exception as err:
                    last_err = err

        assert last_err is not None
        raise last_err

    async def async_get_hourly(
        self,
        account_id: str,
        start: datetime,
        end: datetime,
    ) -> dict[str, Any]:
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)

        url = self._with_params(
            f"{self.BASE_URL}/usage/{account_id}/hourly",
            {
                "startDate": start.isoformat(),
                "endDate": end.isoformat(),
                "temp": self.TEMP_UNIT,
            },
        )

        return await self._async_get_json(url)

    async def async_get_usage_summary(self, account_id: str) -> dict[str, Any]:

        now = datetime.now().astimezone()
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        data = await self.async_get_hourly(account_id, start, now)

        intervals = data.get("intervals") or []
        if not intervals:
            return {
                "hourly_values": [],
                "today_total": 0,
                "last_hour_kwh": 0,
            }

        values = intervals[0].get("values") or []
        total_today = 0.0
        last_consumed = 0.0

        for item in values:
            consumed = item.get("consumed")
            if isinstance(consumed, (int, float)):
                total_today += float(consumed)
                last_consumed = float(consumed)

        return {
            "hourly_values": values,
            "today_total": round(total_today, 2),
            "last_hour_kwh": round(last_consumed, 3),
        }
