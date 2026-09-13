from pathlib import Path


ROOT = Path(__file__).parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text()


def test_cloud_sources_start_after_platform_registration() -> None:
    source = _read("custom_components/dummy_os_data/__init__.py")
    setup = source.split("async def async_setup_entry", 1)[1]
    assert setup.index("async_forward_entry_setups") < setup.index("_async_setup_cloud_sources")
    assert "coordinator.weather.async_setup = _async_noop" in setup
    assert "coordinator.weather.async_setup = weather_setup" in setup


def test_weather_prices_and_solar_initialize_concurrently() -> None:
    source = _read("custom_components/dummy_os_data/__init__.py")
    helper = source.split("async def _async_setup_cloud_sources", 1)[1].split("def _is_obsolete_home_input_state", 1)[0]
    assert "await asyncio.gather(" in helper
    assert "weather_setup()" in helper
    assert "coordinator.prices.async_setup()" in helper
    assert "coordinator.solar.async_setup()" in helper
    assert "return_exceptions=True" in helper


def test_degree_days_starts_after_cloud_source_wave() -> None:
    source = _read("custom_components/dummy_os_data/__init__.py")
    helper = source.split("async def _async_setup_cloud_sources", 1)[1].split("def _is_obsolete_home_input_state", 1)[0]
    assert helper.index("await asyncio.gather(") < helper.index("await coordinator.degree_days.async_setup()")


def test_background_startup_task_is_cancelled_on_unload() -> None:
    source = _read("custom_components/dummy_os_data/__init__.py")
    assert "coordinator._source_setup_task = source_setup_task" in source
    assert "source_setup_task.cancel()" in source
    assert "except asyncio.CancelledError" in source


def test_alpha30_version_is_consistent() -> None:
    const = _read("custom_components/dummy_os_data/const.py")
    manifest = _read("custom_components/dummy_os_data/manifest.json")
    assert 'VERSION = "0.2.0-alpha.30"' in const
    assert '"version": "0.2.0-alpha.30"' in manifest
