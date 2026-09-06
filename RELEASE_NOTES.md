# GitHub Release

**Tag:** `0.1.0-alpha.12.18`  
**Release title:** Dummy OS Forecast 0.1.0-alpha.12.18 - Stable Foundation Reset

## Dummy OS Forecast 0.1.0-alpha.12.18

Deze pre-release is een stabiliteitsrelease. Er wordt geen nieuwe forecastfunctionaliteit toegevoegd. Het doel is de bestaande Dummy OS Forecast-runtime terug te brengen naar een beheersbaar fundament voordat verdere modelontwikkeling wordt hervat.

### Opgelost
- Snelle state-wijzigingen van `sensor.do_source_home_power` blijven het lopende kwartier exact integreren, maar starten niet langer een volledige `_notify()`-fan-out naar alle Energy Forecast- en analyse-entiteiten.
- Zware Energy Forecast-/observerberekeningen worden daardoor niet meer bij iedere live vermogenswijziging opnieuw door Home Assistant aangeroepen.
- Kwartiergrenzen en expliciete profielwijzigingen blijven geldige refreshmomenten voor de Energy Forecast-laag.

### Stabiliteitsgate
- Nieuwe regressietest borgt dat live Home Power-updates wel integreren maar niet de forecastlaag notificeren.
- Kwartiergrens blijft de normale Energy-refreshtrigger.
- Profielwijziging blijft een expliciete refreshtrigger.
- Compile, manifestcontrole en volledige regressietestset zijn verplicht vóór publicatie.

### Ongewijzigd
- Native architectuur blijft exact 15 minuten / 72 uur / 288 slots.
- Bestaande Energy Forecast-historie, snapshots en evaluaties worden niet verwijderd.
- Het productie-forecastmodel en de huidige 28-daagse recency-weging blijven functioneel ongewijzigd.
- Solar, Weather, Prices en Degree Days worden in deze gerichte stabiliteitsrelease niet functioneel herschreven.
- Dummy OS EMS en fysieke batterijbesturing worden niet gewijzigd.

### Bekend / nog geblokkeerd
- De integratiebrede Home Assistant `friendly_name`-/device-name-identiteitskwestie is nog niet als live opgelost bewezen en blijft afzonderlijk onderdeel van de stabilisatie.
- Peak Learning, Time Windows, Recency Weighting en uitgebreide kwaliteitsdiagnostiek blijven onderwerp van de Minimal Core-ontleding; deze release verwijdert geen historische data.

### Live validatie na installatie
- Bevestigen dat Dummy OS Forecast zonder fout start na upgrade vanaf alpha.12.17.
- Minimaal één volledig kwartier laten voltooien en controleren dat `sensor.do_energy_actual_quarter` normaal blijft vullen.
- Controleren dat de 72-uurs Energy Forecast 288 kwartierslots blijft leveren.
- Home Assistant-responsiviteit vergelijken met alpha.12.17, met bijzondere aandacht voor snelle Home Power-wijzigingen.
- Controleren dat bestaande historie en profielinstelling behouden zijn.
