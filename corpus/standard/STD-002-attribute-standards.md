---
id: STD-002
type: STANDARD
title: Attribute Units, Rounding and Identifiers
owner: Product Data
version: 3.4
effective: 2026-01-20
entities: [VAR-01A, VAR-01B, VAR-02A, VAR-02B, CH-MKT-A, CH-MKT-B]
tags: [attributes, units, rounding, gtin, dtype, wattage, normalisation]
---

# Attribute Units, Rounding and Identifiers

## Purpose

One canonical representation per attribute, held once at the variant and
projected into channels by the attribute map. Channels differ in what they call
a field; they do not differ in what the value is.

## Canonical attribute set

| path | dtype | unit | safety class | applies to |
|---|---|---|---|---|
| `specs.power_w` | int | W | no | home. |
| `specs.noise_db` | int | dB | no | home. |
| `specs.coverage_m2` | int | m² | no | home.air-treatment |
| `specs.filter_type` | str | - | no | home.air-treatment |
| `energy.class` | str | - | no | home. |
| `food.ingredients` | list[str] | - | no | food. |
| `food.allergens.contains` | list[str] | - | **yes** | food. |
| `food.allergens.may_contain` | list[str] | - | **yes** | food. |
| `food.net_weight_g` | int | g | no | food. |
| `food.fibre_g` | float | g | no | food. |
| `identifiers.gtin` | str | - | no | all |
| `claims` | list[str] | - | no | all |

`food.ingredients` is an **ordered** attribute. Its order is part of its value:
reordering it without changing its members is a change, and CH-MKT-B checks it
(RUL-B04, rejection MKB-2208).

## Units

Units are carried by the attribute definition, never by the value. Store `65`,
not `"65 W"` and not `"65W"`. A numeric attribute whose stored value is a string
containing its unit is a `channel_schema` defect and will be rejected by
CH-MKT-A as MKA-4102 on the `wattage` field, which is typed `int` by RUL-A03.

The unit is re-attached at rendering time by the channel adapter. `65 W` in
prose is copy, and copy is governed by STD-001, which requires it to declare
`derived_from` so that a later correction can find it.

## Wattage is an integer

`specs.power_w` is a whole number of watts. Suppliers routinely send rated power
as `65.0`, `65W`, `"approx 65"` or `0.065 kW`. All four normalise to `65`.

- Kilowatts multiply by 1000 and must divide exactly; `0.0655 kW` is not a
  wattage, it is a measurement, and is referred back to the supplier.
- A range - `60-70 W` - is not a value. Ranges are never averaged. Record no
  value and raise a supplier query under POL-003.
- A rating qualified as "typical", "peak" or "in boost mode" is a different
  quantity from rated power and must not be written to `specs.power_w`.

`specs.noise_db` follows the same rule in dB, and rounds to the nearest whole
decibel. A change of 6 dB - VAR-01B moving from 38 to 44 - crosses the
`ultra-quiet` threshold of 40 in STD-001 and is therefore never immaterial.

## Rounding

| attribute | precision | rule |
|---|---|---|
| `specs.power_w` | integer | round half up |
| `specs.noise_db` | integer | round half up |
| `specs.coverage_m2` | integer | round half up |
| `food.net_weight_g` | integer | round half up |
| `food.fibre_g` | one decimal | round half up |

Round once, at ingestion, against the supplier's own figure. Never round a
value that has already been rounded, and never round a value on its way into a
channel - a channel that wants fewer digits gets them from the renderer, so the
stored value stays the one the supplier certified.

Rounding is applied before any claim rule is evaluated. `food.fibre_g` of
`5.96` rounds to `6.0` and `high-fibre` holds; `5.94` rounds to `5.9` and it
does not.

## GTIN

`identifiers.gtin` is a **string** of 14 digits, zero-padded from GTIN-13 where
necessary, with leading zeros preserved. VAR-01A is `05012345600018` and
VAR-01B is `05012345600025`; VAR-02A is `05098765400011` and VAR-02B is
`05098765400028`.

- Never store a GTIN as a number. The leading zero is significant and integer
  storage silently deletes it.
- The final digit is the mod-10 check digit and is validated on ingest.
- A GTIN identifies a variant, never a product. Two variants of one product
  never share a GTIN, and a multipack - VAR-02B - carries its own.
- `gtin` is required on CH-MKT-A (RUL-A06) and as `globalTradeItemNumber` on
  CH-MKT-B (RUL-B05). A missing or malformed GTIN blocks both marketplaces and
  neither will accept the listing until it is corrected at source.

## Related

STD-001 (claims and copy), STD-003 (taxonomy and the attribute map),
CHN-002 (CH-MKT-A field names), CHN-003 (CH-MKT-B field names),
POL-002 (source precedence when two documents disagree on a value).
