"""Integration-wide identity baseline gate for public Dummy OS Forecast entities."""

from pathlib import Path

ROOT = Path(__file__).parents[1]


def _text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_public_entity_bases_use_full_name_semantics() -> None:
    """Public entities keep their canonical DO name without device-name prefixing."""
    for path in (
        "custom_components/dummy_os_data/home_input_sensor.py",
        "custom_components/dummy_os_data/sensor.py",
        "custom_components/dummy_os_data/solar_sensor.py",
        "custom_components/dummy_os_data/degree_days_sensor.py",
        "custom_components/dummy_os_data/select.py",
    ):
        assert "_attr_has_entity_name = False" in _text(path), path


def test_core_device_name_remains_integration_name() -> None:
    """The central device can remain Dummy OS Forecast while entity names stay full names."""
    const = _text("custom_components/dummy_os_data/const.py")
    assert 'NAME = "Dummy OS Forecast"' in const
