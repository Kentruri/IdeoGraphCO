# Traspaso de la inferencia a IdeoGraphCO-BE

Este repositorio llega hasta el **checkpoint entrenado y su evaluación**
(OE1-OE3). La inferencia, el servicio HTTP y el prototipo (OE4) viven en
IdeoGraphCO-BE.

## Qué se retiró de aquí

Todo sigue recuperable del historial:

```bash
git log --oneline -- src/inference          # el commit de la retirada
git show <commit>^:src/inference/predictor.py > predictor.py
```

| archivo | líneas | qué hacía |
|---|---|---|
| `src/inference/predictor.py` | 161 | carga el checkpoint, trocea el texto, devuelve clase + probabilidades |
| `src/inference/api.py` | 110 | servicio HTTP `POST /classify` |
| `src/inference/heatmap.py` | 107 | mapa de calor de la distribución (Plotly) |
| `src/inference/delta.py` | 116 | ΔD: distancia de Jensen-Shannon entre huellas ideológicas |
| `tests/test_delta.py` | 53 | tests de ΔD |
| `workflows-guide/08-inference.md` | 60 | guía de uso |

## Las tres reglas que el BE debe respetar

Ninguna se puede verificar con un test desde aquí: **ningún test cruza la
frontera entre repositorios**. Por eso quedan escritas.

### 1. El troceo sale del checkpoint, no de una config

`IdeoClassifier` guarda `chunk_size`, `chunk_stride` y `max_chunks` en sus
hiperparámetros, y `tests/test_labels.py::test_checkpoint_carries_its_own_chunking`
lo garantiza. El BE los lee de ahí:

```python
ckpt = torch.load(path, map_location="cpu")
hp = ckpt["hyper_parameters"]
chunk_size  = hp["chunk_size"]
chunk_stride = hp["chunk_stride"]
max_chunks  = hp["max_chunks"]
```

**No los escribas a mano.** Ese bug ya ocurrió una vez: se entrenaba con
`max_chunks=16` y se servía con 8, así que el modelo veía hasta el token 6.270
al entrenar y solo 3.198 al predecir. No da ningún error — solo peores
predicciones, y peores justo en los artículos largos, que es donde más
importa.

Antes el predictor leía esos valores de `configs/data/default.yaml`. Ese
archivo no existe en el BE, así que el checkpoint pasó a describirse a sí
mismo: es lo que hace seguro este traspaso.

### 2. La entrada se compone igual que en el entrenamiento

`src/core/text.py::build_model_input` es la fuente única: **titular limpio +
línea en blanco + cuerpo**, con el sufijo del medio quitado del titular
(`… | El Tiempo`, `… - Indepaz`). Cópiala tal cual.

Si el BE le pasa solo el cuerpo, o el titular sin limpiar, el modelo ve en
producción algo distinto de lo que aprendió. El sufijo importa especialmente:
es constante por medio, así que el modelo podría haberlo usado como atajo si
no se quitara — por eso se quita en las dos puntas.

### 3. Las 8 clases y su orden

`src/core/schema.py::IDEOLOGY_CLASSES` define el orden de los índices, y el
`CONTRACT.md` del BE replica la lista. **Si cambia aquí, cambia allí.** Un
desajuste de orden no falla: simplemente devuelve la clase equivocada con
plena confianza.

## Lo que el BE ya tiene

Su `CONTRACT.md` define el `ClassificationDTO` esperado:

```jsonc
{
  "label": "populismo",                  // argmax
  "probabilities": { "personalismo": 0.12, /* …8 claves, suman 1.0 */ },
  "model_version": "mock-0.1.0"
}
```

`predictor.py` ya devolvía exactamente esa forma. El `mock-0.1.0` se
sustituye por la versión real cuando el checkpoint del OE2 esté listo.
