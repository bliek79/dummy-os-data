"""Config flow for Dummy OS Data."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .const import (
    CONF_ELECTRICITY_EXPORT_SUPPLIER,
    CONF_ELECTRICITY_EXPORT_TAX,
    CONF_ELECTRICITY_FIXED_SUPPLY_PER_DAY,
    CONF_ELECTRICITY_GRID_PER_DAY,
    CONF_ELECTRICITY_IMPORT_SUPPLIER,
    CONF_ELECTRICITY_IMPORT_TAX,
    CONF_ELECTRICITY_TAX_CREDIT_PER_DAY,
    CONF_GAS_FIXED_SUPPLY_PER_DAY,
    CONF_GAS_GRID_PER_DAY,
    CONF_GAS_MARKET_ENTITY,
    CONF_GAS_SUPPLIER,
    CONF_GAS_TAX,
    CONF_HOME_POWER_ENTITY,
    CONF_HOME_POWER_POSITIVE_DIRECTION,
    CONF_SOLAR_ACTUAL_NORTH_DC_ENTITY,
    CONF_SOLAR_ACTUAL_SOUTH_DC_ENTITY,
    CONF_SOLAR_ACTUAL_TOTAL_ENTITY,
    CONF_SOLAR_LATITUDE,
    CONF_SOLAR_LONGITUDE,
    CONF_SOLAR_NORTH_AC_KW,
    CONF_SOLAR_NORTH_AZIMUTH,
    CONF_SOLAR_NORTH_DC_KWP,
    CONF_SOLAR_NORTH_FACTOR,
    CONF_SOLAR_NORTH_TILT,
    CONF_SOLAR_SOUTH_AC_KW,
    CONF_SOLAR_SOUTH_AZIMUTH,
    CONF_SOLAR_SOUTH_DC_KWP,
    CONF_SOLAR_SOUTH_FACTOR,
    CONF_SOLAR_SOUTH_TILT,
    CONF_TARIFF_PROFILE_ID,
    CONF_TARIFF_SUPPLIER,
    CONF_TARIFF_VALID_FROM,
    CONF_VAT_PERCENT,
    DEFAULT_GAS_MARKET_ENTITY,
    DEFAULT_HOME_POWER_ENTITY,
    DEFAULT_SOLAR_ACTUAL_NORTH_DC_ENTITY,
    DEFAULT_SOLAR_ACTUAL_SOUTH_DC_ENTITY,
    DEFAULT_SOLAR_ACTUAL_TOTAL_ENTITY,
    DOMAIN,
    HOME_POWER_POSITIVE_CONSUMPTION,
    HOME_POWER_POSITIVE_DIRECTION_OPTIONS,
    NAME,
)


class DummyOSDataConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle Dummy OS Data config flow."""

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
                    data={
                        CONF_HOME_POWER_ENTITY: entity_id,
                        CONF_HOME_POWER_POSITIVE_DIRECTION: user_input[
                            CONF_HOME_POWER_POSITIVE_DIRECTION
                        ],
                    },
                )

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_HOME_POWER_ENTITY,
                    default=DEFAULT_HOME_POWER_ENTITY,
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor")
                ),
                vol.Required(
                    CONF_HOME_POWER_POSITIVE_DIRECTION,
                    default=HOME_POWER_POSITIVE_CONSUMPTION,
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=HOME_POWER_POSITIVE_DIRECTION_OPTIONS,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
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

    def _current(self, key: str, default: Any) -> Any:
        return self.config_entry.options.get(key, self.config_entry.data.get(key, default))

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Manage source and tariff options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        schema = vol.Schema(
            {
                vol.Required(CONF_HOME_POWER_ENTITY, default=self._current(CONF_HOME_POWER_ENTITY, DEFAULT_HOME_POWER_ENTITY)): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor")
                ),
                vol.Required(
                    CONF_HOME_POWER_POSITIVE_DIRECTION,
                    default=self._current(
                        CONF_HOME_POWER_POSITIVE_DIRECTION,
                        HOME_POWER_POSITIVE_CONSUMPTION,
                    ),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=HOME_POWER_POSITIVE_DIRECTION_OPTIONS,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Required(CONF_TARIFF_PROFILE_ID, default=self._current(CONF_TARIFF_PROFILE_ID, "current")): str,
                vol.Required(CONF_TARIFF_SUPPLIER, default=self._current(CONF_TARIFF_SUPPLIER, "ANWB Energie")): str,
                vol.Optional(CONF_TARIFF_VALID_FROM, default=self._current(CONF_TARIFF_VALID_FROM, "2026-01-01")): str,
                vol.Required(CONF_VAT_PERCENT, default=self._current(CONF_VAT_PERCENT, 21.0)): vol.Coerce(float),
                vol.Required(CONF_ELECTRICITY_IMPORT_SUPPLIER, default=self._current(CONF_ELECTRICITY_IMPORT_SUPPLIER, 0.0)): vol.Coerce(float),
                vol.Required(CONF_ELECTRICITY_IMPORT_TAX, default=self._current(CONF_ELECTRICITY_IMPORT_TAX, 0.0)): vol.Coerce(float),
                vol.Required(CONF_ELECTRICITY_EXPORT_SUPPLIER, default=self._current(CONF_ELECTRICITY_EXPORT_SUPPLIER, 0.0)): vol.Coerce(float),
                vol.Required(CONF_ELECTRICITY_EXPORT_TAX, default=self._current(CONF_ELECTRICITY_EXPORT_TAX, 0.0)): vol.Coerce(float),
                vol.Required(CONF_ELECTRICITY_FIXED_SUPPLY_PER_DAY, default=self._current(CONF_ELECTRICITY_FIXED_SUPPLY_PER_DAY, 0.0)): vol.Coerce(float),
                vol.Required(CONF_ELECTRICITY_GRID_PER_DAY, default=self._current(CONF_ELECTRICITY_GRID_PER_DAY, 0.0)): vol.Coerce(float),
                vol.Required(CONF_ELECTRICITY_TAX_CREDIT_PER_DAY, default=self._current(CONF_ELECTRICITY_TAX_CREDIT_PER_DAY, 0.0)): vol.Coerce(float),
                vol.Required(CONF_GAS_MARKET_ENTITY, default=self._current(CONF_GAS_MARKET_ENTITY, DEFAULT_GAS_MARKET_ENTITY)): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor")
                ),
                vol.Required(CONF_GAS_SUPPLIER, default=self._current(CONF_GAS_SUPPLIER, 0.0)): vol.Coerce(float),
                vol.Required(CONF_GAS_TAX, default=self._current(CONF_GAS_TAX, 0.0)): vol.Coerce(float),
                vol.Required(CONF_GAS_FIXED_SUPPLY_PER_DAY, default=self._current(CONF_GAS_FIXED_SUPPLY_PER_DAY, 0.0)): vol.Coerce(float),
                vol.Required(CONF_GAS_GRID_PER_DAY, default=self._current(CONF_GAS_GRID_PER_DAY, 0.0)): vol.Coerce(float),
                vol.Required(CONF_SOLAR_ACTUAL_TOTAL_ENTITY, default=self._current(CONF_SOLAR_ACTUAL_TOTAL_ENTITY, DEFAULT_SOLAR_ACTUAL_TOTAL_ENTITY)): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor")
                ),
                vol.Required(CONF_SOLAR_ACTUAL_NORTH_DC_ENTITY, default=self._current(CONF_SOLAR_ACTUAL_NORTH_DC_ENTITY, DEFAULT_SOLAR_ACTUAL_NORTH_DC_ENTITY)): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor")
                ),
                vol.Required(CONF_SOLAR_ACTUAL_SOUTH_DC_ENTITY, default=self._current(CONF_SOLAR_ACTUAL_SOUTH_DC_ENTITY, DEFAULT_SOLAR_ACTUAL_SOUTH_DC_ENTITY)): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor")
                ),
                vol.Required(CONF_SOLAR_LATITUDE, default=self._current(CONF_SOLAR_LATITUDE, 51.828981)): vol.All(vol.Coerce(float), vol.Range(min=-90, max=90)),
                vol.Required(CONF_SOLAR_LONGITUDE, default=self._current(CONF_SOLAR_LONGITUDE, 4.839871)): vol.All(vol.Coerce(float), vol.Range(min=-180, max=180)),
                vol.Required(CONF_SOLAR_NORTH_DC_KWP, default=self._current(CONF_SOLAR_NORTH_DC_KWP, 2.96)): vol.All(vol.Coerce(float), vol.Range(min=0)),
                vol.Required(CONF_SOLAR_NORTH_AC_KW, default=self._current(CONF_SOLAR_NORTH_AC_KW, 2.45)): vol.All(vol.Coerce(float), vol.Range(min=0)),
                vol.Required(CONF_SOLAR_NORTH_TILT, default=self._current(CONF_SOLAR_NORTH_TILT, 37.0)): vol.All(vol.Coerce(float), vol.Range(min=0, max=90)),
                vol.Required(CONF_SOLAR_NORTH_AZIMUTH, default=self._current(CONF_SOLAR_NORTH_AZIMUTH, 180.0)): vol.All(vol.Coerce(float), vol.Range(min=-180, max=180)),
                vol.Required(CONF_SOLAR_NORTH_FACTOR, default=self._current(CONF_SOLAR_NORTH_FACTOR, 0.9)): vol.All(vol.Coerce(float), vol.Range(min=0)),
                vol.Required(CONF_SOLAR_SOUTH_DC_KWP, default=self._current(CONF_SOLAR_SOUTH_DC_KWP, 1.48)): vol.All(vol.Coerce(float), vol.Range(min=0)),
                vol.Required(CONF_SOLAR_SOUTH_AC_KW, default=self._current(CONF_SOLAR_SOUTH_AC_KW, 1.23)): vol.All(vol.Coerce(float), vol.Range(min=0)),
                vol.Required(CONF_SOLAR_SOUTH_TILT, default=self._current(CONF_SOLAR_SOUTH_TILT, 37.0)): vol.All(vol.Coerce(float), vol.Range(min=0, max=90)),
                vol.Required(CONF_SOLAR_SOUTH_AZIMUTH, default=self._current(CONF_SOLAR_SOUTH_AZIMUTH, 0.0)): vol.All(vol.Coerce(float), vol.Range(min=-180, max=180)),
                vol.Required(CONF_SOLAR_SOUTH_FACTOR, default=self._current(CONF_SOLAR_SOUTH_FACTOR, 0.9)): vol.All(vol.Coerce(float), vol.Range(min=0)),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
