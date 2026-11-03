# Codebook — fuente LaTeX

`codebook_v1.1.tex` es la fuente del codebook de anotación (producto P1.2 del OE1).
Está en el repo, y no en un documento ofimático, para que los cambios queden en el
historial de git: la v1.1 es una *iteración del codebook* en el sentido del §1.7, y
el jurado puede pedir ver qué cambió y cuándo.

## Regenerar el PDF

```bash
cd docs/codebook
xelatex codebook_v1.1.tex && xelatex codebook_v1.1.tex   # dos pasadas por el índice
```

Requiere `xelatex` con `booktabs`, `longtable`, `framed`, `babel-spanish` y la fuente
Georgia (presente en macOS). En Windows: MiKTeX instala los paquetes al vuelo.

## Al cambiar el codebook

El §1.1 del propio documento obliga a propagar cualquier cambio a los **dos**
instrumentos que lo usan:

1. este PDF — el que anota a mano,
2. `src/agents/silver/codebook.py` — el que instruye al juez LLM del silver.

Si solo se toca uno, la auditoría de concordancia mide la diferencia entre dos
codebooks en vez de la fidelidad del etiquetado asistido.
