# 7 — Benchmark de encoders

Compara los 4 encoders del anteproyecto (OE2) × M semillas con los **mismos
splits e hiperparámetros** para aislar el efecto del pre-entrenamiento.
Métrica principal: F1 Macro sobre el test (gold humano).

## Comando

```bash
# Una semilla (exploratorio)
python scripts/benchmark.py

# Multi-seed (rigor estadístico)
python scripts/benchmark.py --seeds 42 43 44

# Reporte
python scripts/compare_models.py
```

## Flags útiles

- `--models confliberto beto xlm-roberta` — qué encoders correr (default: todos)
- `--seeds 42 43 44` — semillas
- `--max-epochs 5` — override para corridas rápidas
- `--skip confliberto` — saltar uno ya hecho
- `--smoke-test` — 1 batch por modelo (valida pipeline)
- `--continue-on-error` — no parar si falla uno

## Encoders del benchmark

`src/training/benchmark/registry.py`:

| Alias | Modelo | Hipótesis |
|-------|--------|-----------|
| `confliberto` | ConfliBERT-Spanish | Pre-entreno en política → debería ser el mejor |
| `beto` | BERT-base español (BETO) | Baseline español estándar |
| `xlm-roberta` | XLM-RoBERTa base | Multilingual grande |
| `xlnet` | mDeBERTa (placeholder, TBD) | Ver `docs/preguntas-director.md` tema 4 |

## Output

| Archivo | Contenido |
|---------|-----------|
| `logs/benchmark/<alias>__seed<N>/metrics.json` | Métricas + confusion matrix por corrida |
| `reports/benchmark_report.md` | Tabla comparativa F1 / Precision / Recall / Accuracy |
| `reports/benchmark_metrics.csv` | Todas las métricas (encoder × seed × métrica) |
| `reports/f1_macro_per_encoder.png` | Bar chart con errorbars |
| `reports/confusion_matrix_<alias>.png` | Matriz de confusión por encoder |

## Componentes

- [scripts/benchmark.py](../scripts/benchmark.py) — orquestador (agnóstico al modelo)
- [scripts/compare_models.py](../scripts/compare_models.py) — reporte + gráficos
- [src/training/benchmark/registry.py](../src/training/benchmark/registry.py)
