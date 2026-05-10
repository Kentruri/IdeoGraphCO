"""Codebook político — define los 8 ejes ideológicos y sus criterios de evaluación.

Este codebook se inyecta como system prompt al LLM-as-a-Judge para que
califique cada noticia de 0 a 100 en cada eje de forma consistente.

Las secciones marcadas con [TBD] requieren definición por parte del
investigador basándose en su conocimiento de ciencia política colombiana.
"""

# ---------------------------------------------------------------------------
# Definiciones operacionales de los 8 ejes
# ---------------------------------------------------------------------------

AXIS_DEFINITIONS: dict[str, dict] = {
    "personalismo": {
        "definition": (
            "Grado en que el texto se centra en figuras individuales como motor de la "
            "acción política, por encima de las instituciones o procesos colectivos."
        ),
        "markers": [
            "Deícticos de primera persona ('yo decidí', 'mi gobierno', 'lo logré')",
            "Nombre del líder como sujeto reiterado de la acción política",
            "Retórica carismática, emocional y directa",
            "Promesas personales ('yo les prometo', 'conmigo va a cambiar')",
            "Culto a la personalidad o heroización del líder",
            "Ausencia de referencias a procesos institucionales",
        ],
        "scale": {
            "0-10": "No hay referencia a figuras individuales. Texto puramente institucional.",
            "20-40": "Se menciona un líder pero como parte de un proceso institucional.",
            "50-60": "El líder es protagonista pero dentro de un marco institucional.",
            "70-85": "El texto gira alrededor de una persona. Las instituciones son secundarias.",
            "90-100": "Discurso completamente centrado en una sola figura. Todo depende de ella.",
        },
        "examples_high": (
            "El mandatario asumió todo el crédito por los avances del proyecto, "
            "asegurando desde la tarima: 'Fui yo quien tomó la decisión valiente de "
            "enfrentar a las mafias cuando nadie más quería hacerlo. Mi gobierno ha "
            "logrado lo que no se hizo en 20 años'. Durante su discurso, la figura "
            "del dirigente opacó por completo el trámite legislativo, presentándose "
            "como el salvador indispensable del proceso."
        ),
        "examples_low": (
            "El Ministerio de Hacienda expidió la Resolución 0450, mediante la cual "
            "se reglamentan las nuevas tarifas de retención. El documento técnico fue "
            "producto de varias mesas de diálogo interinstitucional y su implementación "
            "estará a cargo de las direcciones regionales de la DIAN durante el "
            "próximo trimestre."
        ),
    },
    "institucionalismo": {
        "definition": (
            "Grado en que el texto enfatiza las instituciones, procesos legales y el "
            "Estado de derecho como ejes de la acción política."
        ),
        "markers": [
            "Léxico jurídico ('mediante decreto', 'conforme a la ley', 'artículo 230')",
            "Referencias a entidades del Estado (Congreso, Corte Constitucional, Procuraduría)",
            "Descripción de procesos formales (trámite legislativo, ponencia, debate)",
            "Formalidad burocrática y neutralidad en el tono",
            "Citación de normas, sentencias, resoluciones",
            "Actores institucionales como sujeto ('la Corte determinó', 'el Congreso aprobó')",
        ],
        "scale": {
            "0-10": "No hay lenguaje institucional. Texto puramente personal/emocional.",
            "20-40": "Menciones pasajeras a instituciones sin profundidad.",
            "50-60": "Balance entre actores institucionales y personales.",
            "70-85": "Predomina el lenguaje jurídico y los procesos formales.",
            "90-100": "Texto puramente institucional. Ej: boletín de Función Pública describiendo un decreto.",
        },
        "examples_high": (
            "La Sala Plena de la Corte Constitucional declaró inexequible el artículo 4 "
            "de la reforma, tras concluir que durante el trámite legislativo en el "
            "Congreso de la República se vulneró el principio de consecutividad. En su "
            "providencia, el alto tribunal exhortó al Ejecutivo a expedir una nueva "
            "reglamentación ceñida a los parámetros legales vigentes."
        ),
        "examples_low": (
            "¡Aquí no vinimos a pedir permiso, vinimos a hacer historia! Yo les "
            "garantizo que las cosas se van a hacer a mi manera, porque es lo que "
            "el pueblo en las calles me está exigiendo. No me importan las trabas "
            "que nos pongan los mismos de siempre, mi voluntad es cumplirles hoy mismo."
        ),
    },
    "populismo": {
        "definition": (
            "Grado en que el texto construye una dicotomía entre 'el pueblo' y 'la élite', "
            "usando retórica anti-establishment."
        ),
        "markers": [
            "Dicotomía explícita pueblo vs. élite ('los de arriba', 'la oligarquía', 'el pueblo')",
            "Lenguaje anti-establishment y deslegitimación de instituciones existentes",
            "Apelación emocional directa a las masas",
            "Simplificación de problemas complejos en buenos vs. malos",
            "Demonización de adversarios políticos",
            "Uso de 'nosotros' inclusivo contra 'ellos' corrupto/privilegiado",
        ],
        "scale": {
            "0-10": "Texto técnico, sin apelación emocional ni dicotomías.",
            "20-40": "Alguna referencia a desigualdad pero sin antagonismo explícito.",
            "50-60": "Claro 'nosotros vs. ellos' pero con matices.",
            "70-85": "Fuerte retórica anti-élite. Antagonismo como eje central.",
            "90-100": "Discurso plenamente populista. El pueblo virtuoso contra la élite corrupta.",
        },
        "examples_high": (
            "Este no es el proyecto de las oligarquías que por décadas se han "
            "robado y repartido el país a sus espaldas. Este es el mandato del "
            "pueblo, de las familias trabajadoras y de 'los nadies' que hoy se "
            "levantan contra una élite corrupta, privilegiada y excluyente que "
            "solo ha legislado para sus propios bolsillos desde sus clubes privados."
        ),
        "examples_low": (
            "El informe del Departamento Administrativo Nacional de Estadística "
            "(DANE) señaló una contracción del 1.2% en la demanda interna. Los "
            "analistas del sector financiero explicaron que este fenómeno responde "
            "a ajustes macroeconómicos y a la estabilización de las tasas de "
            "interés por parte de la junta directiva del Banco de la República."
        ),
    },
    "doctrinarismo": {
        "definition": (
            "Grado de rigidez teórica e ideológica en el texto. Presencia de marcos "
            "conceptuales cerrados y dogmáticos."
        ),
        "markers": [
            "Uso frecuente de '-ismos' (socialismo, neoliberalismo, marxismo, uribismo)",
            "Citas a teóricos, manifiestos o doctrinas políticas",
            "Abstracción ideológica elevada, alejada de lo concreto",
            "Dogmatismo: rechazo absoluto de posiciones intermedias",
            "Marco teórico como lente único para interpretar la realidad",
            "Lenguaje prescriptivo basado en doctrina ('según la teoría de...')",
        ],
        "scale": {
            "0-10": "Texto práctico, concreto, sin referencias teóricas.",
            "20-40": "Alguna referencia ideológica pero pragmática.",
            "50-60": "Marco teórico visible pero flexible.",
            "70-85": "Fuerte carga doctrinal. Interpreta todo desde una sola doctrina.",
            "90-100": "Texto puramente doctrinario. Manifiesto ideológico.",
        },
        "examples_high": (
            "La crisis estructural que atravesamos es la consecuencia ineludible "
            "del modelo neoliberal y la acumulación por desposesión del capitalismo "
            "periférico. Siguiendo la teoría de la dependencia, es evidente que "
            "cualquier reformismo tibio está condenado al fracaso; la única vía "
            "histórica es desmantelar la hegemonía burguesa y avanzar hacia una "
            "transición socialista que recupere los medios de producción."
        ),
        "examples_low": (
            "Para mitigar los trancones en la entrada sur de la ciudad, la "
            "Secretaría de Movilidad anunció que habilitará un carril de "
            "contraflujo entre las 5:00 a.m. y las 8:00 a.m. Adicionalmente, "
            "se destinarán 2.000 millones de pesos para tapar los huecos del "
            "corredor principal, con el fin de agilizar la velocidad promedio "
            "de los vehículos de carga y transporte público."
        ),
    },
    "soberanismo": {
        "definition": (
            "Grado en que el texto enfatiza la autonomía nacional, la protección de "
            "intereses propios y el rechazo a la injerencia externa."
        ),
        "markers": [
            "Defensa de fronteras y soberanía territorial",
            "Proteccionismo económico ('producción nacional', 'industria local')",
            "Rechazo a injerencia extranjera ('no nos van a imponer')",
            "Nacionalismo y orgullo patrio",
            "Énfasis en recursos naturales propios y su control",
            (
                "Rechazo a injerencia externa en el contexto colombiano: "
                "en la izquierda → proteccionismo agrario, crítica a la política "
                "antidrogas de EE.UU. y a los TLCs; "
                "en la derecha → defensa territorial en San Andrés y rechazo a "
                "organismos como la ONU o la CIDH frente al orden público"
            ),
        ],
        "scale": {
            "0-10": "No hay referencia a autonomía nacional ni protección.",
            "20-40": "Mención tangencial de intereses nacionales.",
            "50-60": "Defensa moderada de autonomía con apertura a cooperación.",
            "70-85": "Fuerte énfasis en protección nacional. Desconfianza hacia lo externo.",
            "90-100": "Discurso plenamente soberanista. Rechazo total a influencia externa.",
        },
        "examples_high": (
            "No podemos permitir que tribunales internacionales, ONG extranjeras o "
            "potencias nos vengan a dictar cómo manejar nuestro orden interno o la "
            "política antidrogas. La soberanía de Colombia se respeta; las decisiones "
            "sobre nuestro territorio y nuestras leyes las tomamos los colombianos, "
            "sin arrodillarnos ante imposiciones externas."
        ),
        "examples_low": (
            "El Ministerio presentó la nueva hoja de ruta económica, diseñada en "
            "estricta coordinación con las recomendaciones del Fondo Monetario "
            "Internacional y la OCDE. El objetivo es homologar nuestros estándares "
            "normativos para integrarnos plenamente a los mercados globales y "
            "atraer inversión extranjera."
        ),
    },
    "globalismo": {
        "definition": (
            "Grado en que el texto favorece la integración internacional, el "
            "multilateralismo y la cooperación supranacional."
        ),
        "markers": [
            "Mención de organismos internacionales (ONU, OCDE, FMI, BID, OMS)",
            "Tratados de libre comercio y apertura económica",
            "Cooperación internacional y ayuda multilateral",
            "Estándares y normativas globales",
            "Inversión extranjera como valor positivo",
            "Integración regional (CAN, Alianza del Pacífico, Mercosur)",
        ],
        "scale": {
            "0-10": "No hay referencia a lo internacional ni multilateral.",
            "20-40": "Menciones puntuales a organismos internacionales.",
            "50-60": "Balance entre lo nacional y lo internacional.",
            "70-85": "Fuerte énfasis en integración y cooperación global.",
            "90-100": "Discurso plenamente globalista. La solución viene de lo multilateral.",
        },
        "examples_high": (
            "El canciller reiteró que el camino para el desarrollo del país exige "
            "consolidar nuestra participación en la OCDE y fortalecer los lazos "
            "comerciales mediante la Alianza del Pacífico. Además, destacó que la "
            "cooperación técnica del Banco Interamericano de Desarrollo y el "
            "cumplimiento de la agenda climática global de la ONU serán la brújula "
            "para atraer la inversión extranjera que necesitamos."
        ),
        "examples_low": (
            "La Alcaldía anunció que destinará recursos propios para financiar a "
            "las asociaciones de recicladores del municipio. El programa, que busca "
            "formalizar el trabajo de estas cooperativas locales, será operado "
            "directamente por la Secretaría de Inclusión Social y dependerá del "
            "presupuesto aprobado por el Concejo Municipal para el próximo año."
        ),
    },
    "conservadurismo": {
        "definition": (
            "Grado en que el texto defiende el orden social tradicional, la estabilidad "
            "y la resistencia al cambio."
        ),
        "markers": [
            "Defensa de la propiedad privada y libre mercado",
            "Valores familiares tradicionales",
            "Religiosidad y moral cristiana como fundamento social",
            "Autoridad, orden, seguridad y mano dura",
            "Resistencia al cambio social ('así siempre ha sido', 'tradiciones')",
            "Defensa del estatus quo y estabilidad institucional",
            (
                "Conservadurismo colombiano apoyado en tres pilares: "
                "ortodoxia institucional/económica (propiedad privada, libre empresa), "
                "exigencia de orden y autoridad ('mano dura' frente al crimen o la protesta, "
                "respaldo irrestricto a la Fuerza Pública), y "
                "moral tradicional/religiosa (familia clásica como núcleo de la sociedad)"
            ),
        ],
        "scale": {
            "0-10": "No hay referencias a tradición, orden ni valores conservadores.",
            "20-40": "Alguna referencia a estabilidad o tradición sin ser central.",
            "50-60": "Balance entre conservar y reformar.",
            "70-85": "Fuerte defensa del orden tradicional. Cambio visto como amenaza.",
            "90-100": "Discurso plenamente conservador. Tradición como valor supremo.",
        },
        "examples_high": (
            "No vamos a permitir que bajo el pretexto de un falso 'cambio' se "
            "destruyan las instituciones, se premie a los delincuentes y se amenace "
            "la propiedad privada. Aquí lo que se necesita es respaldar a nuestra "
            "Fuerza Pública con firmeza y autoridad para recuperar el orden, "
            "mientras defendemos la familia como núcleo sagrado de la sociedad "
            "frente a ideologías que buscan destruir nuestros valores."
        ),
        "examples_low": (
            "La reforma radicada busca transformar de raíz el modelo vigente "
            "mediante la redistribución equitativa de las tierras improductivas "
            "y la garantía plena de los derechos sexuales y reproductivos. Es "
            "imperativo dejar atrás las estructuras anticuadas que han perpetuado "
            "la desigualdad para construir una sociedad nueva y moderna."
        ),
    },
    "progresismo": {
        "definition": (
            "Grado en que el texto promueve reformas sociales, ampliación de derechos "
            "y transformación del orden existente."
        ),
        "markers": [
            "Derechos de minorías (LGBTQ+, indígenas, afrodescendientes, mujeres)",
            "Justicia climática y medioambiental",
            "Redistribución económica y justicia social",
            "Laicismo y separación iglesia-Estado",
            "Igualdad de género y feminismo",
            "Reforma agraria y acceso a la tierra",
            "Justicia transicional y memoria histórica",
            "Paz como proceso transformador (no solo ausencia de conflicto)",
        ],
        "scale": {
            "0-10": "No hay referencias a reforma social ni ampliación de derechos.",
            "20-40": "Alguna mención de derechos o reformas sin ser el foco.",
            "50-60": "Balance entre reforma y continuidad.",
            "70-85": "Fuerte agenda reformista. Cambio como necesidad urgente.",
            "90-100": "Discurso plenamente progresista. Transformación estructural.",
        },
        "examples_high": (
            "La paz real y duradera es imposible sin una reforma agraria integral "
            "que devuelva la tierra al campesinado y a las comunidades indígenas. "
            "Nuestro imperativo es transformar las estructuras de exclusión "
            "histórica, garantizando los derechos plenos de las mujeres y "
            "diversidades, mientras aceleramos una transición justa para dejar "
            "atrás el modelo económico extractivista que destruye la vida."
        ),
        "examples_low": (
            "El gremio empresarial hizo un llamado urgente a mantener la "
            "estabilidad jurídica y a no modificar la actual legislación laboral. "
            "Los voceros del sector aseguraron que cualquier intento de reforma "
            "estructural en este momento ahuyentará la inversión extranjera y "
            "pondrá en riesgo el libre desarrollo de los mercados, que son el "
            "único motor real para generar riqueza."
        ),
    },
}

# ---------------------------------------------------------------------------
# Reglas de calibración global
# [TBD] items requieren decisión del investigador
# ---------------------------------------------------------------------------

CALIBRATION_RULES: list[str] = [
    # 1. Regla fundamental de evidencia
    "Evalúa SOLO lo que el texto dice explícitamente. No asumas posturas, no infieras "
    "ideologías basadas en tu conocimiento previo del medio de comunicación, del "
    "periodista o del político mencionado.",

    # 2. Independencia total de los 8 ejes
    "Los 8 puntajes son ESTRICTAMENTE INDEPENDIENTES entre sí. No deben sumar 100 ni "
    "interactuar matemáticamente de ninguna forma.",

    # 3. No exclusión de opuestos
    "Los ejes conceptualmente opuestos (Personalismo vs. Institucionalismo; Populismo "
    "vs. Doctrinarismo; Soberanismo vs. Globalismo; Conservadurismo vs. Progresismo) "
    "NO son mutuamente excluyentes. Un texto puede tener scores altos en ambos si "
    "expone con fuerza ambas posturas (por ejemplo, un debate donde chocan dos "
    "visiones, o un decreto justificado con retórica caudillista).",

    # 4. Filtro de politicidad
    "Primero determina si la noticia es de carácter político, de políticas públicas o "
    "impacto estatal (is_political=1). Si NO es política (ej. deportes, farándula, "
    "crónica roja sin implicaciones institucionales), asigna is_political=0 y todos "
    "los ejes estrictamente en 0.",

    # 5. Medición de intensidad, no de postura
    "Los scores miden la INTENSIDAD RETÓRICA del marcador en el texto, no si el "
    "artículo está a favor o en contra de dicha postura. Si un texto critica "
    "fuertemente el populismo describiendo sus tácticas, el texto contiene lenguaje "
    "populista y debe puntuar en ese eje.",

    # 6. Regla del contexto transversal colombiano
    "Ten en cuenta el CONTEXTO COLOMBIANO: Temas como el conflicto armado, el proceso "
    "de paz, la política antidrogas o la restitución de tierras son transversales. Un "
    "solo artículo sobre estos temas puede activar simultáneamente progresismo "
    "(justicia transicional), institucionalismo (fallos de la JEP o cortes), "
    "conservadurismo (exigencia de seguridad y mano dura) y soberanismo (control "
    "territorial). Evalúa la presencia de cada retórica por separado.",

    # 7. Restricción de formato
    "Responde SOLO con un objeto JSON válido, sin usar bloques de código Markdown "
    "(```json ... ```), sin explicaciones, sin preámbulos y sin comentarios adicionales.",
]

# ---------------------------------------------------------------------------
# Construcción del system prompt
# ---------------------------------------------------------------------------


def build_system_prompt(include_examples: bool = False) -> str:
    """Construye el system prompt para el LLM-as-a-Judge.

    Args:
        include_examples: Si True, incluye los ejemplos de calibración
            (requiere que los [TBD] estén completados).
    """
    axes_section = ""
    for name, axis in AXIS_DEFINITIONS.items():
        axes_section += f"\n### {name.upper()}\n"
        axes_section += f"**Definición:** {axis['definition']}\n\n"

        axes_section += "**Marcadores lingüísticos:**\n"
        for marker in axis["markers"]:
            if not marker.startswith("[TBD"):
                axes_section += f"- {marker}\n"

        axes_section += "\n**Escala de calibración:**\n"
        for range_key, description in axis["scale"].items():
            axes_section += f"- **{range_key}:** {description}\n"

        if include_examples and not axis["examples_high"].startswith("[TBD"):
            axes_section += f"\n**Ejemplo score alto:**\n> {axis['examples_high']}\n"
            axes_section += f"\n**Ejemplo score bajo:**\n> {axis['examples_low']}\n"

    rules_section = ""
    for i, rule in enumerate(CALIBRATION_RULES, 1):
        if not rule.startswith("[TBD"):
            rules_section += f"{i}. {rule}\n"

    return f"""Eres un analista político experto en el contexto colombiano. Tu tarea es
evaluar noticias colombianas y asignar un puntaje de intensidad ideológica en 8 dimensiones.

Para cada noticia, devuelve un JSON con:
- "is_political": 1 si es política, 0 si no
- 8 campos numéricos (0-100), uno por cada eje ideológico

## EJES IDEOLÓGICOS
{axes_section}

## REGLAS DE CALIBRACIÓN
{rules_section}

## FORMATO DE RESPUESTA (solo JSON, nada más)

```json
{{{{
    "is_political": 1,
    "personalismo": 0,
    "institucionalismo": 0,
    "populismo": 0,
    "doctrinarismo": 0,
    "soberanismo": 0,
    "globalismo": 0,
    "conservadurismo": 0,
    "progresismo": 0
}}}}
```"""
