# CLAUDE.md — IdeoGraphCO

## Proyecto

**Clasificador multiclase probabilístico** de ideología política en noticias
colombianas. Trabajo de grado universitario.

Cada artículo se asigna a **una** de 8 clases ideológicas (single-label,
mutuamente excluyentes). El modelo devuelve una distribución de probabilidades
sobre las 8 clases; la salida se visualiza como **mapa de calor** (no radar).

> Diseño previo: era regresión multisalida sobre 8 ejes en `[0,1]⁸`. Se
> migró a clasificador multiclase por requisito del anteproyecto aprobado.
> Ver `docs/preguntas-director.md` (varios temas ya RESUELTOS ago-2026:
> XLNet, pares de clases; sigue abierto el de la cabeza de politicidad).

## El anteproyecto (contrato de la tesis)

Documento aprobado: *"Desarrollo de clasificador multiclase para
identificación de orientación ideológica en noticias políticas colombianas"*
(Univalle, jun-2026; director: Raúl Gutiérrez de Piñerez). Es la fuente de
verdad ante cualquier duda de diseño — el jurado califica contra él.

**Pregunta de investigación**: ¿de qué manera el desarrollo y evaluación de
un clasificador multiclase, entrenado a partir de un corpus anotado de
noticias políticas colombianas, permite identificar la orientación
ideológica mediante ocho clases y presentar los resultados en un prototipo
interactivo?

**Objetivos específicos y productos comprometidos**:

| OE | Compromiso | Productos |
|----|-----------|-----------|
| OE1 | Corpus: scraping + refinamiento + etiquetado Gold/Silver según codebook | P1.1 scraper con dedup y limpieza · P1.2 codebook operacional · P1.3 dataset Gold+Silver con métricas de concordancia DOCUMENTADAS |
| OE2 | Benchmarking BETO / XLNet / XLM-RoBERTa / ConfliBERT-Spanish + segmentación + Softmax | P2.1 reporte con métricas por clase y análisis de varianza (multi-seed) · P2.2 modelo fine-tuned empaquetado · P2.3 componente de chunking validado |
| OE3 | Evaluar con Precision, Recall, F1 Macro sobre el conjunto de pruebas | P3.1 reporte con matrices de confusión por categoría y análisis de errores |
| OE4 | Prototipo web interactivo con el pipeline de inferencia | P4.1 prototipo que muestra la noticia, la clase predicha y la distribución de probabilidad (repos IdeoGraphCO-FE / IdeoGraphCO-BE) |

**Alcance declarado**:
- Dominio temático ESTRICTO: noticias políticas de Colombia (electoral,
  legislativo, política exterior, gobernanza). Se excluye farándula y lo
  judicial que no impacte la agenda pública — eso implementa el filter LLM.
- El TEMA debe ser colombiano, no solo el medio: la categoría
  `political_foreign` del filtro descarta la política de terceros países que
  la prensa colombiana cubre (elecciones en Chile, Irán-EE.UU.). La política
  exterior COLOMBIANA sí entra, porque el anteproyecto la declara en alcance.
- SOLO prensa colombiana (decisión reforzada ago-2026 con auditoría de
  colombianidad: medir % de contenido colombiano antes de añadir fuentes).
- Una sola distribución Softmax de dimensión 8 que suma 1.0 (single-label);
  las posturas macroeconómicas se asumen subsumidas en las 8 clases, no son
  clases aparte.

**Protocolo de anotación comprometido** (Krippendorff α = 1 − D_o/D_e):
- Gold: los DOS investigadores anotan una muestra de forma independiente;
  α ≥ 0.8 → discrepancias por consenso; α < 0.8 → iterar el codebook.
- Silver: LLM-judge sigue el codebook; auditoría CONTINUA sobre muestras
  aleatorias midiendo α entre el judge y el consenso de los investigadores.
  Ese α documentado es parte del producto P1.3, no opcional.

**Limitaciones declaradas** (citarlas, no resolverlas): subjetividad residual
del ground truth (el modelo aprende un consenso intersubjetivo, no una
"verdad"); dilución de señal por la agregación vectorial (encuadres agudos
localizados en un párrafo pueden atenuarse en V_doc). Las que surgieron en el
desarrollo, sobre todo las de `sin_encuadre`, están en su sección abajo.

## Las 8 clases ideológicas (4 ejes teóricos del anteproyecto §5.3)

La taxonomía se alinea con el **V-Party Dataset de V-Dem** — el emparejamiento
correcto es el de los ejes, no el "intuitivo" (aquí hubo un bug: el código
tenía los compañeros de los dos primeros ejes intercambiados hasta ago-2026):

| Eje teórico | Par | Anclaje V-Party |
|-------------|-----|-----------------|
| Gobernanza y discurso estamental | Populismo ↔ Institucionalismo | retórica populista (anti-élite) vs. compromiso con el pluralismo |
| Estructura de liderazgo político | Personalismo ↔ Doctrinarismo | control individual del líder sobre la estructura partidaria |
| Política exterior | Soberanismo ↔ Globalismo | nacionalismo económico vs. internacionalismo/multilateralismo |
| Sociocultural | Conservadurismo ↔ Progresismo | derechos civiles, diversidad de género, secularismo |

Definiciones y marcadores en
[src/agents/silver/codebook.py](src/agents/silver/codebook.py). Los pares
opuestos están declarados en `src.core.schema.OPPOSITE_PAIRS` y se usan
en el análisis de errores del OE3.

## Arquitectura del modelo

**Entrada canónica** (`src/core/text.py`, `build_model_input`): titular limpio
+ línea en blanco + cuerpo. La usan las TRES etapas que tocan la etiqueta —
judge, dataset e inferencia — porque antes divergían (el juez y el
entrenamiento veían solo `text`, la API antependía el titular: train/serve
skew). Al titular se le quita el sufijo del medio (`… | CONtexto Ganadero`):
es constante por fuente y sería una huella que el modelo usaría como atajo.

```
titular + cuerpo → K chunks de 512 tokens (sliding_window, stride=384, max K=16
              → cubre hasta el token 6.270; solape de 126 tokens = 25%)
                    ↓
              Encoder (BETO / ConfliBERT / XLM-RoBERTa / XLNet)
                    ↓
              K embeddings [CLS] — uno por chunk
                    ↓
              V_doc = (1/K) · Σ V_chunk_i    (agregación mean-pool con máscara)
                    ↓
              Dropout → Linear(H, 8) → Softmax (implícito en CE loss)
                    ↓
              P(clase | doc) sobre 8 ideologías
```

- **Loss**: Categorical Cross-Entropy.
- **Métricas** (`torchmetrics`, macro): Precision, Recall, F1, Accuracy,
  Confusion Matrix. `f1_macro` es la métrica principal del OE3.
- **Encoders del benchmark** (OE2):
  `dccuchile/bert-base-spanish-wwm-cased` (BETO),
  `eventdata-utd/ConfliBERT-Spanish-Beto-Cased-v1` (ConfliBERT),
  `FacebookAI/xlm-roberta-base` (XLM-RoBERTa),
  `xlnet-base-cased` (XLNet original en inglés; decisión ago-2026 de mantener
  el modelo comprometido en el anteproyecto — su bajo desempeño esperado en
  español es hallazgo del benchmark, no un error).
- **Encoder adicional de contexto largo** (decisión del autor, 2-nov-2026;
  FUERA del anteproyecto, consultar al director): `BSC-LT/MrBERT-es`
  (ModernBERT español del BSC, 150M, ventana de 8.192 tokens). Lee el
  artículo seguido, sin trocear ni promediar, y mide si la dilución del
  mean-pool —limitación declarada— cuesta acierto. En el Mac corre con un
  solo chunk de 4.096 tokens (8.192 no cabe en memoria; ver hallazgos abajo),
  que lee completo el 96,1 % del corpus. Va en `EXTRA_MODELS` del registry
  (no corre por defecto; `--models mrbert-es`, con `data.chunk_size=4096` y
  `data.max_chunks=1`, ver `logs/cadena_largo.sh`), mismo split y
  presupuesto que los demás.
  Regla fijada antes de ver resultados: si supera a BETO troceado por más de
  ~1,5–2 puntos de macro-F1 en validación, entra al benchmark oficial como
  quinto modelo; si no, se documenta en la tesis como alternativa intentada.
  Los 4 del anteproyecto se corren igual en ambos casos.
- **Cribado (1/2-nov, 1 semilla, train de 5.000, máx. 4 épocas, val por
  medio)**: BETO 0,752 · MrBERT-es (4.096) 0,750 · ConfliBERT 0,741 ·
  TF-IDF 0,733 · XLM-R 0,717 · BETO truncado a 512 0,716 (el troceo queda
  validado, P2.3) · XLNet 0,661 (el peor en las 8 clases). Finalistas: BETO
  y ConfliBERT. MrBERT-es NO cumple la regla (−0,2 puntos): no entra al
  benchmark oficial y se documenta como alternativa evaluada. IC 95 %
  bootstrap ≈ ±2 puntos: el orden entre los primeros no es concluyente con
  una semilla. Es selección preliminar, no el resultado de la tesis.

### Fundamento de los hiperparámetros

Receta estándar de fine-tuning de BERT, la MISMA para todos los encoders y
sin búsqueda por modelo (decisión de equidad y de cómputo; Devlin et al.
recomiendan buscar en sus rangos sobre dev, aquí no se hizo: citarlo como
limitación, puede desfavorecer a XLNet o XLM-R). Configs en
`configs/model/*.yaml`, `configs/data/default.yaml`, `configs/trainer/`.

| Parámetro | Valor | Fundamento |
|-----------|-------|------------|
| Tasa de aprendizaje | 2e-5 | Devlin et al. 2019, §A.3: rango {5e-5, 3e-5, 2e-5}; Sun et al. 2019 usan 2e-5; Mosbach et al. 2021: tasas pequeñas estabilizan |
| Lote efectivo | 16 | Devlin et al. 2019, §A.3: {16, 32}; se llega por acumulación de gradiente |
| Optimizador | AdamW, weight decay 0,01 | Loshchilov y Hutter 2019 (AdamW); 0,01 es el decay del preentrenamiento de BERT (Devlin et al. 2019, §A.2) |
| Calentamiento | 10 % lineal + decaimiento lineal | Programa de Devlin et al. 2019; proporción 0,1 de Sun et al. 2019 |
| Dropout de la cabeza | 0,1 | Devlin et al. 2019, §A.3; Sun et al. 2019 |
| Épocas / parada temprana | máx. 10, paciencia 3 | Decisión propia: Devlin sugiere 2–4 para corpus grandes; Mosbach et al. 2021 muestran que entrenar más iteraciones mejora la estabilidad; Dodge et al. 2020, parada temprana |
| Semillas | 3 (42, 43, 44) | Dodge et al. 2020: la semilla (inicialización de la cabeza y orden de datos) mueve el resultado; Reimers y Gurevych 2017: reportar distribuciones. Los valores son convención, fijados antes de ver resultados |
| Ventana | 512 tokens | Límite de posiciones de BERT (Devlin et al. 2019) |
| Desplazamiento / máx. ventanas | 384 / 16 | Decisión propia sobre la distribución de longitudes del corpus (silver train+val, 13.574 art., tokenizer de BETO: mediana 828, p95 3.039, p99 6.122; 79,6 % pasa de 512; de 8 a 16 ventanas, truncados 4,5 % → 0,9 % y tokens perdidos 9,7 % → 4,0 %, por +6,7 % de ventanas); troceo con solape + agregación: Pappagari et al. 2019, Dai et al. 2022 |
| Agregación | media de [CLS] con máscara | Anteproyecto §5.3 (V_doc) |
| Pesos de clase | raíz de la frecuencia inversa | Cui et al. 2019 (CVPR) la describen como la versión suavizada habitual de la frecuencia inversa |
| Gradient checkpointing | solo por memoria | Chen et al. 2016; no cambia el resultado (verificado: diferencia 0) |
| Precisión | FP32 en MPS; mixta en CUDA | Micikevicius et al. 2018 (mixta) |
| Validación agrupada por medio | 73 medios no vistos | Baly et al. 2020 |

**Sobre los valores de las semillas.** No significan nada: una semilla solo
fija el punto de partida del generador pseudoaleatorio, y misma semilla da
misma secuencia (misma cabeza inicial, mismo barajado, mismas máscaras de
dropout). No cambia el encoder preentrenado ni la partición (fija por ID en
`splits.json`). 42 es una convención de la comunidad, homenaje a Adams
(1979), donde 42 es la "respuesta a la pregunta fundamental de la vida, el
universo y todo lo demás"; 43 y 44 son los siguientes. No hay un estudio
revisado por pares que mida esa convención: citar a Adams solo como origen
del número, y a Dodge et al. (2020) para por qué se usan varias. Las tres se
fijaron antes de ver resultados y son las mismas para todos los modelos;
elegir la semilla a posteriori sería sesgo.

Referencias (todas verificadas, nov-2026):

- Adams, D. (1979). *The Hitchhiker's Guide to the Galaxy*. Pan Books.
- Baly, R., Da San Martino, G., Glass, J. y Nakov, P. (2020). We Can Detect
  Your Bias: Predicting the Political Ideology of News Articles. *EMNLP 2020*.
- Chen, T., Xu, B., Zhang, C. y Guestrin, C. (2016). Training Deep Nets with
  Sublinear Memory Cost. arXiv:1604.06174.
- Cui, Y., Jia, M., Lin, T.-Y., Song, Y. y Belongie, S. (2019).
  Class-Balanced Loss Based on Effective Number of Samples. *CVPR 2019*.
  arXiv:1901.05555.
- Dai, X., Chalkidis, I., Darkner, S. y Elliott, D. (2022). Revisiting
  Transformer-based Models for Long Document Classification. *Findings of
  EMNLP 2022*. arXiv:2204.06683.
- Devlin, J., Chang, M.-W., Lee, K. y Toutanova, K. (2019). BERT:
  Pre-training of Deep Bidirectional Transformers for Language
  Understanding. *NAACL 2019*. arXiv:1810.04805.
- Dodge, J., Ilharco, G., Schwartz, R., Farhadi, A., Hajishirzi, H. y
  Smith, N. A. (2020). Fine-Tuning Pretrained Language Models: Weight
  Initializations, Data Orders, and Early Stopping. arXiv:2002.06305.
- Loshchilov, I. y Hutter, F. (2019). Decoupled Weight Decay
  Regularization. *ICLR 2019*. arXiv:1711.05101.
- Micikevicius, P. et al. (2018). Mixed Precision Training. *ICLR 2018*.
  arXiv:1710.03740.
- Mosbach, M., Andriushchenko, M. y Klakow, D. (2021). On the Stability of
  Fine-tuning BERT: Misconceptions, Explanations, and Strong Baselines.
  *ICLR 2021*. arXiv:2006.04884.
- Pappagari, R., Żelasko, P., Villalba, J., Carmiel, Y. y Dehak, N.
  (2019). Hierarchical Transformers for Long Document Classification.
  *IEEE ASRU 2019*. arXiv:1910.10781.
- Reimers, N. y Gurevych, I. (2017). Reporting Score Distributions Makes a
  Difference: Performance Study of LSTM-networks for Sequence Tagging.
  *EMNLP 2017*.
- Sun, C., Qiu, X., Xu, Y. y Huang, X. (2019). How to Fine-Tune BERT for
  Text Classification? *CCL 2019*, LNCS 11856. arXiv:1905.05583.

### Hallazgos durante el entrenamiento (nov-2026, Mac M4 Pro de 24 GB)

Incidencias reales del benchmark, citables en la tesis como limitaciones de
cómputo y decisiones de ingeniería:

- **XLNet necesitó gradient checkpointing propio.** La implementación de HF
  no lo admite (`supports_gradient_checkpointing=False`) y sin él, con el
  batch mínimo (1 × 16), pedía ~26 GB en un equipo de 24: macOS lo mandó a
  swap (21,7 de 22,5 GB) y se arrastró a ~0,75 pasos/min (BETO: ~6,7); se
  detuvo el 2-nov en la época 1 (0,593). Se añadió checkpointing capa a capa
  (`ideoclassifier._checkpoint_layers`, `use_reentrant=False`; diferencia 0
  en pérdida y gradientes). Con él cabe a 1 × 16 (swap estable ~6 GB), entrena
  a ~3,4 pasos/min y completó el cribado en 371 min, el doble que BETO:
  **val macro-F1 0,661** (0,579 → 0,633 → 0,653 → 0,661 por época).
  IC 95 % bootstrap 0,637–0,683: por debajo de todos, incluido TF-IDF.
  La primera época quedó 1,4 puntos bajo la del intento detenido (0,593)
  con la misma semilla: MPS no es determinista entre corridas.
  Docker Desktop (VM de 8 GB, 6 contenedores) también ocupaba memoria; el
  autor lo cerró el 2-nov (memoria libre del sistema 19 % → 37 %).
- **Por qué XLNet rinde menos: su tokenizador inglés.** `xlnet-base-cased`
  (`keep_accents=False`) en val da 2,39 tokens por palabra (BETO: 1,27) y
  borra las tildes («está» = «esta», «publicó» = «publico»). La mediana de
  un artículo pasa de 814 a 1.540 tokens y el 3,5 % se trunca pasado el
  token 6.270 (BETO: 0,8 %; en todo `dataset.jsonl`: 4,1 % vs 0,9 %).
  Es la explicación que usa la tesis (§8.4); la receta común de
  hiperparámetros también podría desfavorecerlo (§11).
- **Memoria de la GPU (MPS).** Con el dropout activo, un batch de 8 artículos
  largos no cabe: BETO/ConfliBERT/XLM-R entrenan con gradient checkpointing
  (mismo resultado, ~30 % más lento); XLM-R además con batch 1 × 16 por su
  vocabulario de 250k. El batch efectivo es 16 en todos. Para no caer en swap
  se topa la GPU en 16 GiB (`PYTORCH_MPS_HIGH_WATERMARK_RATIO=1.0`, con
  `LOW_WATERMARK_RATIO=0.8`) y se usa un solo proceso de carga de datos.
- **MrBERT-es a un solo chunk de 4.096 tokens, no 8.192.** Con el tope de
  16 GiB, 8.192 tokens no cabe, ni 2 chunks de 4.096 con el optimizador
  (Adam ≈ 2 GB). Un chunk de 4.096 lee completo el 96,1 % de los artículos;
  el 3,9 % más largo se trunca a ~3.000 palabras (8× lo de BETO truncado).
  Con largos variables, el allocator de MPS acumulaba bloques: el modelo
  redondea el ancho a múltiplos de 256 y vacía la caché cada 50 batches.
  Su tokenizador no declara cls/sep: el dataset usa `<s>` / `</s>`.
- **Errores de código que se corrigieron antes del cribado**: el dropout
  interno del encoder quedaba apagado (transformers 5 devuelve el modelo en
  eval y Lightning ≥2.3 ya no llama a `.train()`); los chunks de relleno y el
  padding hasta `chunk_size` pasaban por el encoder (ahora solo lo real,
  salida idéntica); `hf-xet` colgaba las descargas de Hugging Face (se baja
  con `HF_HUB_DISABLE_XET=1` y se entrena con `HF_HUB_OFFLINE=1`).
- **Cabeza binaria de politicidad**: deshabilitada por defecto. Ver TBD en el
  docstring de `src/training/models/ideoclassifier.py` y
  `docs/preguntas-director.md` tema 1.

## Escalas y dataset

- **Formato categórico (actual, metodología del anteproyecto)**: el judge
  asigna la clase DOMINANTE → `{"label": "populismo", "label_idx": 2,
  "label_source": "silver-llm"}` + los 8 scores de intensidad en `[0,1]`
  como señal secundaria.
- **Formato legacy (silver continuo)** — solo 8 floats por artículo. El
  dataset lo convierte con `argmax` al vuelo vía `resolve_label_idx()`
  (con warning por empates). Deprecado: re-etiquetar con
  `python scripts/label.py --force`.
- **Gold (humano) v2**: `clase_dominante` obligatoria en Label Studio (el
  Excel es respaldo; las escalas 1-5 son opcionales): una de las 8 clases o
  `sin_encuadre` (ver abajo). Doble anotación independiente con solape →
  Krippendorff α ≥ 0.8 (`scripts/ingest_gold.py` +
  `src/agents/gold/agreement.py`); discrepancias por consenso. Salida con
  `label_source: human*`.

## sin_encuadre: opción de anotación, NO clase (decisión del autor, 3-nov-2026)

Noticia política sin encuadre ideológico: no cumple ninguno de los tres
criterios del umbral del codebook (voz propia evaluativa, selección asimétrica
de voces, prueba de sustracción); p. ej. el boletín, el parte operativo o la
nota de gestión. Existe como respuesta en Label Studio
(`src.core.schema.NO_FRAME_LABEL`) y en el silver, pero **no entra ni a
entrenamiento ni a test**: el Softmax sigue siendo de 8 y la pregunta de
investigación habla de ocho clases. Comentarla con el director.

**Por qué se decidió**: Juan anotó 207 artículos antes del codebook v1.1 y
puso institucionalismo en el 82 %, casi siempre en textos neutros. Con el v1.1
(22-24 oct) saltó 129 de 184 tareas porque la interfaz no tenía la opción, y
un salto no distingue "sin encuadre" de "texto roto". Donde los jueces ven
encuadre, Juan coincide con ellos en el 86 %. El α = 0,068 del tribunal sobre
los 262 lo hunden esas 207 anotaciones antiguas: **no citarlo como el α de
P1.3**. Juan las está rehaciendo.

**Implementación**: `ingest_gold.py` la cuenta para el α (decidir si hay
encuadre es parte de la codificación) y reporta además el α solo donde todos
ven encuadre; no la escribe en `gold_set_v2_labeled.jsonl`. Si un anotador
pone una clase y el otro `sin_encuadre`, va a consenso. Test de regresión en
`tests/test_gold_isolation.py`. En Label Studio, "saltar" queda solo para
texto roto o no político.

**A tener en cuenta en la tesis** (limitaciones y hallazgos a reportar):
- **El test queda solo con noticias con encuadre.** Al ritmo del v1.1 serían
  unos 400-500 de los 1.301; las clases raras tendrán pocos ejemplos.
  Reportar el F1 por clase con intervalos de confianza; con n ejemplos el
  intervalo del recall es de unos ±1,96·√(0,21/n): ±0,28 con 10, ±0,09 con 100.
- **El prototipo no sabe decir "neutra"**: ante una noticia sin encuadre igual
  elige una de las 8. Declararlo como limitación. Se consideró un filtro
  binario "¿tiene encuadre?" (redefinir la cabeza binaria del anteproyecto con
  los `sin_encuadre` como negativos) y se descartó el 3-nov para no salir del
  diseño de 8 clases: va como trabajo futuro. El tema 1 de
  `docs/preguntas-director.md` (que el filtro LLM cumpla el papel del
  clasificador binario de politicidad) sigue pendiente del director.
- **El porcentaje sin encuadre es un hallazgo**: 22 % de lo juzgado en el
  silver (que se minó buscando encuadre) frente a ~70 % del gold (muestra
  natural del corpus).
- **El α se reporta de dos formas**: sobre las 9 respuestas y solo donde los
  anotadores ven encuadre (el desacuerdo es sobre SI hay encuadre más que
  sobre CUÁL).
- **Doble anotación completa** (decisión del 3-nov): Kevin anota también los
  1.301 (`scripts/gold_solape.py`, tareas en
  `annotation/labelstudio/gold_set_v2_kevin_tasks.json`), empezando por los
  392 que Juan ya abrió. Así cada etiqueta del test sale del acuerdo o el
  consenso de dos, y el α alcanza a las clases raras: con una categoría del
  ~1 %, Krippendorff (2019, fórmula de Bloch y Kraemer 1989) pide ~1.350
  unidades con doble anotación para α mínimo 0,8 (con 8 clases igual de
  frecuentes bastarían ~120).

## Aislamiento del gold (no negociable)

Los **1.301 artículos** de `annotation/gold_set_v2_ids.json` son el conjunto
de PRUEBA del OE3. Dos reglas, ambas con test de regresión
(`tests/test_gold_isolation.py`):

- **No reciben etiqueta silver.** `scripts/label.py` los excluye por defecto
  leyendo ese archivo de IDs; contaminarlos haría que el modelo se evaluara
  contra el juicio de otro modelo en vez de contra el humano (métricas
  circulares). Hay que pasar `--allow-gold-in-silver` para saltarse la
  guarda.
- **No entran a train/val.** `scripts/prepare_splits.py` los manda al split
  de test y aplica además una guardia anti-fuga por near-duplicados. Los que
  el humano marca `sin_encuadre` no van al test, pero siguen en
  `gold_set_v2_ids.json`, así que tampoco entran a train/val.

Ninguna de las dos fugas da error en tiempo de ejecución: producen números
buenos y falsos.

## Alcance del repositorio

Este repo llega hasta el **checkpoint entrenado y su evaluación** (OE1-OE3).
La inferencia, el servicio HTTP y el prototipo (OE4) viven en
**IdeoGraphCO-BE**; se retiraron de aquí en sep-2026.

Tres contratos cruzan esa frontera y **ningún test puede verificarlos**:
el troceo (viaja en los hiperparámetros del checkpoint), la composición de la
entrada (`src/core/text.py::build_model_input`) y el orden de las 8 clases
(`src/core/schema.py`). Están escritos en
[docs/traspaso-inferencia-BE.md](docs/traspaso-inferencia-BE.md).

## Pipeline de datos

```
scraper.py (scrape+clean+filter LLM) → data/raw/articles.jsonl
        ↓
label.py (judge categórico: dominante + scores) → data/silver/silver_set.jsonl
        ↓
prepare_gold_set.py (libros por anotador + solape) → anotación humana
        ↓
ingest_gold.py (α de Krippendorff + consenso) → annotation/gold_set_v2_labeled.jsonl
        ↓
prepare_splits.py (dataset canónico + splits por ID, test=gold HUMANO)
        → data/processed/dataset.jsonl + splits.json
        ↓
src.training.train / scripts/benchmark.py (selección en VALIDACIÓN)
        ↓
scripts/final_eval.py (test UNA vez, P3.1) → reports/evaluacion_final.md
        ↓
checkpoint entrenado → IdeoGraphCO-BE (inferencia y prototipo, OE4)
```

## Estructura del proyecto (monorepo)

```
src/
├── core/                  # ids, paths, IDEOLOGY_CLASSES (fuente única)
├── scraper/
│   ├── sources.py         # 435 fuentes colombianas en 7 categorías
│   ├── parser.py          # trafilatura + UA rotativo
│   ├── cleaner.py         # regex (cookies, CTAs, URLs, handles)
│   ├── article_filter.py  # LLM filter con escalado automático
│   ├── prompts.py         # FILTER_SYSTEM_PROMPT aislado
│   ├── pipeline.py        # orquesta scrape→clean→filter
│   ├── db.py              # SQLite (dedup persistente)
│   └── robots.py
├── agents/
│   ├── silver/            # LLM-as-a-Judge (judge.py, codebook.py)
│   └── gold/              # (tooling de anotación humana)
├── training/
│   ├── data/              # dataset (article-level) + datamodule + collate
│   ├── models/            # IdeoClassifier
│   ├── benchmark/         # registry de los 4 encoders del PDF
│   └── train.py           # Hydra + Lightning Trainer

scripts/                   # CLIs delgados (orquestan src/)
configs/                   # Hydra (model, data, trainer)
annotation/                # gold set v2 (jsonl + ids + tareas de Label Studio)
data/                      # corpus en HF (data/corpus.lock ancla la revisión)
docs/                      # guías técnicas + preguntas al director
workflows-guide/           # guía paso a paso por etapa
```

## Fuentes (435 en 7 categorías — todas colombianas)

`src/scraper/sources.py` — distribución actual (ampliaciones + auditoría de
colombianidad, ago-2026; los medios extranjeros que "cubrían Colombia" se
dieron de baja tras medir que su contenido era mayormente de otros países):

| Categoría | # |
|-----------|---|
| Institucional | 140 |
| Regional | 99 |
| Gremial | 61 |
| Opinion (think tanks) | 53 |
| Independiente | 42 |
| Nacional | 24 |
| Judicial | 16 |

## Stack técnico

- **PyTorch Lightning + Hydra** — entrenamiento y configuración
- **transformers** — 4 encoders del OE2 (BETO / ConfliBERT / XLM-R / XLNet)
- **Trafilatura** — extracción robusta de artículos
- **Gemini API** — silver labels + filter LLM (con escalado auto). El filtro
  devuelve `category` + `confidence` + **`text_issues`**: los issues
  `digest_multinoticia` / `truncado` / `preview_paywall` DESCARTAN el artículo
  (rompen el supuesto single-label o no traen cuerpo), y
  `boilerplate_residual` solo se registra — es la señal para mejorar
  `cleaner.py`, visible en `scripts/analyze_filter_log.py`
- **torchmetrics** — Precision / Recall / F1 Macro / Accuracy / Confusion Matrix
- **Hugging Face Hub** — corpus en un dataset privado; `data/corpus.lock`
  ancla qué revisión corresponde a cada commit (`scripts/dataset_sync.py`)

## Convenciones de código

- Python >= 3.10
- Linter: ruff
- Tests: pytest (en `tests/`)
- Idioma del código: inglés (clases, funciones, variables)
- Idioma de docs/comentarios: español donde aporta contexto político
