# GitHub Release

**Tag:** `0.1.0-alpha.12.13`  
**Release title:** Dummy OS Forecast 0.1.0-alpha.12.13 - Peak Learning Identity Fix

## Dummy OS Forecast 0.1.0-alpha.12.13

Gerichte identity-correctie op de in alpha.12.12 geïntroduceerde observer-only Energy Peak Learning-sensor. Er is geen wijziging aan forecast-, kalibratie-, classificatie- of plannerlogica.

### Correctie
- Canonieke Home Assistant-entiteit blijft `sensor.do_energy_peak_learning`.
- `unique_id` is gecorrigeerd van `dummy_os_data_energy_peak_learning` naar `do_energy_peak_learning` zodat Peak Learning exact dezelfde Energy-namespace volgt als alle overige Energy-sensoren.
- `suggested_object_id` blijft `do_energy_peak_learning`.
- Friendly name blijft `DO Energy Peak Learning`, conform de bestaande `DO Energy ...`-naamgeving.

### Migratie / cleanup
- Een bestaande alpha.12.12 registry-entry met unique-id `dummy_os_data_energy_peak_learning` wordt in-place gemigreerd naar `do_energy_peak_learning` en naar exact `sensor.do_energy_peak_learning`.
- Daardoor hoort geen `_2`-entiteit en geen dubbele Peak Learning-entiteit te ontstaan.
- De canonical entity-id wordt ook opgenomen in de stabiele entity-id migratielijst.

### Ongewijzigd
- Native architectuur blijft exact 15 minuten / 72 uur / 288 slots.
- Peak Learning blijft strikt observer-only.
- `forecast_influence_enabled=false` en `ready_for_model_influence=false` blijven ongewijzigd.
- Geen wijziging aan thresholds, event-samenvoeging, classificatie, protected window 17:00-18:00, confidence, recency, fallback of plannerfeed.

### Validatie
- Identity-contracttest controleert nu `do_energy_peak_learning` als unique-id.
- Release-consistencytest controleert Peak Learning binnen de uniforme `do_energy_*` Energy-namespace.
- Migratiecontracttest controleert de overgang van de foutieve alpha.12.12 unique-id naar de canonical identity.
- Volledige testsuite, Python compile en manifest JSON-validatie worden vóór publicatie uitgevoerd.
