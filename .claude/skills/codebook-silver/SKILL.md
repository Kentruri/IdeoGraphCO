---
name: codebook-silver
description: Codebook para asignar la clase ideológica DOMINANTE a un artículo de prensa política colombiana (una de ocho: populismo, institucionalismo, personalismo, doctrinarismo, soberanismo, globalismo, conservadurismo, progresismo). Úsalo al etiquetar lotes del silver set de IdeoGraphCO, al juzgar qué encuadre estructura un texto, o cuando haya que decidir entre dos clases que parecen aplicar. Incluye los cuatro ejes, el criterio de dominancia y el formato de las decisiones.
---

# Codebook del silver — clase ideológica dominante

Asignas a cada artículo **una** de ocho clases: la que **estructura el
argumento del texto**, no la que se menciona de pasada. Es single-label: las
ocho son mutuamente excluyentes y el modelo aprende una distribución que suma
1,0.

Estos artículos ya pasaron el filtro de politicidad: **asume que el texto es
política colombiana**. Tu trabajo no es decidir si entra, sino con qué
encuadre.

## 1. Carga el criterio canónico

El codebook completo —definiciones, marcadores lingüísticos y reglas de
calibración— vive en un solo sitio. Léelo antes de etiquetar:

```bash
.venv/bin/python -c "from src.agents.silver.codebook import build_system_prompt; print(build_system_prompt(include_examples=True))"
```

Si el proyecto tiene un codebook propio del anotador humano, se pasa con
`--codebook` y **ese manda**: el silver debe aplicar el mismo criterio que el
gold, o las etiquetas no son comparables.

No trabajes de memoria: si tu criterio y el archivo divergen, el silver deja
de ser homogéneo y la auditoría de concordancia pierde sentido.

## 2. Las ocho clases, en cuatro ejes opuestos

| Eje | Par | Qué lo distingue |
|---|---|---|
| Gobernanza y discurso | `populismo` ↔ `institucionalismo` | dicotomía pueblo/élite vs. compromiso con procesos y pluralismo |
| Liderazgo político | `personalismo` ↔ `doctrinarismo` | el líder como eje vs. el cuerpo ideológico como autoridad |
| Política exterior | `soberanismo` ↔ `globalismo` | autonomía nacional, anti-injerencia vs. multilateralismo |
| Sociocultural | `conservadurismo` ↔ `progresismo` | tradición, orden, autoridad vs. derechos, diversidad, reforma |

Anclados en el **V-Party Dataset de V-Dem**. Los pares son opuestos: un texto
fuertemente populista rara vez es también institucionalista.

## 3. El criterio de dominancia

La pregunta operativa, en este orden:

1. **¿Qué organiza el argumento?** No qué temas toca, sino qué lógica sostiene
   la pieza de principio a fin.
2. **¿Qué se pierde si le quitas ese encuadre?** Si el texto sigue en pie, no
   era el dominante.
3. **El titular y el primer tercio pesan más.** Es donde el texto declara su
   marco; el resto suele desarrollarlo.

Casos que confunden:

- **Un texto puede criticar una ideología y ser de esa clase.** Lo que cuenta
  es el encuadre que estructura el argumento, no de qué lado está el autor.
- **Citar a un líder no es personalismo.** Lo es cuando el líder *sustituye* a
  la estructura: su voluntad como fuente de legitimidad.
- **Mencionar "el pueblo" no es populismo.** Lo es cuando hay dicotomía
  pueblo virtuoso / élite corrupta como motor del argumento.
- **Una nota de política exterior no es automáticamente soberanismo ni
  globalismo.** Si el eje que la organiza es otro (p. ej. el líder), esa es la
  dominante.

## 4. Cuando dos clases empatan de verdad

Escribe `dud`. No fuerces una.

Esos casos los resuelve otro juez, y además son señal: un `dud` bien puesto
dice más sobre los límites del codebook que una etiqueta inventada. Pero úsalo
con moderación — por encima del ~8 % significa que estás delegando, no
dudando. Si te inclinas hacia un lado, decide y **baja la confianza**: para
eso está.

## 5. Formato de salida

Una línea por artículo, en el orden del lote:

```
n  clase  [confianza]
```

- `n` — el número entre corchetes del lote
- `clase` — una de las ocho, o `dud`. Abreviaturas admitidas:
  `pop` `inst` `pers` `doc` `sob` `glob` `cons` `prog`
- `confianza` — opcional, 0.0-1.0 (por defecto 0.8). Es tu certeza en **esta
  clase frente a las otras siete**, no lo interesante que sea el artículo
- todo lo que siga a `#` es comentario

```
1  populismo 0.9
2  inst 0.7          # institucionalismo, pero con retórica de líder
3  dud               # empate real entre personalismo y populismo
4  prog 0.85
```

Escribe **una línea por cada artículo del lote**, sin saltarte ninguno.

## 6. Errores que arruinan el silver

- **Etiquetar por el tema.** Una nota sobre pensiones puede ser
  conservadurismo, progresismo o institucionalismo según cómo la enmarque.
- **Etiquetar por la fuente.** No la ves, y es a propósito.
- **Usar `dud` para no pensar.** Es para el empate real.
- **Confianza inflada.** Un 0.9 en un caso límite envenena la calibración:
  es justo el número con el que después se decide qué etiquetas fiar.
