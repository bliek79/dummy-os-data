# Retired Alpha35 planner tests

These tests are intentionally excluded from the EMS alpha76-copy acceptance run.
They encode planner behaviour that was introduced during the rejected Alpha35
redesign and therefore conflict with the approved recovery specification:

> Dummy OS Energy copies the functional behaviour of Dummy OS EMS
> `0.0.1-alpha.76`; only the forecast/input layer is replaced by the new
> Dummy OS Data 15-minute / 72-hour / 288-slot forecast contract.

This is **not** a mechanism to hide parity failures. The alpha76 golden outputs
are not changed. The replacement parity tests execute the original vendored
alpha76 modules and compare the adapter/runtime against those same modules.

Retired files:

- `test_alpha28_grid_support_contract.py` — Alpha35 grid-support planner policy.
- `test_alpha31_resilient_planner.py` — Alpha35 degraded-prefix/planner policy.
- `test_alpha32_native_planner_parity.py` — redesigned native-quarter EMS policy.
- `test_alpha34_sequential_safety.py` — replay/commitment/backward-precharge safety redesign.
- `test_alpha35_shared_time_contract.py` — mixes valid time-contract checks with rejected native-planner policy; its clock-boundary coverage is superseded by `test_ems_alpha76_quarter_offset_parity.py` while the time/input layer remains covered by the unaffected forecast/time tests.
- `test_do_plan_72h.py` — tests the rejected Alpha35 Plan72 implementation.
- `test_do_plan_72h_sensor_contract.py` — textual contract for the rejected Alpha35 Plan72 module.
- `test_do_plan_energy_need.py` — tests post-alpha76 Energy Need semantics rather than the copied EMS semantics.
- `test_do_plan_preview.py` — tests the redesigned preview/economic contract rather than alpha76.
- `test_do_plan_preview_sensor_contract.py` — textual contract for that redesigned preview.
- `test_do_plan_reserve_soc.py` — tests a separate reserve authority that no longer exists; reserve is now a view of alpha76 Energy Need/Plan72.
- `test_pre_step5_evaluation_metrics_main_thread_fix.py` — asserts textual invariants of the rejected preview module.
- `test_pre_step5_final_two_main_thread_fix.py` — same rejected preview contract.
- `test_pre_step5_remaining_main_thread_fix.py` — same rejected preview contract.
- `test_pre_step5_time_windows_main_thread_fix.py` — same rejected preview contract.

Replacement acceptance coverage:

- `test_ems_alpha76_core_parity.py`: F01-F25 core Energy Need / Preview / Plan72 parity.
- `test_ems_alpha76_quarter_offset_parity.py`: :00 / :15 / :30 / :45 transport-boundary parity without changing alpha76 decisions.
- `test_ems_alpha76_full_chain_parity.py`: Action Bridge, Plan Store/Scheduler gates, prestart/safety/controller and Execution Controller ordering/fail-safe behaviour.

All other repository tests remain active. Any failure outside this explicit retired
set continues to block release/publication.
