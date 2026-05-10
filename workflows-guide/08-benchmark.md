# Paso 8 — Benchmark de encoders

## Qué hace

Entrena el mismo modelo (8 cabezas de regresión + filtro de politicidad) con **3 encoders distintos** y compara cuál funciona mejor para tu dataset:

| Encoder | HuggingFace ID | Hipótesis |
|---------|----------------|-----------|
| **ConfliBERT-Spanish** | `eventdata-utd/ConfliBERT-Spanish-Beto-Cased-v1` | Pre-entrenado en política — debería ser el mejor |
| **RoBERTa-bne (MarIA)** | `PlanTL-GOB-ES/roberta-base-bne` | Generalista español con corpus enorme |
| **BETO** | `dccuchile/bert-base-spanish-wwm-cased` | El BERT español "estándar" |

## Por qué hacer este benchmark

Para la tesis, **no basta con afirmar** que ConfliBERT es mejor para política colombiana. Hay que **demostrarlo empíricamente**:

1. Justifica la elección de ConfliBERT con números reales
2. Demuestra rigor metodológico
3. Identifica si hay ejes donde otros modelos son mejores
4. Defendible ante jurados

## Cómo funciona

```
Mismo dataset (labeled_news_clean.jsonl)
        ↓
Mismo split (semilla 42)
        ↓
Mismos hiperparámetros (LR=2e-5, batch=16, etc.)
        ↓
   ┌─────────────┬─────────────┬──────────┐
   │ ConfliBERT  │   MarIA     │   BETO   │
   │ entrenar    │  entrenar   │ entrenar │
   └─────┬───────┴─────┬───────┴────┬─────┘
         │             │            │
         ▼             ▼            ▼
    metrics.json  metrics.json  metrics.json
                       │
                       ▼
            scripts/compare_models.py
                       │
                       ▼
        reports/benchmark_report.md (+ CSV + PNG)
```

## Archivos involucrados

### Configs
- [configs/model/confliberto.yaml](../configs/model/confliberto.yaml)
- [configs/model/maria.yaml](../configs/model/maria.yaml)
- [configs/model/beto.yaml](../configs/model/beto.yaml)

### Scripts
- [scripts/benchmark.py](../scripts/benchmark.py) — Lanza los 3 entrenamientos
- [scripts/compare_models.py](../scripts/compare_models.py) — Genera el reporte
- [src/training/train.py](../src/training/train.py) — Modificado para guardar `metrics.json` por encoder

### Modelo
- [src/models/ideovect_model.py](../src/models/ideovect_model.py) — Acepta `model_name` configurable

## Setup previo

Necesitas el dataset filtrado (paso 4) y `matplotlib` para los gráficos:

```bash
ls data/interim/labeled_news_clean.jsonl    # debe existir
pip install matplotlib                       # para gráficos comparativos
```

## Comandos

### Entrenar los 3 modelos

```bash
source .venv/bin/activate

# Mantener Mac despierto (el benchmark dura 6-8 horas)
caffeinate -d -i -s &

# Entrenar los 3 secuencialmente
python scripts/benchmark.py

# Solo 2 modelos
python scripts/benchmark.py --models confliberto beto

# Saltar uno ya entrenado
python scripts/benchmark.py --skip confliberto

# Prueba rápida con 5 epochs
python scripts/benchmark.py --max-epochs 5

# Continuar aunque uno falle
python scripts/benchmark.py --continue-on-error
```

### Generar reporte comparativo

```bash
# Después de que terminen los 3 entrenamientos
python scripts/compare_models.py
```

### Entrenar UN solo modelo manualmente

Si prefieres entrenar manualmente:
```bash
# Con el config Hydra
python -m src.training.train model=confliberto
python -m src.training.train model=maria
python -m src.training.train model=beto

# Con override de hiperparámetros
python -m src.training.train model=confliberto trainer.max_epochs=20
```

## Salida

### Estructura de archivos generados

```
logs/
├── checkpoints/
│   ├── confliberto/
│   │   ├── ideovect-epoch=08-val_loss=0.0432.ckpt
│   │   └── last.ckpt
│   ├── maria/
│   │   └── ...
│   └── beto/
│       └── ...
├── benchmark/
│   ├── confliberto/metrics.json
│   ├── maria/metrics.json
│   └── beto/metrics.json
└── lightning_logs/
    ├── confliberto/...      # TensorBoard logs
    ├── maria/...
    └── beto/...

reports/
├── benchmark_report.md       # Reporte Markdown
├── benchmark_metrics.csv     # Métricas en formato CSV
├── r2_per_axis.png           # Bar chart R² por eje
├── mse_per_axis.png          # Bar chart MSE por eje
└── radar_comparison.png      # Radar chart comparativo
```

### Contenido del reporte Markdown

`reports/benchmark_report.md` tiene:

1. **Configuración** — Dataset, hiperparámetros, modelos comparados
2. **Tabla resumen global** — Best val loss, avg R², avg MSE, train time
3. **R² por eje y modelo** — Tabla con ganador por eje
4. **MSE por eje y modelo** — Idem
5. **Análisis automático** — Cuántos ejes gana cada modelo

## Métricas que se comparan

| Métrica | Significado | Mejor |
|---------|-------------|-------|
| **R²** | Varianza explicada (0-1) | Mayor |
| **MSE** | Error cuadrático medio | Menor |
| **Best Val Loss** | Loss en validación al terminar | Menor |
| **Train time** | Minutos de entrenamiento | Menor |

## Tiempo estimado

| Fase | Tiempo en M1 (MPS) | Tiempo en GPU (RTX 3060+) |
|------|--------------------|-----------------------------|
| ConfliBERT (1 modelo, 10 epochs) | ~2 horas | ~30 min |
| MarIA | ~2 horas | ~30 min |
| BETO | ~2 horas | ~30 min |
| **Total benchmark** | **~6-7 horas** | **~1.5 horas** |
| Reporte | ~5 segundos | ~5 segundos |

Para una prueba rápida (`--max-epochs 5`): ~3-4 horas en M1, ~45 min en GPU.

## Garantía de comparabilidad

Para que la comparación sea justa, los 3 entrenamientos usan:

- ✅ **Mismo dataset** (mismo `data.data_path`)
- ✅ **Mismo split** (`seed=42` determinista)
- ✅ **Mismos hiperparámetros**: LR=2e-5, dropout=0.1, batch=16, weight_decay=0.01
- ✅ **Mismas épocas máximas** y patience de early stopping
- ✅ **Mismo hardware** (corren en la misma máquina)
- ✅ **Mismo tokenizer** que el encoder (cada uno con su propio tokenizer)

La única diferencia es el **encoder pre-entrenado**.

## Interpretación de resultados

### Si ConfliBERT gana en TODOS los ejes
- Confirma tu hipótesis: el pre-entreno especializado en política es valioso
- Justifica usarlo como modelo final

### Si ConfliBERT pierde en algunos ejes
- Hipótesis matizada: ConfliBERT es mejor en X, pero MarIA es mejor en Y
- Posibles razones:
  - MarIA tiene más datos generales → mejor con vocabulario amplio (ej: ciencia, economía)
  - ConfliBERT puede tener sesgo hacia el conflicto militar

### Si BETO gana en algunos
- BETO tiene buen balance — útil cuando el otro está sobreajustado al dominio

### Si los 3 son similares (R² ±0.05)
- El encoder no es el cuello de botella
- Posible problema: dataset pequeño o labels ruidosos
- Considerar más datos o mejores labels antes de cambiar arquitectura

## Solución de problemas

### Out of memory
Reducir batch size:
```bash
python scripts/benchmark.py --max-epochs 10
# O modificar configs/data/default.yaml: batch_size: 8
```

### Un modelo siempre falla con error de descarga
Algunos modelos requieren login en HuggingFace. Verificar:
```bash
huggingface-cli login
```

### Quiero re-entrenar solo uno
```bash
# Borrar métricas anteriores
rm -rf logs/benchmark/confliberto/

# Volver a entrenar solo ese
python scripts/benchmark.py --models confliberto
```

### El CSV / gráficos no se generan
Verificar que matplotlib está instalado:
```bash
pip install matplotlib
```

## Para la tesis

El benchmark genera evidencia empírica para:

1. **Sección de Metodología**: explicar el diseño del benchmark
2. **Sección de Resultados**: mostrar la tabla comparativa y los gráficos
3. **Sección de Discusión**: analizar por qué ConfliBERT es mejor (o no)
4. **Apéndice**: incluir el CSV completo para reproducibilidad

El reporte Markdown se puede convertir a LaTeX o Word fácilmente.

## Cuándo correrlo

- **Después** del paso 4 (filtering) — necesitas el dataset limpio
- **Antes** de elegir el modelo final — el benchmark decide qué encoder usar
- **Antes** de cualquier experimentación con hiperparámetros — primero asegurar que el encoder es óptimo

## Extensión: comparar más modelos

Para añadir un cuarto modelo (ej: `xlm-roberta-base`):

1. Crear `configs/model/xlmr.yaml`:
```yaml
model_name: "FacebookAI/xlm-roberta-base"
encoder_alias: "xlmr"
# (resto igual a los demás)
```

2. Añadir `"xlmr"` a `AVAILABLE_MODELS` en `scripts/benchmark.py`

3. Correr:
```bash
python scripts/benchmark.py --models xlmr
python scripts/compare_models.py
```
