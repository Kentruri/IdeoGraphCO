# CLAUDE.md — IdeoGraphCO

## Proyecto

IdeoGraphCO es un sistema de **regresión multisalida (multi-output regression)** que cuantifica la intensidad ideológica en noticias colombianas a través de 8 dimensiones simultáneas. Es un trabajo de grado universitario.

En lugar de clasificar izquierda/derecha, el sistema genera una "huella digital ideológica" representada como un gráfico de radar donde 0 = neutralidad y la deformación hacia los bordes revela el sesgo.

## Arquitectura del modelo (pipeline completo)

1. **Encoder**: ConfliBERT-Spanish (`snowood1/ConfliBERT-Spanish`) — pre-entrenado en corpus de conflicto político en español.
2. **Filtro de Politicidad**: Capa Softmax binaria sobre el token [CLS] — clasifica si la noticia es política o no política (gate previo a la regresión).
3. **Cabezas de Regresión**: 8 MLPs independientes con activación Sigmoide — estiman la intensidad (0-100) de cada eje ideológico.
4. **Visualización**: Radar Charts interactivos con Plotly (normalización min-max).

## Los 8 ejes ideológicos (4 pares opuestos)

| Eje                | Opuesto           | Marcadores clave                                          |
|--------------------|------------------ |-----------------------------------------------------------|
| Personalismo       | Institucionalismo | Deícticos 1ra persona, nombres de líderes, retórica carismática |
| Institucionalismo  | Personalismo      | Léxico jurídico, referencias a la ley, formalidad          |
| Populismo          | Doctrinarismo     | Dicotomía pueblo vs. élite, lenguaje anti-establishment    |
| Doctrinarismo      | Populismo         | Rigidez teórica, uso de "ismos", abstracción ideológica    |
| Soberanismo        | Globalismo        | Fronteras, autonomía nacional, proteccionismo              |
| Globalismo         | Soberanismo       | Tratados internacionales, organismos multilaterales         |
| Conservadurismo    | Progresismo       | Orden tradicional, propiedad privada, valores familiares   |
| Progresismo        | Conservadurismo   | Reformas sociales, derechos de minorías, justicia climática |

## Loss function

```
TotalLoss = Σ(i=1..8) MSE(y_i, ŷ_i)
```

Métricas por eje: MSE y R² calculados con `torchmetrics`.

## Stack técnico

- **PyTorch Lightning**: bucle de entrenamiento, checkpoints, logging
- **Hydra**: configuración jerárquica de hiperparámetros (configs/)
- **torchmetrics**: métricas independientes por cada eje
- **Plotly**: radar charts interactivos
- **Newspaper3k**: scraping de noticias colombianas

## Pipeline de datos

1. `scripts/` — Scraping de noticias → `data/raw/`
2. `src/labeling/` — LLM-as-a-Judge con codebook político califica 0-100 por eje → `data/interim/`
3. `src/data/` — Tokenización + LightningDataModule → `data/processed/`
4. `src/models/` — IdeoVectModel (ConfliBERT + filtro + 8 cabezas)
5. `src/training/` — Entrenamiento con Lightning
6. `src/inference/` — Predicción + generación de radar chart

## Estructura del proyecto

```
src/
├── data/           # LightningDataModule, tokenización
├── labeling/       # Pipeline LLM-as-a-Judge
├── models/         # IdeoVectModel (encoder + filtro + 8 cabezas)
├── training/       # Bucle de entrenamiento Lightning
├── inference/      # Predicción + radar charts
├── utils/          # Métricas y helpers
└── paths.py        # Gestión de rutas con pathlib
```

## Convenciones de código

- Python >= 3.10
- Linter: ruff
- Tests: pytest (en tests/)
- Idioma del código: inglés (nombres de clases, funciones, variables)
- Idioma de documentación y comentarios: español donde sea necesario para contexto político
