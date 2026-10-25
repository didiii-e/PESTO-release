# Frozen-input comparisons: 59 pairs with a candidate pool

## A. Sieve on the identical pool (same articles, synonyms, batches, prompt)

3693 articles; articles left unbanded by Haiku/Luna (defaulted to 2, as production does): {'': 3693}

| Haiku \ Luna (band) | 1 none | 2 nonhuman | 3 weak | 4 strong | n |
|---|---|---|---|---|---|
| 1 none | 910 | 201 | 352 | 0 | 1463 |
| 2 nonhuman | 100 | 784 | 118 | 11 | 1013 |
| 3 weak | 86 | 27 | 547 | 26 | 686 |
| 4 strong | 8 | 19 | 149 | 355 | 531 | 

| criterion | Haiku rate | Luna rate | agreement | kappa | Haiku-only | Luna-only |
|---|---|---|---|---|---|---|
| pass (band >= 2) | 60.4% | 70.1% | 79.8% | 0.56 | 194 | 553 |
| human (band >= 3) | 33.0% | 42.2% | 83.2% | 0.64 | 140 | 481 |
| strong (band 4) | 14.4% | 10.6% | 94.2% | 0.74 | 176 | 37 | 

exact band agreement 70.3%; within one band 87.1%; weighted kappa 0.68

packet handed to the reader: Jaccard Haiku-vs-Luna selection mean 0.51, median 0.48; identical in 3/59; mean size 15.9 vs 16.9

### Sieve draw-to-draw stability (same pool; 12 stability pairs; Haiku draw 1 = the live run)

| sieve | draw pairs | exact band agreement | pass/reject agreement | mean kappa(pass) |
|---|---|---|---|---|
| Haiku | 36 | 90.5% | 92.3% | 0.74 |
| Luna | 36 | 86.1% | 91.3% | 0.69 | 

## B. Readers on identical packets

| comparison (A vs B) | n | exact (mean call) | within 1 | quad. kappa | Spearman E | Pearson E | mean E B-A |
|---|---|---|---|---|---|---|---|
| READER only: Opus vs Sol on the Haiku packet | 59 | 49/59 (83%) | 58/59 (98%) | 0.92 | 0.973 | 0.957 | +0.02 |
| READER only: Opus vs Sol on the Luna packet | 59 | 51/59 (86%) | 59/59 (100%) | 0.95 | 0.973 | 0.974 | -0.06 |
| SIEVE only (Opus reading): Haiku packet vs Luna packet | 59 | 52/59 (88%) | 59/59 (100%) | 0.96 | 0.987 | 0.990 | -0.03 |
| SIEVE only (Sol reading): Haiku packet vs Luna packet | 59 | 50/59 (85%) | 56/59 (95%) | 0.89 | 0.957 | 0.927 | -0.11 |
| READER+SIEVE: Opus on Haiku packet vs Sol on Luna packet (same pool) | 59 | 51/59 (86%) | 58/59 (98%) | 0.93 | 0.956 | 0.956 | -0.09 |
| FULL PIPELINE: Claude e2e vs OpenAI e2e (own retrieval) | 59 | 48/59 (81%) | 57/59 (97%) | 0.89 | 0.946 | 0.933 | -0.12 | 

(For the 3 pairs where both sieves choose the same packet the Luna-packet answer is the Haiku-packet answer.)

### Frozen readers' sharpness (same packets)

| reader / packet | n | mean entropy | mean top-p | exactly one-hot |
|---|---|---|---|---|
| Opus, Haiku packet (live Claude read) | 59 | 1.07 | 0.70 | 0/59 (0%) |
| Sol, Haiku packet | 59 | 0.26 | 0.94 | 17/59 (29%) |
| Sol, Luna packet | 59 | 0.25 | 0.95 | 19/59 (32%) |
| Opus, Luna packet | 59 | 1.03 | 0.71 | 0/59 (0%) | 

### Confusion on the Haiku packet (rows Opus, cols Sol)

| Opus \ Sol | Novel | Hypothesized | Existing | Established | n |
|---|---|---|---|---|---|
| Novel | 13 | 3 | 0 | 0 | 16 |
| Hypothesized | 1 | 8 | 2 | 0 | 11 |
| Existing | 1 | 0 | 14 | 3 | 18 |
| Established | 0 | 0 | 0 | 14 | 14 | 

### Frozen reader disagreements on the Haiku packet (mean call differs)

| pair | saved | Opus (E) | Sol (E) | packet n |
|---|---|---|---|---|
| DDX41 / red | Exist* | Existing (2.68) | Novel (1.20) | 20 |
| CSNK1E / Autism Spectrum Disorder | Hypot* | Hypothesized (2.04) | Existing (2.84) | 20 |
| SLTM / Autism Spectrum Disorder | Novel | Novel (1.28) | Hypothesized (1.90) | 15 |
| ERP44 / schizophrenia | Hypot* | Novel (1.29) | Hypothesized (1.85) | 20 |
| CETP / low density lipoprotein | Estab | Existing (3.44) | Established (3.90) | 20 |
| MEF2C / Autism Spectrum Disorder | Exist* | Existing (3.45) | Established (3.90) | 20 |
| LTBP1 / Height | Estab | Existing (3.40) | Established (3.85) | 20 |
| RANBP2 / Autism Spectrum Disorder | Hypot* | Hypothesized (1.69) | Novel (1.27) | 20 |
| BRD4 / Autism Spectrum Disorder | Hypot | Hypothesized (2.34) | Existing (2.65) | 20 |
| CCT7 / complex neurodevelopmental dis | Novel* | Novel (1.46) | Hypothesized (1.75) | 13 | 

### Reader draw-to-draw stability (same packet; 12 stability pairs)

| reader | draw pairs | same mean call | mean sd of E[grade] |
|---|---|---|---|
| Opus | 36 | 36/36 (100%) | 0.04 |
| Sol | 36 | 36/36 (100%) | 0.01 | 

frozen-stage spend: $10.06 (sieve $1.29, readers $8.77)
