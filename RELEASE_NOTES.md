# GitHub Release

**Tag:** `0.1.0-alpha.12.7`

**Release title:** `Dummy OS Forecast 0.1.0-alpha.12.7 - Energy Persistent Store Foundation`

## Dummy OS Forecast 0.1.0-alpha.12.7

Gerichte uitbreiding voor Energy Forecast Stap 2: versieerbare persistente learning- en evaluatieopslag als basis voor restart- en restore-bestendigheid.

### Toegevoegd / verbeterd
- De bestaande Energy Store krijgt een expliciete `energy_store_schema_version` naast de Home Assistant Store-versie.
- Nieuwe Energy-evaluatierecords krijgen `evaluation_schema_version` zodat toekomstige schema-evolutie gecontroleerd kan plaatsvinden.
- Bestaande legacy Store-payloads zonder expliciete schema-aanduiding worden veilig als schema 0 ingelezen en in geheugen naar de huidige structuur genormaliseerd zonder historie te verliezen.
- Onbekende toekomstige Energy Store-schema's worden geweigerd in plaats van stil teruggeschreven door oudere code.
- De coordinator gebruikt de genormaliseerde payload bij het laden en schrijft de huidige Energy Store-schema-aanduiding bij iedere persistente save.
- Gerichte regressietests bewaken legacy-upgrade, behoud van bestaande data, veilige defaults, toekomstig-schema-blokkade en coordinator-integratie.

### Ongewijzigd
- Native architectuur blijft 15 minuten / 72 uur / 288 slots.
- `STORAGE_VERSION = 1` en de bestaande Store-key blijven behouden; er is geen gedwongen Home Assistant Store-migratie nodig voor deze additieve stap.
- Canonieke Energy-entity-ID's blijven ongewijzigd; deze release voegt geen nieuwe Home Assistant-entiteiten toe.
- Bestaande records, forecast snapshots en evaluaties blijven behouden en bruikbaar.
- Solar, Weather, Prices, Degree Days en fysieke EMS-sturing zijn functioneel ongewijzigd.

### Live validatie na installatie
1. Controleer dat de bestaande `sensor.do_energy_*` entiteiten normaal blijven publiceren en de timeline 288 punten houdt.
2. Controleer dat history days, valid quarters en evaluation samples niet resetten na installatie/herstart.
3. Laat minimaal één volledig kwartier verlopen en bevestig dat nieuwe records en evaluaties blijven oplopen.
4. Controleer dat de persistente Energy Store `energy_store_schema_version: 1` bevat en nieuwe evaluaties `evaluation_schema_version: 1` krijgen.
5. Maak daarna een Home Assistant-back-up en herstel die gecontroleerd; bevestig dat dezelfde Energy-historie/evaluaties terugkomen en daarna verder oplopen. Pas na deze restore-proef is Stap 2 volledig live gevalideerd.
