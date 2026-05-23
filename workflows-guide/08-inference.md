# 8 — Inferencia

Toma un texto, carga el checkpoint del modelo y devuelve los 8 scores +
opcionalmente un radar chart HTML.

## Comando

```bash
python -m src.inference.predict --text "El presidente anunció ..."
python -m src.inference.predict --file articulo.txt --radar salida.html
```

## API (uso desde código)

```python
from src.inference.predictor import IdeoVectPredictor
from src.inference.radar import create_radar_chart, save_chart

predictor = IdeoVectPredictor("logs/checkpoints/confliberto__seed42/best.ckpt")
result = predictor.predict("Texto de la noticia...")
# {"axes": {"personalismo": 72.4, "institucionalismo": 15.3, ...}}

chart = create_radar_chart(result["axes"], title="Análisis")
save_chart(chart, "radar.html")
```

## Output

- `result["axes"]` — dict con 8 valores en `[0, 100]` (escalado para visualización)
- Radar HTML interactivo (Plotly) si se solicita

## Componentes

- [src/inference/predictor.py](../src/inference/predictor.py) — carga checkpoint + forward
- [src/inference/radar.py](../src/inference/radar.py) — chart con Plotly
