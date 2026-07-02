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

## Componentes

- [src/inference/predictor.py](../src/inference/predictor.py) — carga checkpoint + forward + chunking
- [src/inference/heatmap.py](../src/inference/heatmap.py) — mapa de calor Plotly
