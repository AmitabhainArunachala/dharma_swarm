# Operator Scoreboard

Date: 2026-03-13
Purpose: measure whether the money-side operating loop is becoming real

## North star

`Close and deliver the first paid Campaign X-Ray without hiding the brittle parts.`

## Leading indicators

| Metric | Target | Current truth | Status |
|---|---:|---:|---|
| Fresh internal X-Ray packet | `1` | `1` | green |
| Internal proving-ground runs beyond DGC | `2` | `0` | red |
| Demo runtime | `<15 min` | ready | green |
| External warm accounts verified | `25` | `0` | red |
| Tailored outreach sent | `10-15` | `0` | red |
| Discovery calls booked | `5` | `0` | red |

## Delivery indicators

| Metric | Target | Current truth | Status |
|---|---:|---:|---|
| `corpus -> first brief` | `<24h` | same-turn local run | green |
| `brief -> buyer packet` | `<48h` | same-turn local run | green |
| `brief -> verified artifact` | `<72h` | not reliable yet | yellow/red |
| explicit proof boundary in every packet | `100%` | yes for this packet | green |
| human re-explaining overhead | week over week down | not measured yet | red |

## Revenue indicators

| Metric | Day-30 target | Current truth | Status |
|---|---:|---:|---|
| paid X-Rays closed | `1-2` | `0` | red |
| sprint proposals issued | `1` | `0` | red |
| active design-partner opportunities | `2` | `0` | red |
| collected revenue | `>0` | `0` | red |

## Weekly operating rhythm

### Monday

- choose proving-ground corpus or client corpus
- run X-Ray
- refresh packet

### Tuesday

- tighten demo and proof language
- score targets

### Wednesday

- send outreach
- book calls

### Thursday

- run discovery
- update objection map

### Friday

- decide go/no-go on sprint proposals
- update the campaign ledger and scoreboard

## Stop conditions

Stop and fix the system if:

- warm-account count is still `0` after the relationship graph should have been imported
- the demo requires hidden manual rescue to look clean
- a packet is delivered without explicit proof boundaries
- the first diagnostic takes more than `6` operator hours repeatedly
- the sprint upsell depends on claims the proof packet does not support

## Immediate next milestones

1. By day `3`: run X-Ray on one adjacent internal corpus.
2. By day `5`: import the first real warm graph.
3. By day `7`: have `10` outreach-ready names with relationship evidence.
4. By day `14`: send `10-15` tailored messages.
5. By day `30`: close `1` paid diagnostic.
