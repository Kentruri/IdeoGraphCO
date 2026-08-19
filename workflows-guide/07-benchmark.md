# 7 — Benchmark de encoders

Compara los 4 encoders del anteproyecto (OE2) × M semillas con los **mismos
splits e hiperparámetros** para aislar el efecto del pre-entrenamiento.
Métrica principal: **F1 Macro en VALIDACIÓN** — el test/gold se evalúa UNA
sola vez, con el modelo ganador, vía `scripts/final_eval.py` (P3.1). Evaluar
todos los modelos × semillas contra el test lo contaminaría por selección
(cada corrida pasa `+run_test=false` automáticamente).

## Comando

```bash
# Una semilla (exploratorio)
python scripts/benchmark.py

# Multi-seed (rigor estadístico)
python scripts/benchmark.py --seeds 42 43 44

# Reporte (métricas de validación, por semilla y agregadas)
python scripts/compare_models.py

# Evaluación FINAL en test — SOLO el ganador, una vez (P3.1)
python scripts/final_eval.py --checkpoint logs/checkpoints/<alias>__seed42/best.ckpt
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
| `xlnet` | `xlnet-base-cased` (inglés) | Decisión ago-2026: se mantiene el modelo del anteproyecto |

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
