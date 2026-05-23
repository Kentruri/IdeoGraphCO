# 7 — Benchmark de encoders

Compara N encoders × M semillas con los **mismos splits e hiperparámetros**
para aislar el efecto del pre-entrenamiento. Recomendado para defensa de tesis.

## Comando

```bash
# Una semilla (exploratorio, ~6-9 h en Mac)
python scripts/benchmark.py

# Multi-seed (rigor estadístico, ~18-27 h en Mac)
python scripts/benchmark.py --seeds 42 43 44

# Reporte
python scripts/compare_models.py
```

## Flags útiles

- `--models confliberto maria beto` — qué encoders correr (default: todos)
- `--seeds 42 43 44` — semillas
- `--max-epochs 5` — override para corridas rápidas
- `--skip confliberto` — saltar uno ya hecho
- `--continue-on-error` — no parar si falla uno

## Encoders disponibles

`src/training/benchmark/registry.py`:

| Alias | Modelo | Hipótesis |
|-------|--------|-----------|
| `confliberto` | ConfliBERT-Spanish | Pre-entreno en política → debería ser el mejor |
| `maria` | RoBERTa-bne (MarIA) | Generalista español enorme |
| `beto` | BERT-base español (BETO) | Baseline obligatorio |

## Output

| Archivo | Contenido |
|---------|-----------|
| `logs/benchmark/<alias>__seed<N>/metrics.json` | Métricas finales por corrida |
| `reports/benchmark_report.md` | Tabla comparativa MSE/R² + análisis |
| `reports/benchmark_metrics.csv` | Todas las métricas (modelo × semilla × eje) |
| `reports/{r2_per_axis,mse_per_axis,radar_comparison}.png` | Gráficos |

## Componentes

- [scripts/benchmark.py](../scripts/benchmark.py)
- [scripts/compare_models.py](../scripts/compare_models.py)
- [src/training/benchmark/registry.py](../src/training/benchmark/registry.py)
