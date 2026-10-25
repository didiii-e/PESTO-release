# End-to-end, r1: 60 of 60 pairs complete in both families

pairs with errors: [] 

## 1. Category agreement (Claude vs OpenAI)

| measure | exact | within 1 | kappa | quad. kappa |
|---|---|---|---|---|
| literature, mean call (headline) | 49/60 (82%) | 58/60 (97%) | 0.75 | 0.89 |
| literature, argmax | 47/60 (78%) | 58/60 (97%) | 0.71 | 0.89 |
| Open Targets verdict | 56/59 (95%) | 59/59 (100%) | 0.93 | 0.98 |
| final Max(lit mean, OT) | 53/60 (88%) | 59/60 (98%) | 0.84 | 0.93 | 

### Confusion, literature mean call (rows Claude, cols OpenAI)

| Claude \ OpenAI | Novel | Hypothesized | Existing | Established | n |
|---|---|---|---|---|---|
| Novel | 15 | 2 | 0 | 0 | 17 |
| Hypothesized | 3 | 7 | 1 | 0 | 11 |
| Existing | 2 | 1 | 14 | 1 | 18 |
| Established | 0 | 0 | 1 | 13 | 14 | 

### Confusion, final Max (rows Claude, cols OpenAI)

| Claude \ OpenAI | Novel | Hypothesized | Existing | Established | n |
|---|---|---|---|---|---|
| Novel | 10 | 1 | 0 | 0 | 11 |
| Hypothesized | 1 | 11 | 1 | 0 | 13 |
| Existing | 1 | 2 | 12 | 0 | 15 |
| Established | 0 | 0 | 1 | 20 | 21 | 

### Confusion, Open Targets verdict (rows Claude, cols OpenAI)

| Claude \ OpenAI | Novel | Hypothesized | Existing | Established | n |
|---|---|---|---|---|---|
| Novel | 14 | 0 | 0 | 0 | 14 |
| Hypothesized | 3 | 19 | 0 | 0 | 22 |
| Existing | 0 | 0 | 8 | 0 | 8 |
| Established | 0 | 0 | 0 | 15 | 15 | 

Direction of the literature mean-call disagreements: {'OpenAI higher': 4, 'OpenAI lower': 7} 

### Agreement by stratum (literature mean call)

| stratum | n | exact | within 1 | mean E[grade] OpenAI-Claude |
|---|---|---|---|---|
| borderline | 22 | 17/22 (77%) | 20/22 (91%) | -0.19 |
| disease pair | 46 | 39/46 (85%) | 45/46 (98%) | -0.08 |
| non-borderline | 38 | 32/38 (84%) | 38/38 (100%) | -0.08 |
| saved Established | 15 | 13/15 (87%) | 15/15 (100%) | +0.06 |
| saved Existing | 15 | 13/15 (87%) | 14/15 (93%) | -0.19 |
| saved Hypothesized | 15 | 10/15 (67%) | 14/15 (93%) | -0.22 |
| saved Novel | 15 | 13/15 (87%) | 15/15 (100%) | -0.11 |
| trait pair | 14 | 10/14 (71%) | 13/14 (93%) | -0.24 | 

## 2. Continuous E[grade] (sum(grade*p), grades 1..4)

Spearman 0.948 (p=1.9e-30), Pearson 0.935; mean diff OpenAI-Claude -0.116, mean |diff| 0.290, within 0.5 of each other 51/60, >1.0 apart 2

## 3. Probability sharpness

| family | mean entropy (bits) | median | mean top-p | median | exactly one-hot | top-p >= 0.9 |
|---|---|---|---|---|---|---|
| claude | 1.05 | 1.19 | 0.71 | 0.68 | 0/60 (0%) | 12/60 (20%) |
| openai | 0.23 | 0.14 | 0.95 | 0.98 | 22/60 (37%) | 53/60 (88%) | 

## 4. Router (identical phenotype string, two routers)

arm agreement 60/60 (100%)
- claude router vs the pair-table trait flag: 60/60 (100%)
- openai router vs the pair-table trait flag: 60/60 (100%)

## 5. Retrieval: is a disagreement the model or the retrieval?

candidate-pool Jaccard (PMIDs): mean 0.86, median 0.93; read-set Jaccard: mean 0.46, median 0.48; synonym-list Jaccard: mean 0.28
pool size Claude/OpenAI mean 62/59; synonyms per pair 9.1/4.7 (note: Claude expands with Opus, OpenAI with Luna, because --model-fast covers that step)

### Does the call depend on how much the read sets overlap? (literature mean call)

| stratum | n | exact | within 1 | mean |dE[grade]| |
|---|---|---|---|---|
| read-set Jaccard < 0.34 | 24 | 18/24 (75%) | 23/24 (96%) | 0.35 |
| 0.34 - 0.67 | 22 | 20/22 (91%) | 22/22 (100%) | 0.22 |
| >= 0.67 | 13 | 10/13 (77%) | 12/13 (92%) | 0.31 | 

Spearman(read-set Jaccard, |dE[grade]|) = -0.12 (p=0.36)

## 6. Sieve inside the live runs (own pools)

| sieve | articles | pass (>=2) | human (>=3) | strong (4) | mean read per pair |
|---|---|---|---|---|---|
| claude (Haiku) | 3693 | 2230/3693 (60%) | 1217/3693 (33%) | 531/3693 (14%) | 15.7 |
| openai (Luna) | 3554 | 2515/3554 (71%) | 1550/3554 (44%) | 366/3554 (10%) | 16.3 | 

on PMIDs that both retrieved (3248 article-pairs): pass/reject agreement 79.8%, kappa 0.56

## 7. Cost, latency, reliability (per pair, end to end)

| family | total | mean/pair | median | mean wall | median wall | p90 wall | calls | API attempts | retries | refusals | non-end_turn / errored calls | reasoning/output tokens |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| claude | $9.48 | $0.158 | $0.166 | 41s | 40s | 55s | 753 | 753 | 0 | 0 | 0 | 0/217802 |
| openai | $1.75 | $0.029 | $0.030 | 42s | 40s | 58s | 739 | 739 | 0 | 0 | 0 | 173177/281980 | 

cost ratio Claude/OpenAI (all recorded pairs) = 5.4x; mean wall ratio Claude/OpenAI = 0.98

### Where the cost and the time go (mean per pair)

| step | claude $ / s | openai $ / s |
|---|---|---|
| router | $0.0024 / 1.3s | $0.0004 / 1.2s |
| expand | $0.0081 / 4.1s | $0.0001 / 2.7s |
| sieve | $0.0282 / 2.9s | $0.0031 / 6.6s |
| read | $0.0543 / 8.3s | $0.0124 / 4.6s |
| open targets | $0.0351 / 18.4s | $0.0078 / 21.0s | 

## 8. Disagreement list (literature mean call differs, or final Max differs)

| pair | saved | Claude lit (E/Ex/H/N) | OpenAI lit | dE | pool J | read J | OT C/O | Max C/O |
|---|---|---|---|---|---|---|---|---|
| DDX41 / red | Exist* | Existing (12/55/22/11) | Novel (0/5/5/90) | -1.53 | 0.85 | 0.82 | Novel/Novel | Exist/Novel |
| TRAF7 / Autism Spectrum Disorder | Hypot* | Existing (8/62/23/7) | Novel (0/8/2/90) | -1.53 | 0.99 | 0.03 | Hypot/Hypot | Exist/Hypot |
| APOB / Hemoglobin [Mass/volume] in Blood | Hypot | Hypothesized (3/18/49/30) | Novel (0/0/3/97) | -0.91 | 0.54 | 0.00 | Estab/Estab | Estab/Estab |
| PKD1 / Total cholesterol | Novel | Hypothesized (2/10/60/28) | Novel (0/0/2/98) | -0.84 | 0.91 | 0.29 | Hypot/Hypot | Hypot/Hypot |
| CSNK1E / Autism Spectrum Disorder | Hypot* | Hypothesized (2/23/52/23) | Existing (0/80/19/1) | +0.75 | 1.00 | 0.48 | Hypot/Hypot | Hypot/Exist |
| GRIA2 / Autism Spectrum Disorder | Estab | Established (70/26/4/0) | Existing (0/98/2/0) | -0.68 | 0.64 | 0.33 | Hypot/Hypot | Estab/Exist |
| SLTM / Autism Spectrum Disorder | Novel | Novel (0/3/22/75) | Hypothesized (0/0/90/10) | +0.62 | 0.78 | 0.11 | Hypot/Novel | Hypot/Hypot |
| ERP44 / schizophrenia | Hypot* | Novel (0/2/25/73) | Hypothesized (0/0/90/10) | +0.61 | 1.00 | 0.90 | Novel/Novel | Novel/Hypot |
| CETP / low density lipoprotein | Estab | Existing (55/36/7/2) | Established (98/2/0/0) | +0.54 | 0.60 | 0.18 | Estab/Estab | Estab/Estab |
| RANBP2 / Autism Spectrum Disorder | Hypot* | Hypothesized (1/17/32/50) | Novel (0/10/10/80) | -0.39 | 0.95 | 0.54 | Hypot/Hypot | Hypot/Hypot |
| BCR / Autism Spectrum Disorder | Hypot | Novel (1/5/19/75) | Novel (0/0/0/100) | -0.32 | 0.76 | 0.04 | Hypot/Novel | Hypot/Novel |
| TMEM135 / neurodevelopmental disorder | Exist | Existing (3/58/34/5) | Hypothesized (0/30/69/1) | -0.30 | 1.00 | 1.00 | Hypot/Hypot | Exist/Hypot | 

(* = borderline pair)

## 9. Stability: 12 pairs x 3 end-to-end runs per family

| family | same call in all 3 runs | pairwise run-to-run agreement | mean sd of E[grade] | pool J run-to-run | read-set J run-to-run | router stable | OT verdict stable |
|---|---|---|---|---|---|---|---|
| claude | 11/12 (92%) | 34/36 (94%) | 0.05 | 0.87 | 0.55 | 12/12 (100%) | 12/12 (100%) |
| openai | 8/12 (67%) | 28/36 (78%) | 0.12 | 0.83 | 0.54 | 12/12 (100%) | 12/12 (100%) | 

cross-family agreement in the same run index: 29/36 (81%) (compare with each family's run-to-run agreement above)

| pair | saved | Claude r1 r2 r3 (E[grade]) | OpenAI r1 r2 r3 (E[grade]) |
|---|---|---|---|
| ABCE1 / mean corpuscular hemoglobin co | Novel* | Nov(1.4) Nov(1.5) Nov(1.4) | Nov(1.0) Nov(1.1) Hyp(1.7) |
| CCT7 / complex neurodevelopmental dis | Novel* | Nov(1.5) Nov(1.4) Nov(1.5) | Nov(1.2) Hyp(1.7) Hyp(1.8) |
| DGKE / Autism Spectrum Disorder | Novel | Nov(1.2) Nov(1.3) Nov(1.2) | Nov(1.0) Nov(1.0) Nov(1.0) |
| SMAD6 / Triglycerides | Hypot* | Nov(1.3) Nov(1.2) Nov(1.1) | Nov(1.0) Hyp(1.8) Nov(1.0) |
| ASCL1 / neurodevelopmental disorder | Hypot* | Exi(2.8) Exi(2.8) Exi(2.7) | Exi(2.9) Exi(2.9) Exi(2.9) |
| BRD4 / Autism Spectrum Disorder | Hypot | Hyp(2.3) Hyp(2.2) Hyp(2.3) | Hyp(2.1) Exi(2.8) Exi(2.8) |
| ZNF638 / Height | Exist* | Est(3.6) Exi(3.5) Est(3.6) | Est(3.9) Est(3.8) Est(3.8) |
| LRRC4 / Autism Spectrum Disorder | Exist* | Exi(2.9) Exi(2.9) Exi(2.8) | Exi(3.0) Exi(3.0) Exi(3.0) |
| SS18L1 / amyotrophic lateral sclerosis | Exist | Exi(3.0) Exi(3.1) Exi(3.2) | Exi(3.0) Exi(3.0) Exi(3.0) |
| DDX41 / myelodysplastic syndrome | Estab | Est(3.9) Est(3.9) Est(3.9) | Est(4.0) Est(4.0) Est(4.0) |
| TRIO / Autism Spectrum Disorder | Estab | Exi(3.4) Exi(3.4) Exi(3.2) | Exi(3.0) Exi(3.0) Exi(3.0) |
| NRXN1 / Autism Spectrum Disorder | Estab | Est(3.6) Est(3.7) Est(3.6) | Est(4.0) Est(4.0) Est(4.0) | 

stability spend (r2+r3): {'claude': '$4.00', 'openai': '$0.74'}
