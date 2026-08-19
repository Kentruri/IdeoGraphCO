# 4 — Gold set humano (Handwrite)

Muestreo estratificado de N artículos y exporta a Excel para anotación humana.
El gold set es el **test set** del modelo (mientras silver es train/val).

**v2 (metodología del anteproyecto):** cada anotador recibe SU libro, con un
bloque de **solape** (los mismos artículos para ambos → Krippendorff α) y un
bloque exclusivo. Además de las escalas 1-5, se marca la **clase dominante**
(obligatoria) — la etiqueta categórica que consume el clasificador.

## Comando

```bash
python scripts/prepare_gold_set.py --annotators kevin juan --target 200 --overlap 60
```

## Flags útiles

- `--target 200` — cuántos artículos ÚNICOS muestrear (default 200)
- `--overlap 60` — tamaño del bloque compartido para α (default 60)
- `--annotators kevin juan` — nombres (default anotador1 anotador2)
- `--seed 42` — semilla del muestreo

## Output

| Archivo | Contenido |
|---------|-----------|
| `annotation/gold_set_v2_<anotador>.xlsx` | Libro por anotador: 8 ejes (1-5) + `clase_dominante` (dropdown, OBLIGATORIA) |
| `annotation/gold_set_v2.jsonl` | Todos los artículos muestreados (texto + meta) |
| `annotation/gold_set_v2_ids.json` | IDs gold — usada por `prepare_splits.py` |
| `annotation/gold_set_v2_assignment.json` | Qué IDs son de solape y cuáles exclusivos de cada uno |

## Flujo de anotación (anteproyecto: doble anotación INDEPENDIENTE)

1. Cada anotador sube SU libro a Google Drive y anota **sin ver el del otro**
   (el α solo es válido si la anotación del solape es independiente).
2. Al terminar ambos: `File → Download → .xlsx` y reemplazar los locales.
3. Ingesta + concordancia:
   ```bash
   python scripts/ingest_gold.py --books annotation/gold_set_v2_kevin.xlsx \
       annotation/gold_set_v2_juan.xlsx --audit-silver data/silver/silver_set.jsonl
   ```
   Calcula **Krippendorff α** (umbral del anteproyecto: ≥ 0.8), audita el
   silver contra el consenso humano, y deja las discrepancias en
   `annotation/gold_set_v2_discrepancias.csv`.
4. Sesión de consenso: llenar `label_final` en el CSV y re-correr con
   `--consensus annotation/gold_set_v2_discrepancias.csv`.
5. Salida final: `annotation/gold_set_v2_labeled.jsonl` (etiquetas humanas,
   `label_source: human*`) → entra a `prepare_splits.py`.

Si α < 0.8: iterar el codebook (eliminar ambigüedades) y re-anotar el solape,
como define el anteproyecto.

## Escala humana

Enteros 1-5 por eje (intensidad — dato secundario para análisis) + clase
dominante categórica (la etiqueta de entrenamiento/evaluación).

```
1 (Ausente) → 0.00     3 (Moderado)  → 0.50     5 (Dominante) → 1.00
2 (Leve)    → 0.25     4 (Marcado)   → 0.75
```

## Componentes

- [scripts/prepare_gold_set.py](../scripts/prepare_gold_set.py) — muestreo + libros Excel
- [scripts/ingest_gold.py](../scripts/ingest_gold.py) — ingesta + α + consenso
- [src/agents/gold/agreement.py](../src/agents/gold/agreement.py) — Krippendorff α (nominal/interval)
