"""Pesos por clase para la Cross-Entropy, a partir de la distribución de train.

El silver está desbalanceado por naturaleza del corpus (doctrinarismo es
~0,25 % de la prensa política; progresismo, decenas de veces más). Con la
pérdida sin ponderar, el gradiente lo dominan las clases grandes y el F1
macro —la métrica del OE3, que pesa igual las ocho— se hunde en las chicas.

Modos:
- "inverse":       w_c = N / (C · n_c). Iguala la contribución de cada clase.
                   Con desbalances de 20:1 puede volver inestable el
                   entrenamiento y sobrepredecir la clase rara.
- "sqrt_inverse":  la raíz de lo anterior. Compromiso habitual: corrige el
                   grueso del sesgo sin multiplicar por 20 el ruido de las
                   etiquetas de la clase más escasa.

Los pesos se normalizan a media 1 para que la escala de la pérdida (y por
tanto el learning rate efectivo) no cambie al activarlos.
"""

from __future__ import annotations

import math

MODES = ("inverse", "sqrt_inverse")


def class_weights(counts: list[int], mode: str) -> list[float]:
    """Pesos de media 1 para `F.cross_entropy(weight=...)`.

    Una clase sin ejemplos en train recibe peso 0: no hay gradiente que
    ponderar, y un peso infinito rompería la pérdida.
    """
    if mode not in MODES:
        raise ValueError(f"modo desconocido: {mode!r}. Opciones: {MODES}")
    total = sum(counts)
    presentes = [c for c in counts if c > 0]
    if not presentes:
        raise ValueError("train no tiene ninguna etiqueta")
    k = len(presentes)
    crudos = []
    for n in counts:
        if n == 0:
            crudos.append(0.0)
            continue
        w = total / (k * n)
        crudos.append(math.sqrt(w) if mode == "sqrt_inverse" else w)
    media = sum(crudos) / k
    return [round(w / media, 4) for w in crudos]
