import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .client import GMPClient
from .const import (
    CONF_ACCOUNT_ID,
    CONF_CLIENT_ID,
    CONF_PASSWORD,
    CONF_USERNAME,
    DEFAULT_CLIENT_ID,
    DOMAIN,
)
from .exceptions import GMPAuthError, GMPConnectionError

class GMPConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        super().__init__()
        self._pending_creds: dict[str, str] | None = None
        self._discovered_accounts: list[str] = []

    async def _async_login(self, username: str, password: str) -> GMPClient:
        session = async_get_clientsession(self.hass)
        client = GMPClient(
            session=session,
            username=username,
            password=password,
            client_id=DEFAULT_CLIENT_ID,
        )
        await client.async_login()
        return client

    async def _async_discover_accounts(self, client: GMPClient) -> list[str]:
        try:
            return await client.async_discover_account_ids()
        except Exception:  # noqa: BLE001
            return []

    async def _async_create_entry(self, *, username: str, password: str, account_id: str):
        await self.async_set_unique_id(account_id)
        self._abort_if_unique_id_configured()

        return self.async_create_entry(
            title="Green Mountain Power",
            data={
                CONF_USERNAME: username,
                CONF_PASSWORD: password,
                CONF_ACCOUNT_ID: account_id,
                # Store for forward compatibility (and potential future options flow).
                CONF_CLIENT_ID: DEFAULT_CLIENT_ID,
            },
        )

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            username = user_input[CONF_USERNAME]
            password = user_input[CONF_PASSWORD]

            try:
                client = await self._async_login(username, password)
            except GMPAuthError:
                errors["base"] = "invalid_auth"
            except GMPConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:
                errors["base"] = "unknown"
            else:
                accounts = await self._async_discover_accounts(client)
                self._pending_creds = {CONF_USERNAME: username, CONF_PASSWORD: password}
                self._discovered_accounts = accounts

                if len(accounts) == 1:
                    return await self._async_create_entry(
                        username=username, password=password, account_id=accounts[0]
                    )

                if len(accounts) > 1:
                    return await self.async_step_account_select()

                # Discovery failed; ask the user for the account id.
                return await self.async_step_account()

        data_schema = vol.Schema(
            {
                vol.Required(CONF_USERNAME): str,
                vol.Required(CONF_PASSWORD): str,
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
        )

    async def async_step_account_select(self, user_input=None):
        errors: dict[str, str] = {}
        if user_input is not None:
            assert self._pending_creds is not None
            account_id = user_input[CONF_ACCOUNT_ID]
            return await self._async_create_entry(
                username=self._pending_creds[CONF_USERNAME],
                password=self._pending_creds[CONF_PASSWORD],
                account_id=account_id,
            )

        options = self._discovered_accounts or []
        if not options:
            return await self.async_step_account()

        schema = vol.Schema({vol.Required(CONF_ACCOUNT_ID): vol.In(options)})
        return self.async_show_form(
            step_id="account_select",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_account(self, user_input=None):
        errors: dict[str, str] = {}
        if user_input is not None:
            assert self._pending_creds is not None
            account_id = str(user_input[CONF_ACCOUNT_ID]).strip()
            if not account_id:
                errors["base"] = "unknown"
            else:
                return await self._async_create_entry(
                    username=self._pending_creds[CONF_USERNAME],
                    password=self._pending_creds[CONF_PASSWORD],
                    account_id=account_id,
                )

        schema = vol.Schema({vol.Required(CONF_ACCOUNT_ID): str})
        return self.async_show_form(
            step_id="account",
            data_schema=schema,
            errors=errors,
        )