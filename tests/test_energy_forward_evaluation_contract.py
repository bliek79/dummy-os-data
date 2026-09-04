from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_energy_forward_evaluation_persists_context_and_rejects_late_snapshot():
    coordinator = (ROOT / "custom_components/dummy_os_data/coordinator.py").read_text()

    for field in (
        '"forecast_captured_at": captured_at.isoformat()',
        '"actual_coverage": result.coverage',
        '"sample_count": snapshot.get("sample_count")',
        '"source": snapshot.get("source")',
        '"confidence": snapshot.get("confidence")',
        '"model": snapshot.get("model")',
        '"model_version": snapshot.get("model_version")',
    ):
        assert field in coordinator

    assert 'captured_at = datetime.fromisoformat(snapshot["captured_at"])' in coordinator
    assert "if captured_at > dt_util.as_utc(result.start):" in coordinator
    assert 'snapshot.get("profile") != result.profile' in coordinator
    assert "if not result.valid or result.energy_kwh is None:" in coordinator


def test_energy_scheduler_latency_is_normalized_to_exact_quarter_boundary():
    coordinator = (ROOT / "custom_components/dummy_os_data/coordinator.py").read_text()
    assert "def _quarter_boundary_utc(now: datetime) -> datetime:" in coordinator
    assert "return now_utc.replace(minute=minute, second=0, microsecond=0)" in coordinator
    assert "boundary_utc = self._quarter_boundary_utc(now)" in coordinator
    assert "self._integrate_until(boundary_utc)" in coordinator
    assert "await self._finalize_quarter(boundary_utc)" in coordinator
    assert "self._start_new_quarter(boundary_utc)" in coordinator
    assert "captured_at=boundary_utc" in coordinator


def test_energy_native_architecture_unchanged():
    const = (ROOT / "custom_components/dummy_os_data/const.py").read_text()
    assert "QUARTER_MINUTES = 15" in const
    assert "FORECAST_HORIZON_HOURS = 72" in const
    assert "FORECAST_SLOTS = FORECAST_HORIZON_HOURS * 60 // QUARTER_MINUTES" in const
    assert "MIN_VALID_COVERAGE = 0.90" in const
