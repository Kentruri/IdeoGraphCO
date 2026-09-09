---
name: codebook-filtro
description: Codebook operacional para decidir si un artículo de prensa colombiana entra al corpus de IdeoGraphCO (politicidad + colombianidad + calidad del texto). Úsalo siempre que haya que clasificar artículos scrapeados en political_article / political_foreign / nonpolitical_article / biography_static / garbage, marcar problemas de limpieza del texto, o resolver si una noticia "cuenta como política". Incluye el protocolo de duda y el formato exacto de las decisiones.
---

# Codebook del filtro — IdeoGraphCO

Decides qué entra al corpus de un clasificador de ideología política
colombiana. Este es el producto **P1.2** del anteproyecto: el criterio que
apliques aquí define la composición del dataset, y con ella lo que el modelo
puede y no puede aprender.

## 1. Carga el criterio canónico

El texto íntegro del codebook vive en **un solo sitio**, para que el agente y
Gemini apliquen exactamente el mismo criterio. Léelo antes de clasificar:

```bash
.venv/bin/python -c "from src.scraper.prompts import FILTER_SYSTEM_PROMPT; print(FILTER_SYSTEM_PROMPT)"
```

No trabajes de memoria ni copies el criterio a otro archivo: si diverge, las
decisiones dejan de ser comparables entre motores y la auditoría de
concordancia pierde sentido.

## 2. Las cinco categorías

| Código | Categoría | Entra al corpus |
|--------|-----------|-----------------|
| `pol` | `political_article` | **SÍ** |
| `for` | `political_foreign` | no — política de terceros países |
| `non` | `nonpolitical_article` | no |
| `bio` | `biography_static` | no — perfiles y páginas institucionales |
| `gar` | `garbage` | no — menús, fragmentos, digests |

## 3. El orden de las preguntas

Hazlas siempre en este orden; la primera que dé un "no" cierra el caso.

1. **¿Es un texto?** ¿O son menús, listas de enlaces, fragmentos sin
   coherencia? → `gar`
2. **¿Es UN texto?** ¿O son varias noticias inconexas en una página? →
   `gar` + `dg`. Rompe el supuesto de una ideología por documento.
3. **¿Está completo?** ¿Se corta a mitad de idea, o es una entradilla con
   invitación a suscribirse? → `gar` + `tr` / `pw`
4. **¿Colombia es el SUJETO?** No basta con que la nombre o que el medio sea
   colombiano. La política exterior *de Colombia* sí entra. → si no, `for`
5. **¿Es un perfil de persona o una página institucional estática?** → `bio`
6. **¿Toca el debate público colombiano?** → `pol` si sí, `non` si no.

## 4. Calibración: permisivo en politicidad, estricto en colombianidad

Los dos ejes NO se tratan igual, y confundirlo es el error más caro.

**Politicidad — sé permisivo.** Ante duda genuina, entra.

- La **opinión política cuenta como política**. Columnas, editoriales,
  análisis, cartas abiertas: son el material más valioso del corpus, porque
  el encuadre ideológico está explícito en vez de implícito. No exijas que
  informen de un hecho noticioso.
- El **debate de política sectorial** cuenta: educación, salud, pensiones,
  trabajo, ambiente, energía, tierras, seguridad. Discutir cómo *debería*
  ser una política pública es política, aunque no se nombre a ningún
  funcionario.
- La **memoria histórica con lectura política** cuenta: crónicas de
  sindicalismo, conflicto armado, partidos, movimientos sociales.
- Un **reclamo de respuesta estatal** cuenta, aunque el registro sea de
  crónica humanitaria.
- Lo **local es igual de político** que lo nacional: un debate del concejo
  de un municipio pequeño vale tanto como uno del Congreso.

Lo que el criterio permisivo **NO** autoriza: deportes, farándula, clima,
crónica roja común, trámites administrativos, notas de empresa privada sin
dimensión regulatoria. Eso no es duda, es un no.

**Colombianidad — sé estricto.** Ante duda, `for`. Las ocho clases
ideológicas están ancladas en actores y discurso de Colombia; un texto sobre
las elecciones de otro país es inetiquetable con ellas, y meterlo al corpus
introduce ruido que ninguna etapa posterior puede quitar.

## 5. Marcas de limpieza (`text_issues`)

Son independientes de la categoría: un artículo político con restos de
plantilla sigue siendo `pol`, más su marca.

| Código | Significado | Efecto |
|--------|-------------|--------|
| `br` | restos de plantilla, menús, pies de foto, titulares relacionados colados | solo se registra — alimenta la mejora de `cleaner.py` |
| `dg` | varias noticias distintas en una página | **descarta** |
| `tr` | texto cortado sin desarrollar | **descarta** |
| `pw` | entradilla + invitación a suscribirse | **descarta** |

Marca `br` con generosidad: es señal gratuita para mejorar el limpiador y no
cuesta ningún artículo.

## 6. Protocolo de duda — `dud`

Cuando estés **genuinamente indeciso**, escribe `dud` en vez de forzar una
categoría. Esos casos los desempata Gemini artículo por artículo al ingerir
el lote.

Usa `dud` con moderación: es para el caso límite real, no para evitar
pronunciarte. Si te inclinas hacia un lado, decide y baja la confianza —
la confianza es justamente donde se registra la vacilación. Una tasa de
`dud` por encima del ~5 % significa que estás delegando, no dudando.

## 7. Formato de salida

Una línea por artículo, en el orden del lote:

```
n  categoría  [confianza]  [marcas]
```

- `n` — el número entre corchetes del lote
- `categoría` — `pol` `for` `non` `bio` `gar` `dud`
- `confianza` — opcional, 0.0-1.0 (por defecto 0.9). Refleja tu certeza en
  la **categoría**, no la relevancia del artículo
- `marcas` — opcional: `br` `dg` `tr` `pw`
- Todo lo que siga a `#` es comentario

```
1  pol 0.95
2  pol 0.70 br        # columna de opinión con restos de plantilla
3  gar 0.90 dg
4  dud                # lo desempata Gemini
5  non 0.85
```

Escribe **una línea por cada artículo del lote**, sin saltarte ninguno.

## 8. Errores que arruinan el corpus

- **Clasificar por la fuente.** Que venga de un ministerio no lo hace
  político; que venga de un medio de farándula no lo hace no-político. Juzga
  el texto que tienes delante.
- **Confundir tema con encuadre.** Aquí no decides la ideología del
  artículo, solo si *entra*. Un texto de derecha y uno de izquierda son
  ambos `pol`.
- **Usar la longitud como criterio.** Un comunicado oficial de dos párrafos
  bien redactados es contenido válido, no basura.
- **Dejar entrar política extranjera** porque el medio es colombiano.
