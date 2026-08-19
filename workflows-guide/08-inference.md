# 8 — Inferencia

Toma un texto, carga el checkpoint del clasificador y devuelve la ideología
predicha + distribución de probabilidades sobre las 8 clases, visualizable
como mapa de calor HTML.

## API (uso desde código)

```python
from src.inference.predictor import IdeoClassifierPredictor
from src.inference.heatmap import create_heatmap, save_chart

predictor = IdeoClassifierPredictor("logs/checkpoints/confliberto__seed42/best.ckpt")
result = predictor.predict("Texto de la noticia...")
# {
#   "predicted_class": "populismo",
#   "confidence": 42.7,
#   "probabilities": {
#       "personalismo": 12.3, "institucionalismo": 8.4,
#       "populismo": 42.7, ...
#   }
# }

chart = create_heatmap(result["probabilities"], title="Análisis")
save_chart(chart, "heatmap.html")
```

## Comparación de varios documentos (heatmap grid)

```python
from src.inference.heatmap import create_heatmap_grid

results = [predictor.predict(t)["probabilities"] for t in texts]
grid = create_heatmap_grid(results, row_labels=medios, title="Comparación de medios")
save_chart(grid, "comparacion.html")
```

## Output

- `result["predicted_class"]` — nombre de la clase ganadora (string).
- `result["confidence"]` — probabilidad de la clase ganadora en `[0, 100]`.
- `result["probabilities"]` — dict con las 8 probabilidades (%). Suman ~100.
- Heatmap HTML interactivo (Plotly) si se solicita.

## Servicio HTTP (para IdeoGraphCO-BE)

```bash
IDEOGRAPH_CHECKPOINT=logs/checkpoints/<alias>/best.ckpt \
    uvicorn src.inference.api:app --host 0.0.0.0 --port 8080
```

| Endpoint | Contrato |
|----------|----------|
| `POST /classify` | `{"title","text"}` → `{"label","probabilities" (∈[0,1], suman 1),"model_version"}` |
| `POST /delta` | `{"p","q","method"}` → `{"delta_d"}` — métrica ΔD (P5.2, Jensen-Shannon por defecto) |
| `GET /health` | estado + versión del modelo |

Nota: el predictor local devuelve porcentajes (0-100); la API convierte a
probabilidades en `[0, 1]` (el formato del contrato con el backend).

## Componentes

- [src/inference/predictor.py](../src/inference/predictor.py) — carga checkpoint + forward + chunking
- [src/inference/heatmap.py](../src/inference/heatmap.py) — mapa de calor Plotly
- [src/inference/api.py](../src/inference/api.py) — servicio FastAPI (`/classify`, `/delta`)
- [src/inference/delta.py](../src/inference/delta.py) — métrica ΔD (P5.2)
