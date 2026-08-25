"""Config flow for Dummy OS Data."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .const import CONF_HOME_POWER_ENTITY, DEFAULT_HOME_POWER_ENTITY, DOMAIN, NAME


class DummyOSDataConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Dummy OS Data."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the initial step."""
        await self.async_set_unique_id("dummy_os_data_main")
        self._abort_if_unique_id_configured()

        errors: dict[str, str] = {}
        if user_input is not None:
            entity_id = user_input[CONF_HOME_POWER_ENTITY]
            state = self.hass.states.get(entity_id)
            if state is None:
                errors["base"] = "source_not_found"
            elif state.attributes.get("unit_of_measurement") not in {"W", "kW"}:
                errors["base"] = "unsupported_unit"
            else:
                return self.async_create_entry(
                    title=NAME,
                    data={CONF_HOME_POWER_ENTITY: entity_id},
                )

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_HOME_POWER_ENTITY,
                    default=DEFAULT_HOME_POWER_ENTITY,
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor")
                )
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        """Return the options flow."""
        return DummyOSDataOptionsFlow()


class DummyOSDataOptionsFlow(config_entries.OptionsFlow):
    """Handle Dummy OS Data options."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Manage options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = self.config_entry.options.get(
            CONF_HOME_POWER_ENTITY,
            self.config_entry.data.get(CONF_HOME_POWER_ENTITY, DEFAULT_HOME_POWER_ENTITY),
        )
        schema = vol.Schema(
            {
                vol.Required(CONF_HOME_POWER_ENTITY, default=current): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor")
                )
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
