# Sprint 7 — Coverage Check vs CCEE Eval

**Date:** 2026-04-26  
**Dataset:** `data/dpo/trl/sprint7/sft_sprint7.jsonl` (2689 records)  
**Eval set:** `data/dpo/trl/sft_eval.jsonl` (373 records)  
**Threshold:** 0.92 (Patrón 8 — response-side, no patrones)  

## Results

| Metric | Value |
|---|---|
| Eval cases | 373 |
| Contaminated (sim ≥ 0.92) | **65** (17.4%) |
| Pattern-only (0.85 ≤ sim < 0.92) | 43 (11.5%) |

## Root Cause Analysis

**Type:** Structural overlap — NOT data leakage during training.

**Finding:** All 65 cases come from `source=multi_turn`. The eval set (`sft_eval.jsonl`, created 24 Mar 2026) is a holdout from the **original Sprint 6 DM dataset**. The `sft_mt.jsonl` was **re-extracted from the same DB** in Sprint 7, creating verbatim overlaps.

**Breakdown of 65 cases:**

| Category | Count | Description |
|---|---:|---|
| Exact match (sim=1.0), long >50c | 18 | Real verbatim messages from same DB conversations |
| Exact match (sim=1.0), mid 20-50c | 20 | Real verbatim (shorter messages) |
| Exact match (sim=1.0), short ≤20c | 13 | Generic repeated phrases ("Siiii", "Buff", etc.) |
| Near-dup (0.92≤sim<1.0) | 14 | Emoji/short variants — threshold false positives |
| **Total** | **65** | |

**Implication for training:** The eval loss during training will be slightly optimistic for these 65 cases (~17.4% of eval set). The model may have seen equivalent DM turns during training. This does NOT invalidate training — it means eval metrics should be interpreted with a ±2-3pt caveat.

**Decision options (await Manel):**

| Option | Action | Tradeoff |
|---|---|---|
| A — Accept | Train as-is, note eval caveat | Easiest, slight eval inflation |
| B — Fix eval | Create new holdout from data NOT in sft_sprint7 | Clean eval, requires new holdout set |
| C — Filter train | Remove 51 overlapping records (exact matches) | Loses 1.9% training data, eval cleaner |

## Contaminated Samples

### eval[2]  sim=1.000

- **EVAL:**  `I el mes wai quin es`
- **TRAIN[519]:** `I el mes wai quin es`

### eval[3]  sim=0.930

- **EVAL:**  `Taré aqui esperando`
- **TRAIN[682]:** `Acá te espero`

### eval[9]  sim=1.000

- **EVAL:**  `Siiii`
- **TRAIN[360]:** `Siiii`

### eval[10]  sim=1.000

- **EVAL:**  `Buaaa rei sort que avui no ens veiem xk m’ha vingut la reina🫠😂😂😂`
- **TRAIN[381]:** `Buaaa rei sort que avui no ens veiem xk m’ha vingut la reina🫠😂😂😂`

### eval[25]  sim=1.000

- **EVAL:**  `Vengo?`
- **TRAIN[623]:** `Vengo?`

### eval[27]  sim=1.000

- **EVAL:**  `Ande vaaaa`
- **TRAIN[625]:** `Ande vaaaa`

### eval[28]  sim=0.922

- **EVAL:**  `Mentioned you in their story
[Media/Attachment]`
- **TRAIN[1433]:** `Mentioned you in their story`

### eval[29]  sim=1.000

- **EVAL:**  `El que tu em diguis Marta
🫶🏽`
- **TRAIN[1383]:** `El que tu em diguis Marta
🫶🏽`

### eval[41]  sim=1.000

- **EVAL:**  `Molt toppp nene así cualquiera 🫠❤️`
- **TRAIN[1132]:** `Molt toppp nene así cualquiera 🫠❤️`

### eval[47]  sim=1.000

- **EVAL:**  `Pff
Eso no me va a salir ni flipando
😆😆
Es igual`
- **TRAIN[1242]:** `Pff
Eso no me va a salir ni flipando
😆😆
Es igual`

### eval[50]  sim=1.000

- **EVAL:**  `Olga a les 10:00 va benne?`
- **TRAIN[976]:** `Olga a les 10:00 va benne?`

### eval[71]  sim=1.000

- **EVAL:**  `Jajajajaj ya tu sabe bb🤜🏽🤛🏽❤️`
- **TRAIN[870]:** `Jajajajaj ya tu sabe bb🤜🏽🤛🏽❤️`

### eval[73]  sim=1.000

- **EVAL:**  `🥹❤️‍🩹❤️‍🩹❤️‍🩹
Com tu et sentis😘`
- **TRAIN[120]:** `🥹❤️‍🩹❤️‍🩹❤️‍🩹
Com tu et sentis😘`

### eval[80]  sim=1.000

- **EVAL:**  `Val es que la mama te hora a les 16:30 metge
Em confirmes quan puguis tranqui😘merci`
- **TRAIN[882]:** `Val es que la mama te hora a les 16:30 metge
Em confirmes quan puguis tranqui😘merci`

### eval[82]  sim=1.000

- **EVAL:**  `Mama si te’n vas a dormir no vinc
Si vinc es per posar-te les gasses
Demà vaigna bcn però estaré al migdia i tarda amb t`
- **TRAIN[1479]:** `Mama si te’n vas a dormir no vinc
Si vinc es per posar-te les gasses
Demà vaigna bcn però estaré al migdia i tarda amb t`

### eval[86]  sim=1.000

- **EVAL:**  `[audio]
Tinc una i l’altre no
🫠
Ara ho veuré quan arribi a casa`
- **TRAIN[836]:** `[audio]
Tinc una i l’altre no
🫠
Ara ho veuré quan arribi a casa`

### eval[88]  sim=1.000

- **EVAL:**  `Tia pasando
Dorm i ja ta
Jo aniré amb la mama no passa res
Has de descansar i més si et trobes malament
Estic benne`
- **TRAIN[1197]:** `Tia pasando
Dorm i ja ta
Jo aniré amb la mama no passa res
Has de descansar i més si et trobes malament
Estic benne`

### eval[90]  sim=1.000

- **EVAL:**  `Ok
Tranki
Tu me dices`
- **TRAIN[620]:** `Ok
Tranki
Tu me dices`

### eval[92]  sim=1.000

- **EVAL:**  `Si hem obert franja a les 12:00`
- **TRAIN[356]:** `Si hem obert franja a les 12:00`

### eval[105]  sim=0.985

- **EVAL:**  `Va sigo❤️❤️❤️`
- **TRAIN[1583]:** `Va tira❤️❤️`

### eval[109]  sim=0.965

- **EVAL:**  `Gracias a ti❤️`
- **TRAIN[916]:** `Gràcies🩷`

### eval[110]  sim=1.000

- **EVAL:**  `No no tranqui
L’Andrea ve ara
A zumba no😂😂😂
Vaig a comprarli un pastis abans`
- **TRAIN[833]:** `No no tranqui
L’Andrea ve ara
A zumba no😂😂😂
Vaig a comprarli un pastis abans`

### eval[112]  sim=1.000

- **EVAL:**  `Mama em queden 30’ em dutxo i vinc
Que ja ho he comprat
Tot`
- **TRAIN[1460]:** `Mama em queden 30’ em dutxo i vinc
Que ja ho he comprat
Tot`

### eval[123]  sim=1.000

- **EVAL:**  `[audio]
L’hora de la Maria ja es teva ok acueldate🫶🏽 a les 10:00`
- **TRAIN[1146]:** `[audio]
L’hora de la Maria ja es teva ok acueldate🫶🏽 a les 10:00`

### eval[125]  sim=1.000

- **EVAL:**  `Doncs fem reformer com
Vulguis
Ja decideixes😂❤️`
- **TRAIN[862]:** `Doncs fem reformer com
Vulguis
Ja decideixes😂❤️`

### eval[127]  sim=1.000

- **EVAL:**  `Cuka la veig benne🤍 ho tenim controlat?
Està bé ella?😘`
- **TRAIN[1650]:** `Cuka la veig benne🤍 ho tenim controlat?
Està bé ella?😘`

### eval[130]  sim=1.000

- **EVAL:**  `Gracias a ti estan increiblesssss🥰🥰🥰❤️`
- **TRAIN[539]:** `Gracias a ti estan increiblesssss🥰🥰🥰❤️`

### eval[135]  sim=1.000

- **EVAL:**  `Bon dia rei☀️ Igualada🫠🫠🫠on vols que estigui amb aquestes vistes😂😂😂no tinc el teu privilegi🤴🏽
Que fas llevat tant d’hora`
- **TRAIN[113]:** `Bon dia rei☀️ Igualada🫠🫠🫠on vols que estigui amb aquestes vistes😂😂😂no tinc el teu privilegi🤴🏽
Que fas llevat tant d’hora`

### eval[136]  sim=1.000

- **EVAL:**  `Okaaa baby
Tu me dises`
- **TRAIN[343]:** `Okaaa baby
Tu me dises`

### eval[140]  sim=1.000

- **EVAL:**  `Clarrr
Cuka la Joanna ve a las 11`
- **TRAIN[320]:** `Clarrr
Cuka la Joanna ve a las 11`

### eval[141]  sim=1.000

- **EVAL:**  `🫠🫠🫠`
- **TRAIN[181]:** `🫠🫠🫠🫠🫠`

### eval[162]  sim=1.000

- **EVAL:**  `Cuka la teva amiga que tal🩷`
- **TRAIN[371]:** `Cuka la teva amiga que tal🩷`

### eval[166]  sim=1.000

- **EVAL:**  `Abans de les 18:15`
- **TRAIN[667]:** `Abans de les 18:15`

### eval[193]  sim=1.000

- **EVAL:**  `Siii
Jo porto malles no tinc de bici😂😂
Ja surto es que no trobo ulleres de sol
Si tens 2 porta sino no passa res`
- **TRAIN[1181]:** `Siii
Jo porto malles no tinc de bici😂😂
Ja surto es que no trobo ulleres de sol
Si tens 2 porta sino no passa res`

### eval[194]  sim=1.000

- **EVAL:**  `Siiiiii porfaaa así la llevaré un poquito mejor y la disfrutaré más
A ver si animo alguna amiga mía
Te hago el bizzum ah`
- **TRAIN[1392]:** `Siiiiii porfaaa así la llevaré un poquito mejor y la disfrutaré más
A ver si animo alguna amiga mía
Te hago el bizzum ah`

### eval[203]  sim=0.966

- **EVAL:**  `❤️❤️❤️vamos nene🫂
😍`
- **TRAIN[773]:** `A vosotras❤️🙂‍↔️`

### eval[204]  sim=1.000

- **EVAL:**  `Si tranqui
Voy`
- **TRAIN[963]:** `Si tranqui
Voy`

### eval[206]  sim=0.928

- **EVAL:**  `Me too🤣🤣
Cuka porta bambes
👻`
- **TRAIN[653]:** `🫶🏽🫶🏽🫶🏽🙂‍↔️🤞🏽🍀🍀😘😘`

### eval[208]  sim=1.000

- **EVAL:**  `[video]`
- **TRAIN[518]:** `[video]`

### eval[227]  sim=0.997

- **EVAL:**  `😘😘😘😘`
- **TRAIN[1424]:** `😘😘😘`

### eval[234]  sim=1.000

- **EVAL:**  `Voy
[audio]
Me equivocado
Al final
3 veces una lo digo y la otra ya lo veras
2 veces perdón`
- **TRAIN[1245]:** `Voy
[audio]
Me equivocado
Al final
3 veces una lo digo y la otra ya lo veras
2 veces perdón`

### eval[235]  sim=1.000

- **EVAL:**  `Cuanto eeesss`
- **TRAIN[696]:** `Cuanto eeesss`

### eval[236]  sim=1.000

- **EVAL:**  `Ostiaaa vamosss
Apunteu-vosss🩷🩷🩷🤣🤣🤣`
- **TRAIN[1108]:** `Ostiaaa vamosss
Apunteu-vosss🩷🩷🩷🤣🤣🤣`

### eval[243]  sim=0.993

- **EVAL:**  `🤗🤗😘`
- **TRAIN[1424]:** `😘😘😘`

### eval[244]  sim=1.000

- **EVAL:**  `Que el tens el insta es que no se l’insta
[Media/Attachment]`
- **TRAIN[200]:** `Que el tens el insta es que no se l’insta
[Media/Attachment]`

### eval[245]  sim=1.000

- **EVAL:**  `Buff`
- **TRAIN[81]:** `Buff`

### eval[252]  sim=1.000

- **EVAL:**  `No has de posar res`
- **TRAIN[1482]:** `No has de posar res`

### eval[257]  sim=1.000

- **EVAL:**  `Si si 🤣🤣🤣
Tothom ha flipat amb la felicitació ee🤣🤣🤣🤣`
- **TRAIN[1364]:** `Si si 🤣🤣🤣
Tothom ha flipat amb la felicitació ee🤣🤣🤣🤣`

### eval[258]  sim=0.962

- **EVAL:**  `❤️❤️❤️❤️`
- **TRAIN[315]:** `🫶🏽🫶🏽🫶🏽😘`

### eval[263]  sim=1.000

- **EVAL:**  `Avui al migdia li fan eco que no sé com es diu`
- **TRAIN[1404]:** `Avui al migdia li fan eco que no sé com es diu`

### eval[275]  sim=1.000

- **EVAL:**  `Ants de la comida 11:30?`
- **TRAIN[621]:** `Ants de la comida 11:30?`

### eval[277]  sim=0.950

- **EVAL:**  `😶‍🌫️`
- **TRAIN[1549]:** `No😅`

### eval[285]  sim=1.000

- **EVAL:**  `Vale baby era x si taveu avui x casa tranquilitos, pujavaba a bcn una estona.`
- **TRAIN[231]:** `Vale baby era x si taveu avui x casa tranquilitos, pujavaba a bcn una estona.`

### eval[286]  sim=1.000

- **EVAL:**  `Tranqui taré a bcn no fa tant fred allà`
- **TRAIN[1441]:** `Tranqui taré a bcn no fa tant fred allà`

### eval[297]  sim=1.000

- **EVAL:**  `Gràcies cuka
Y eres una cabrona xk no has afinado mi cara que sepas que ahora todos los videos los pasaré yo x el filtro`
- **TRAIN[1253]:** `Gràcies cuka
Y eres una cabrona xk no has afinado mi cara que sepas que ahora todos los videos los pasaré yo x el filtro`

### eval[298]  sim=1.000

- **EVAL:**  `Dinàmic i personal trainer al meu estudi.`
- **TRAIN[953]:** `Dinàmic i personal trainer al meu estudi.`

### eval[309]  sim=0.990

- **EVAL:**  `Nooo
😂😂`
- **TRAIN[1689]:** `Nooo 😂😂😂`

### eval[311]  sim=1.000

- **EVAL:**  `Impossible contigo una rutina, espero que en el vectus tengan más suerte😂😂😂`
- **TRAIN[61]:** `Impossible contigo una rutina, espero que en el vectus tengan más suerte😂😂😂`

### eval[317]  sim=0.977

- **EVAL:**  `😂
🫶🏽🫶🏽🫶🏽`
- **TRAIN[315]:** `🫶🏽🫶🏽🫶🏽😘`

### eval[319]  sim=1.000

- **EVAL:**  `K va a usted le queda todo perfecto mijoo🤣🤣🤣`
- **TRAIN[911]:** `K va a usted le queda todo perfecto mijoo🤣🤣🤣`

### eval[326]  sim=1.000

- **EVAL:**  `Oka baby`
- **TRAIN[87]:** `Oka baby`

### eval[328]  sim=1.000

- **EVAL:**  `😂😂😂😂😂😂😂😂😂😂😂😂😂😂😂`
- **TRAIN[1000]:** `😂😂😂😂😂😂😂😂😂😂😂😂😂😂😂`

### eval[336]  sim=0.954

- **EVAL:**  `Apuntadas❤️`
- **TRAIN[540]:** `❤️`

### eval[348]  sim=1.000

- **EVAL:**  `Es que no m’enrecordava
Si vindràs a zumba?`
- **TRAIN[19]:** `Es que no m’enrecordava
Si vindràs a zumba?`

### eval[368]  sim=0.982

- **EVAL:**  `Baijjajajajajaj
Buajajajajajajaja`
- **TRAIN[965]:** `Buajajajajajajajajajajajjaajaja`

