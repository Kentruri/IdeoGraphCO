# Paso 8 — Benchmark de encoders

## Qué hace

Entrena el mismo modelo (8 cabezas de regresión + filtro de politicidad opcional) con **N encoders distintos × M semillas** y compara cuál funciona mejor para tu dataset:

| Encoder | HuggingFace ID | Hipótesis |
|---------|----------------|-----------|
| **ConfliBERT-Spanish** | `eventdata-utd/ConfliBERT-Spanish-Beto-Cased-v1` | Pre-entrenado en política — debería ser el mejor |
| **RoBERTa-bne (MarIA)** | `PlanTL-GOB-ES/roberta-base-bne` | Generalista español con corpus enorme |
| **BETO** | `dccuchile/bert-base-spanish-wwm-cased` | El BERT español "estándar" |

## Por qué hacer este benchmark

Para la tesis, **no basta con afirmar** que ConfliBERT es mejor para política colombiana. Hay que **demostrarlo empíricamente** con métricas robustas (multi-seed) sobre un test set fijo.

## Cómo funciona

```
Mismo dataset → splits.json (pre-computado a disco) → 3 modelos × N semillas
                                                              │
                              ┌───────────────────────────────┴───────────┐
                              ▼                                           ▼
                       Cada corrida produce:                   Después del benchmark:
                       - logs/checkpoints/<run>/                scripts/compare_models.py
                       - logs/benchmark/<run>/metrics.json      → reports/benchmark_report.md
                       - logs/benchmark/<run>/stdout.log           + CSV + 3 PNG
```

## Archivos involucrados

### Configs (Hydra)
- [configs/model/confliberto.yaml](../configs/model/confliberto.yaml)
- [configs/model/maria.yaml](../configs/model/maria.yaml)
- [configs/model/beto.yaml](../configs/model/beto.yaml)
- [configs/trainer/default.yaml](../configs/trainer/default.yaml) — `precision: auto`, `fast_dev_run`

### Scripts
- [scripts/prepare_splits.py](../scripts/prepare_splits.py) — Pre-computar train/val/test
- [scripts/analyze_distribution.py](../scripts/analyze_distribution.py) — Diagnosticar el dataset
- [scripts/benchmark.py](../scripts/benchmark.py) — Lanza los entrenamientos (multi-seed)
- [scripts/compare_models.py](../scripts/compare_models.py) — Reporte comparativo

### Código
- [src/benchmark/registry.py](../src/benchmark/registry.py) — Lista de encoders disponibles
- [src/models/ideovect_model.py](../src/models/ideovect_model.py) — Modelo configurable con scheduler
- [src/data/datamodule.py](../src/data/datamodule.py) — Soporta splits desde disco

## Setup previo (en orden)

### 1. Verificar dataset etiquetado y filtrado

```bash
ls -la data/interim/labeled_news_clean.jsonl
```

Si no existe, completar los pasos 1-4 (scraping → cleaning → labeling → filtering).

### 2. Analizar distribución de scores

Identifica ejes con poca varianza ANTES de entrenar:

```bash
python scripts/analyze_distribution.py
```

Salida ejemplo:
```
Eje                  Media     Std     Var  >=0.3  >=0.5  >=0.7  Warning
--------------------------------------------------------------------------
personalismo         0.342   0.234   0.055    640    421    329
institucionalismo    0.589   0.198   0.039    920    788    523
populismo            0.193   0.158   0.025    320    150     45
doctrinarismo        0.122   0.097   0.009    120     48     18  ⚠️ varianza muy baja
soberanismo          0.118   0.103   0.011    140     68     23  ⚠️ <30 muestras altas
...
```

Los ejes con warnings probablemente tendrán **R² bajo independientemente del encoder**. No es culpa del modelo, es falta de señal en el dataset.

### 3. Pre-computar splits

Garantiza que TODAS las corridas (3 modelos × N semillas) usen exactamente los mismos índices de train/val/test:

```bash
python scripts/prepare_splits.py
```

Genera `data/processed/splits.json`. Si añades más datos al JSONL mañana, ese archivo no cambia (a menos que lo regeneres explícitamente). Esto es **crítico** para comparabilidad.

### 4. Instalar matplotlib (para gráficos del reporte)

```bash
pip install matplotlib
```

## Comandos

### Smoke test (validar pipeline, 1 min)

```bash
python scripts/benchmark.py --smoke-test
```

Corre `fast_dev_run` en los 3 modelos — 1 batch de train/val/test cada uno. Si esto funciona, la pipeline está bien y puedes lanzar el benchmark real.

### Benchmark real

```bash
source .venv/bin/activate

# Mantener Mac despierto (puede durar 6-8h con 1 semilla, 18-24h con 3)
caffeinate -d -i -s &

# 1 semilla (exploratorio, 6-8 horas)
python scripts/benchmark.py

# 3 semillas (rigor estadístico para tesis, 18-24 horas)
python scripts/benchmark.py --seeds 42 43 44

# Solo 2 modelos
python scripts/benchmark.py --models confliberto beto

# Continuar aunque uno falle
python scripts/benchmark.py --continue-on-error

# Resumir si se interrumpió
python scripts/benchmark.py --skip confliberto    # ya estaba hecho
```

### Generar reporte comparativo

```bash
python scripts/compare_models.py
```

### Entrenar UN solo modelo manualmente

```bash
# Default semilla 42
python -m src.training.train model=confliberto

# Override de semilla
python -m src.training.train model=maria data.seed=43

# Override de hiperparámetros
python -m src.training.train model=confliberto model.learning_rate=1e-5
```

## Salida

### Estructura de archivos generados

```
logs/
├── checkpoints/
│   ├── confliberto__seed42/    # checkpoints por corrida
│   ├── confliberto__seed43/
│   ├── maria__seed42/
│   └── ...
├── benchmark/
│   ├── confliberto__seed42/
│   │   ├── metrics.json        # métricas finales
│   │   └── stdout.log          # log completo del entrenamiento
│   ├── confliberto__seed43/
│   └── ...
├── lightning_logs/             # TensorBoard logs
└── hydra/                      # Output de Hydra por run

reports/
├── benchmark_report.md         # Reporte Markdown con tablas
├── benchmark_metrics.csv       # Todas las métricas en CSV
├── r2_per_axis.png             # Bar chart R² (con errorbars si multi-seed)
├── mse_per_axis.png            # Bar chart MSE
└── radar_comparison.png        # Radar comparativo
```

### El reporte Markdown

`reports/benchmark_report.md` incluye:

1. **Configuración** — Dataset, hiperparámetros, git commit
2. **Tabla resumen global** — Best val loss, avg R², avg MSE, train time
3. **R² por eje** — Una fila por eje, una columna por modelo, ganador automático
4. **MSE por eje** — Idem
5. **Análisis automático**:
   - Victorias por R² (cuántos ejes gana cada modelo)
   - **Rank promedio** (1 = mejor en cada eje, menor = mejor)

Cuando hay **multi-seed**, los valores se muestran como `media ± std`.

## Métricas que se comparan

| Métrica | Significado | Mejor |
|---------|-------------|-------|
| **R²** | Varianza explicada (puede ser negativo si modelo es peor que la media) | Mayor |
| **MSE** | Error cuadrático medio | Menor |
| **Best Val Loss** | Loss en validación al terminar | Menor |
| **Train time** | Minutos de entrenamiento | Menor |
| **Rank promedio** | Posición promedio entre ejes (1 = mejor) | Menor |

## Garantía de comparabilidad

Para que la comparación sea justa, las corridas usan:

- ✅ **Mismo dataset** (`data.data_path`)
- ✅ **Mismo split** (`data/processed/splits.json` pre-computado)
- ✅ **Mismos hiperparámetros base**: LR=2e-5, dropout=0.1, batch=16, warmup=10%, weight_decay=0.01
- ✅ **Mismas épocas máximas** y patience de early stopping
- ✅ **Misma loss**: solo regresión MSE (cabeza de politicidad deshabilitada)
- ✅ **Scheduler**: linear warmup + decay (estándar para fine-tuning BERT)
- ✅ **Workers seeded** (`worker_init_fn` para reproducibilidad del shuffle)
- ✅ **Mismo hardware**

La única diferencia es el **encoder pre-entrenado**.

## ⚠️ Limitación importante: mismos hiperparámetros

Usar los mismos HP en los 3 modelos significa:

- ✅ **Comparación estricta**: el efecto medido es del encoder, no del HP
- ⚠️ **Posible sesgo**: LR=2e-5 es óptimo para BERT-base pero **MarIA suele necesitar 1e-5**

Hay 2 maneras de presentarlo en la tesis:

**Opción A (simple)**: Documentar la decisión:
> "Se usaron los mismos hiperparámetros para los 3 encoders para aislar el efecto del pre-entrenamiento. Esto puede favorecer modelos cuyo LR óptimo coincide con 2e-5."

**Opción B (rigurosa)**: Pequeño barrido por modelo:
```bash
for lr in 1e-5 2e-5 3e-5; do
    python -m src.training.train model=maria model.learning_rate=$lr data.seed=42
done
```
Y elegir el mejor por `val/loss`. Triplica el tiempo pero es más defendible académicamente.

## Tiempo estimado

| Configuración | Tiempo en M1 (MPS, fp32) | Tiempo en GPU (RTX 3060+) |
|---------------|--------------------------|-----------------------------|
| Smoke test (3 modelos, 1 batch) | 1-2 min | 1-2 min |
| 1 modelo, 10 epochs | ~2-3 horas | ~30 min |
| 3 modelos × 1 semilla | ~6-9 horas | ~1.5 horas |
| **3 modelos × 3 semillas (recomendado tesis)** | **~18-27 horas** | **~4-5 horas** |
| Reporte | ~5 segundos | ~5 segundos |

## Interpretación de resultados

### Si ConfliBERT gana en TODOS los ejes
- Confirma la hipótesis: pre-entreno especializado es valioso para política colombiana
- Justifica usarlo como modelo final

### Si ConfliBERT pierde en algunos ejes
- Hipótesis matizada: ConfliBERT mejor en X, MarIA mejor en Y
- Posibles razones:
  - MarIA: más datos generales → mejor en vocabulario amplio
  - ConfliBERT: puede tener sesgo hacia el conflicto militar
  - Algún eje específico (ej: globalismo) puede beneficiarse de exposición a textos económicos generales

### Si los 3 son similares (R² ±0.05 con multi-seed)
- El encoder no es el cuello de botella
- Posibles causas: dataset pequeño, labels ruidosos, ejes con poca varianza
- Antes de cambiar arquitectura: más datos o mejor codebook

### Diferencias dentro del ruido (sin multi-seed)
Si solo corres 1 semilla, la diferencia entre R²=0.42 y R²=0.39 **puede ser ruido**. Con 1145 muestras políticas y test=15%, el test set tiene ~170 ejemplos — diferencias <0.05 no son confiables. **Por eso multi-seed es importante para la tesis.**

## Solución de problemas

### Out of memory
- Reducir batch: editar `configs/data/default.yaml`: `batch_size: 8`
- Reducir epochs: `python scripts/benchmark.py --max-epochs 5`

### Un modelo siempre falla con error de descarga
Algunos modelos en HuggingFace requieren login:
```bash
huggingface-cli login
```

### Quiero re-entrenar solo uno
```bash
# Borrar métricas anteriores
rm -rf logs/benchmark/confliberto__seed42/

# Volver a entrenar solo ese
python scripts/benchmark.py --models confliberto --seeds 42
```

### El CSV / gráficos no se generan
```bash
pip install matplotlib
```

### Quiero ver el log de una corrida específica
```bash
tail -f logs/benchmark/confliberto__seed42/stdout.log
```

### Lightning quiere graficar con val/loss y se queja
El filename del checkpoint está como `ideovect-epoch{epoch:02d}` (sin `val/loss`) para evitar problemas con el `/`. Si quieres incluir val_loss en el nombre, cámbialo a `ideovect-{val_loss:.4f}` (guion bajo, no slash).

## Extensión: añadir más encoders

Para añadir un cuarto modelo (ej: `xlm-roberta-base`):

1. Crear `configs/model/xlmr.yaml`:
```yaml
model_name: "FacebookAI/xlm-roberta-base"
encoder_alias: "xlmr"
num_axes: 8
learning_rate: 2e-5
dropout: 0.1
weight_decay: 0.01
warmup_ratio: 0.1
freeze_encoder_epochs: 0
use_politicity_head: false
```

2. Añadirlo a `src/benchmark/registry.py`:
```python
MODEL_REGISTRY = {
    "confliberto": "...",
    "maria": "...",
    "beto": "...",
    "xlmr": "FacebookAI/xlm-roberta-base",  # nuevo
}
```

3. Correr:
```bash
python scripts/benchmark.py --models xlmr
python scripts/compare_models.py
```

## Para la tesis

El benchmark genera evidencia empírica para:

1. **Metodología**: explicar el diseño (splits fijos, multi-seed, mismos HP, scheduler estándar)
2. **Resultados**: tabla comparativa + gráficos con errorbars
3. **Discusión**: análisis de por qué cada modelo gana en ciertos ejes
4. **Limitaciones**: declarar mismos HP, tamaño del dataset, ejes con baja varianza
5. **Apéndice**: CSV completo + git commit para reproducibilidad

## Cuándo correrlo

- **Después** del paso 4 (filtering) — necesitas dataset limpio
- **Después** de `prepare_splits.py` — para tener splits fijos
- **Antes** de elegir el modelo final del proyecto
- **Antes** de cualquier experimentación con hiperparámetros
