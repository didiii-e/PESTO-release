# Effect of the sieve (Haiku -> Luna) on the verdict; 59 pairs, pool/reader/prompt identical

packets identical for 3 pairs (verdict cannot change there); different for 56

## Reader = Opus

| verdict level | changed (all pairs) | size of change | if packets differ |
|---|---|---|---|
| literature mean call | 7/59 = 11.9% (95% CI 6-23%) | 7 one step, 0 two+ steps | 12.5% of the 56 pairs with different packets |
| literature argmax | 4/59 = 6.8% (95% CI 3-16%) | 4 one step, 0 two+ steps | 7.1% of the 56 pairs with different packets |
| final verdict Max(lit, Open Targets) | 1/59 = 1.7% (95% CI 0-9%) | 1 one step, 0 two+ steps | 1.8% of the 56 pairs with different packets | 

direction with Luna's sieve: 3 pairs go UP, 4 go DOWN (mean call)

expected grade shift (Luna - Haiku packet): mean -0.032, median |shift| 0.04, 90th pct |shift| 0.16, |shift| > 0.5 in 2 pairs

| pair | saved | Haiku packet (E) | Luna packet (E) | packet Jaccard | final Max |
|---|---|---|---|---|---|
| PKD1 / Total cholesterol | Novel | Hypothesized (1.86) | Novel (1.26) | 0.29 | Hypothesized -> Hypothesized |
| CSNK1E / Autism Spectrum Disorder | Hypothesized* | Hypothesized (2.04) | Novel (1.45) | 0.38 | Hypothesized -> Hypothesized |
| TRAF7 / Autism Spectrum Disorder | Hypothesized* | Existing (2.71) | Hypothesized (2.23) | 0.03 | Existing -> Hypothesized |
| CETP / low density lipoprotein | Established | Existing (3.44) | Established (3.84) | 0.33 | Established -> Established |
| LTBP1 / Height | Established | Existing (3.40) | Established (3.50) | 0.25 | Established -> Established |
| MEF2C / Autism Spectrum Disorder | Existing* | Existing (3.45) | Established (3.55) | 0.38 | Established -> Established |
| EYA4 / dilated cardiomyopathy 1J | Existing* | Established (3.54) | Existing (3.49) | 0.74 | Established -> Established | 

by saved category / stratum (literature mean call changed):

| stratum | n | changed |
|---|---|---|
| Novel | 14 | 1 |
| Hypothesized | 15 | 2 |
| Existing | 15 | 2 |
| Established | 15 | 2 |
| borderline | 22 | 4 |
| non-borderline | 37 | 3 | 

## Reader = Sol

| verdict level | changed (all pairs) | size of change | if packets differ |
|---|---|---|---|
| literature mean call | 9/59 = 15.3% (95% CI 8-27%) | 6 one step, 3 two+ steps | 16.1% of the 56 pairs with different packets |
| literature argmax | 9/59 = 15.3% (95% CI 8-27%) | 6 one step, 3 two+ steps | 16.1% of the 56 pairs with different packets |
| final verdict Max(lit, Open Targets) | 4/59 = 6.8% (95% CI 3-16%) | 3 one step, 1 two+ steps | 7.1% of the 56 pairs with different packets | 

direction with Luna's sieve: 1 pairs go UP, 8 go DOWN (mean call)

expected grade shift (Luna - Haiku packet): mean -0.109, median |shift| 0.01, 90th pct |shift| 0.74, |shift| > 0.5 in 9 pairs

| pair | saved | Haiku packet (E) | Luna packet (E) | packet Jaccard | final Max |
|---|---|---|---|---|---|
| CSNK1E / Autism Spectrum Disorder | Hypothesized* | Existing (2.84) | Novel (1.05) | 0.38 | Existing -> Hypothesized |
| TRAF7 / Autism Spectrum Disorder | Hypothesized* | Existing (2.95) | Novel (1.25) | 0.03 | Existing -> Hypothesized |
| DDX41 / red | Existing* | Novel (1.20) | Existing (2.65) | 0.48 | Novel -> Existing |
| MEF2C / Autism Spectrum Disorder | Existing* | Established (3.90) | Existing (2.98) | 0.38 | Established -> Established |
| PKD1 / Total cholesterol | Novel | Hypothesized (1.92) | Novel (1.00) | 0.29 | Hypothesized -> Hypothesized |
| APOB / Hemoglobin [Mass/volume] in  | Hypothesized | Hypothesized (2.00) | Novel (1.12) | 0.29 | Established -> Established |
| ERP44 / schizophrenia | Hypothesized* | Hypothesized (1.85) | Novel (1.15) | 0.90 | Hypothesized -> Novel |
| LTBP1 / Height | Established | Established (3.85) | Existing (3.15) | 0.25 | Established -> Established |
| CCT7 / complex neurodevelopmental d | Novel* | Hypothesized (1.75) | Novel (1.15) | 0.72 | Hypothesized -> Hypothesized | 

by saved category / stratum (literature mean call changed):

| stratum | n | changed |
|---|---|---|
| Novel | 14 | 2 |
| Hypothesized | 15 | 4 |
| Existing | 15 | 2 |
| Established | 15 | 1 |
| borderline | 22 | 6 |
| non-borderline | 37 | 3 | 

## Does the size of the packet change predict a verdict change? (Opus reading)

| packet Jaccard | n | Opus changed | Sol changed |
|---|---|---|---|
| 0.00-0.34 | 17 | 4 | 4 |
| 0.34-0.67 | 27 | 2 | 3 |
| 0.67-1.00 | 15 | 1 | 2 | 

## Baselines (how much does the verdict move with no change of model at all?)

- Same packet, same reader, fresh draw (12 stability pairs): Opus 0/36 draw-pairs change, Sol 0/36 -> reader sampling noise is ~0, so a change after a sieve swap is caused by the packet, not by luck.
- Whole-pipeline rerun, Haiku sieve + Opus reader (fresh retrieval + fresh sieve draw): verdict changes in 2/36 run pairs (6%)
- Whole-pipeline rerun, Luna sieve + Sol reader (fresh retrieval + fresh sieve draw): verdict changes in 8/36 run pairs (22%)
