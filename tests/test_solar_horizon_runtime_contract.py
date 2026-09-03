from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

def test_runtime_boundary_and_ids():
    solar = (ROOT / "custom_components/dummy_os_data/solar.py").read_text()
    init = (ROOT / "custom_components/dummy_os_data/__init__.py").read_text()
    mig = (ROOT / "custom_components/dummy_os_data/entity_migrations.py").read_text()
    assert "boundary_utc = floor_slot_start(now_utc, QUARTER_MINUTES)" in solar
    assert "self._capture_horizon_snapshots(boundary_utc)" in solar
    for h in (1, 6, 24, 48, 72):
        u = f"do_solar_evaluation_horizon_{h}h"
        assert f'("sensor", "{u}", "sensor.{u}")' in init
        assert f'"{u}": "sensor.dummy_os_solar_evaluation_horizon_{h}h"' in mig
