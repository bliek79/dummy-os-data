"""Regression checks for internal gas tariff ownership."""

from pathlib import Path
import unittest

ROOT = Path(__file__).parents[1]
PRICES = ROOT / "custom_components/dummy_os_data/prices.py"
CONFIG_FLOW = ROOT / "custom_components/dummy_os_data/config_flow.py"


class InternalGasTariffTests(unittest.TestCase):
    def test_external_gas_markup_helper_is_not_in_prices_chain(self) -> None:
        source = PRICES.read_text()
        self.assertNotIn("GAS_VARIABLE_ADDON_ENTITY", source)
        self.assertNotIn("input_number.gas_markup_per_m3", source)
        self.assertIn('"gas_variable_addon_source": "dummy_os_data_options"', source)

    def test_gas_variable_addon_uses_internal_options(self) -> None:
        source = PRICES.read_text()
        self.assertIn("return self._num(CONF_GAS_SUPPLIER) + self._num(CONF_GAS_TAX)", source)
        self.assertIn('"tariff_edit_surface": "Dummy OS Data Options"', source)

    def test_gas_tariffs_remain_editable_in_options_flow(self) -> None:
        source = CONFIG_FLOW.read_text()
        for key in (
            "CONF_GAS_SUPPLIER",
            "CONF_GAS_TAX",
            "CONF_GAS_FIXED_SUPPLY_PER_DAY",
            "CONF_GAS_GRID_PER_DAY",
        ):
            self.assertIn(f"vol.Required({key}", source)


if __name__ == "__main__":
    unittest.main()
