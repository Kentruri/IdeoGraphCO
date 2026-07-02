# Consultas al director — Ajustes de diseño antes de la Fase 3

Antes de implementar la Fase 3 (Entrenamiento del clasificador multiclase) del
anteproyecto, hay varias decisiones de diseño que requieren su aprobación por
implicar posibles ajustes al alcance descrito en el PDF aprobado.

Ninguna cambia los objetivos generales del proyecto ni los productos esperados;
solo ajusta detalles arquitectónicos para maximizar calidad técnica y
reproducibilidad. Todos los cambios se documentarían en la tesis final con la
justificación correspondiente.

---

## 1. Clasificador binario de politicidad (crítico)

**Lo que dice el PDF (Fase 3, OE2 P2.2):**
> "La red integrará un clasificador binario como filtro de politicidad
> (optimizado mediante CrossEntropyLoss) Y una capa de clasificación lineal
> de 8 neuronas acoplada a una función de activación softmax."

**Situación actual:**
Durante la implementación del pipeline de scraping, integramos un filter LLM
(Gemini 2.5-flash-lite con escalado automático a Gemini 2.5-flash cuando la
confidence < 0.7) que clasifica cada artículo en 4 categorías:
`political_article`, `nonpolitical_article`, `biography_static`, `garbage`.
Solo los `political_article` pasan al modelo. Este filter opera **aguas
arriba** del modelo neural, no dentro de él.

**Opciones:**

- **Opción A (fidelidad literal al PDF):** Mantener el filter LLM Y añadir la
  cabeza binaria dentro del modelo neural. Requiere modificar el filter para
  conservar los `nonpolitical_article` como muestras negativas.
- **Opción B (arquitectura de dos etapas):** Considerar que el filter LLM del
  pipeline ES el clasificador binario del sistema (cumple la función pero
  fuera del modelo neural). Modelo queda con solo la cabeza softmax 8-way.
- **Opción C (ambas):** Filter LLM aguas arriba + cabeza binaria dentro del
  modelo (redundante).

**Recomendación técnica:** Opción B. Argumentos:
1. Un LLM (Gemini) tiene mayor capacidad de razonamiento que un linear layer
   sobre embeddings BERT para la tarea binaria de politicidad.
2. Si el dataset de entrenamiento es 100% político (como está actualmente),
   la cabeza binaria dentro del modelo neural aprendería una tarea trivial
   (todos positivos → convergencia a probabilidad 1.0) y añadiría loss
   sin señal útil.
3. Reportaríamos las métricas del filter LLM aparte (accuracy, F1) como
   componente del sistema.

**Pregunta al director:** ¿Aprueba la Opción B o requiere la fidelidad literal
al PDF (Opción A)?

---

## 2. Composición del dataset final

**Lo que dice el PDF (Alcance 4.1):**
> "Corpus bruto de noticias políticas colombianas extraído de múltiples
> fuentes y con metadatos estructurados."

**Situación actual:**
El corpus filtrado (`data/raw/articles.jsonl`) contiene 544 artículos, todos
clasificados como `political_article` por el filter LLM. Las categorías
`nonpolitical_article`, `biography_static` y `garbage` se descartaron.

**Pregunta:** ¿El dataset final debe ser 100% político (como está) o incluir
muestras no políticas como negativos? Esta decisión depende de la respuesta a
la pregunta 1:
- Si Opción A → necesitamos conservar no-políticos en el dataset.
- Si Opción B → dataset 100% político como está.

---

## 3. Formato del Gold Set (anotación humana)

**Situación actual:**
El Excel de anotación (`annotation/gold_set_v1.xlsx`) que estamos completando
manualmente pide a los anotadores:
- 8 columnas (una por cada eje ideológico).
- Escala 1-5 en cada columna (1=Ausente, 2=Leve, 3=Moderado, 4=Marcado,
  5=Dominante).
- Es decir, un anotador puede marcar `personalismo=5, populismo=4,
  progresismo=2, ...` para el mismo artículo.

**Conflicto con el PDF:**
El anteproyecto pide clasificador multiclase single-label (una categoría
dominante por artículo). El formato actual del Excel es multi-output
(intensidades simultáneas). Para reconciliar:

- **Opción A (preservar el trabajo humano):** Convertir con `argmax` — el eje
  con la nota más alta se declara la clase dominante. Empates se resuelven
  por orden canónico.
- **Opción B (rehacer el Excel):** Cambiar el Excel para que los anotadores
  elijan directamente 1 de 8 categorías. Se perdería el trabajo ya hecho.
- **Opción C (formato híbrido):** Mantener las 8 columnas 1-5 y añadir una
  columna extra "categoría dominante" que los anotadores marcan explícitamente.

**Recomendación técnica:** Opción A. Preserva el trabajo humano completo y
además da granularidad adicional para futuros análisis (por ejemplo, medir
intensidad de la ideología ganadora vs. secundaria).

**Pregunta al director:** ¿Aprueba mantener el formato actual y convertir con
`argmax`, o prefiere alguna otra opción?

---

## 4. Encoders del benchmark: problema con XLNet

**Lo que dice el PDF (OE2):**
> "BETO, XLNet, XML-RoBERTa y ConfliBERT-spanish" *(nota: en el PDF aparece
> "XML-RoBERTa"; el nombre correcto en la comunidad es XLM-RoBERTa).*

**Situación:**

| Modelo | Path oficial HuggingFace | Estado |
|--------|--------------------------|--------|
| BETO | `dccuchile/bert-base-spanish-wwm-cased` | Oficial, estable |
| ConfliBERT-Spanish | `eventdata-utd/ConfliBERT-Spanish-Beto-Cased-v1` | Oficial, estable |
| XLM-RoBERTa | `FacebookAI/xlm-roberta-base` | Oficial, estable |
| **XLNet** | ❌ **No hay versión oficial en español** | Opciones abajo |

**Alternativas para XLNet:**

- **A) `xlnet-base-cased`** — versión oficial en inglés. Uso cross-lingual;
  probablemente rinda mal en política colombiana.
- **B) `flax-community/xlnet-base-spanish`** — versión de la comunidad, no
  oficial. Calidad no garantizada.
- **C) Reemplazar XLNet** por otro encoder con mejor soporte en español
  (ejemplo: `microsoft/mdeberta-v3-base`, que es multilingual y de calidad
  probada).

**Recomendación técnica:** Opción C — reemplazar XLNet por mDeBERTa. Justificación:
usar un modelo comunitario de calidad no verificada podría contaminar los
resultados del benchmark y hacer difícil argumentar conclusiones ante evaluadores.

**Pregunta al director:** ¿Aprueba reemplazar XLNet por mDeBERTa? ¿O prefiere
mantener XLNet aún con la limitación?

---

## 5. Silver Set: cómo etiquetar

**Situación actual:**
Los 544 silver labels actuales fueron generados con escala continua [0, 1]
(diseño anterior de multi-output regression). Con el cambio a clasificación
multiclase (single-label), tenemos:

- **Opción A: Convertir con argmax** el silver continuo actual. Rápido y gratis.
  Riesgo: si el LLM se auto-empató en dos ejes (por ejemplo, `personalismo=0.42,
  populismo=0.42`), la conversión es arbitraria.
- **Opción B: Re-etiquetar con nuevo prompt** que pida directamente "categoría
  dominante". Fidelidad literal al PDF. Costo: ~COP 3,600, tiempo: ~25 min.

**Recomendación técnica:** Opción B. El PDF dice explícitamente en Fase 1:
> "asignando la clasificación categórica de la ideología política predominante
> a cada artículo".

**Pregunta al director:** ¿Aprueba re-etiquetar los 544 con el nuevo prompt
categórico (~COP 3,600)?

---

## 6. Manejo de textos largos: parámetros

**Lo que dice el PDF (Sec 5.3 y OE2 P2.3):**
> "segmentación secuencial por bloques" con agregación
> `V_doc = (1/K) · Σ V_chunk_i`.

**Detalles no especificados en el PDF que requieren decisión:**

- Tamaño de cada chunk.
- Overlap entre chunks (si aplica).
- Máximo de chunks por artículo (para evitar problemas de memoria).

**Propuesta técnica:**
- `chunk_size = 512 tokens` (límite arquitectónico de BERT).
- `chunk_stride = 384 tokens` (25% de overlap; estándar en literatura BERT).
- `max_chunks = 8` por artículo (≈ 2000 tokens efectivos ≈ artículo típico
  completo).
- Agregación: promedio simple aritmético (fidelidad literal al PDF).

**Pregunta al director:** ¿Aprueba estos parámetros?

---

## 7. Métricas de evaluación

**Lo que pide el PDF (OE3):**
> "Precision, Recall y F1-Score Macro" sobre el conjunto de pruebas
> + "matrices de confusión por categoría y análisis de errores".

**Métricas adicionales sugeridas** (no en el PDF, pero refuerzan la tesis):

- **Accuracy general** — métrica básica de referencia.
- **Cohen's Kappa** — concordancia entre predicción y ground truth,
  útil para comparar contra baseline aleatorio.
- **Matthews Correlation Coefficient (MCC)** — robusto ante desbalance de
  clases.
- **Análisis de "% de errores que caen en la clase opuesta"** — aprovecha
  el diseño de 4 pares del codebook (personalismo↔institucionalismo,
  populismo↔doctrinarismo, soberanismo↔globalismo, conservadurismo↔progresismo).
  Un error entre opuestos es más grave que un error entre ejes ortogonales.

**Pregunta al director:** ¿Aprueba incluir estas métricas adicionales o
prefiere ceñirnos estrictamente a las del PDF?

---

## Resumen de decisiones pendientes

| # | Tema | Opción recomendada por estudiante |
|---|------|-----------------------------------|
| 1 | Clasificador binario de politicidad | B (filter LLM como componente aguas arriba, modelo neural con 1 cabeza) |
| 2 | Composición del dataset | 100% político (consistente con opción B de tema 1) |
| 3 | Formato del Gold Set | Mantener multi-columna 1-5 y convertir con argmax |
| 4 | Reemplazo de XLNet | mDeBERTa (`microsoft/mdeberta-v3-base`) |
| 5 | Re-etiquetado del silver | Sí, re-etiquetar (~COP 3,600) |
| 6 | Parámetros de chunking | chunk_size=512, stride=384, max_chunks=8 |
| 7 | Métricas adicionales | Incluir Cohen's Kappa, MCC y análisis de opuestos |
