"""Codebook político — define los 8 ejes ideológicos y sus criterios de evaluación.

El LLM-as-a-Judge (silver) califica cada eje DIRECTAMENTE en [0.0, 1.0]
como un score continuo. Los 5 niveles del codebook (Ausente, Leve,
Moderado, Marcado, Dominante) son SOLO referencias semánticas
aproximadas para que el modelo entienda el rango — no son anclajes
obligatorios. El LLM puede dar 0.02, 0.42, 0.83 o cualquier valor.

Referencias aproximadas (no obligatorias):
    0.00 ≈ Ausente      0.50 ≈ Moderado     1.00 ≈ Dominante
    0.25 ≈ Leve         0.75 ≈ Marcado

El gold humano (Excel) sigue siendo entero 1-5 porque los humanos no
dan decimales consistentes. Para comparar silver vs gold:
    humano 1 → 0.00 | 2 → 0.25 | 3 → 0.50 | 4 → 0.75 | 5 → 1.00
    silver: continuo en [0, 1] (ya está en la misma escala)
Ambos comparables con MAE/MSE/R² en [0, 1].
"""

# ---------------------------------------------------------------------------
# Nombres semánticos de los 5 niveles (alineados con la bitácora PDF)
# ---------------------------------------------------------------------------

SCALE_LEVELS: dict[str, str] = {
    "1": "Ausente",
    "2": "Leve",
    "3": "Moderado",
    "4": "Marcado",
    "5": "Dominante",
}

# ---------------------------------------------------------------------------
# Definiciones operacionales de los 8 ejes
# ---------------------------------------------------------------------------

AXIS_DEFINITIONS: dict[str, dict] = {
    "personalismo": {
        "definition": (
            "Grado en que el texto enfatiza a un líder individual (su carisma, voluntad, decisiones o figura) como eje central de la política, por encima de partidos o instituciones"
        ),
        "markers": [
            "Deícticos de primera persona (yo decidí, mi gobierno, lo logró, visión de, el presidente ordenó, su pueblo)",
            "Nombre del líder como sujeto reiterado de la acción política",
            "Retórica carismática, emocional y directa",
            "Promesas personales o lenguaje de lealtad (yo les prometo, conmigo va a cambiar)",
            "Culto a la personalidad o heroización del líder",
            "Ausencia de referencias a procesos institucionales",
        ],
        "scale": {
            "1": "No hay referencia a figuras individuales. Texto puramente institucional",
            "2": "Se menciona un líder de forma ocasional pero como parte de un proceso institucional sin centralidad como referente necesario",
            "3": "El líder es un actor relevante y se mencionan algunas de sus características, pero no monopoliza la narrativa",
            "4": "La personalidad del líder y sus atributos (carisma, trayectoria, autenticidad) estructuran buena parte del argumento",
            "5": "El texto depende casi por completo de la figura del líder, exaltando sus virtudes y presentándolo como motor único de la acción política, sin mediación institucional",
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
            "Grado en que el texto enfatiza las instituciones, procesos legales formales y el Estado de derecho como ejes de la acción política. La legitimidad se ancla en normas, procedimientos y organismos formales, no en voluntades individuales"
        ),
        "markers": [
            "Léxico jurídico (mediante decreto, conforme a la ley, artículo 230)",
            "Referencias a entidades del Estado (Congreso, Corte Constitucional, Procuraduría, JEP, Fiscalia, DIAN, etc) como actores centrales",
            "Descripción de procesos formales (trámite legislativo, ponencia, debate)",
            "Formalidad burocrática y neutralidad en el tono",
            "Citación de normas, sentencias, resoluciones",
            "Actores institucionales como sujeto (la Corte determinó, el Congreso aprobó)",
            "Se valora explícitamente la separación de poderes, el debido proceso o la independencia de órganos de control",
            "Se critica o alaba a actores por respetar o vulnerar reglas institucionales",
        ],
        "scale": {
            "1": "No hay referencias a instituciones, leyes ni procedimientos formales; se ignoran o desestiman esos canales",
            "2": "Las instituciones aparecen como SUJETOS gramaticales de la acción (ej. 'el Congreso aprobó', 'la Corte determinó') sin que el texto argumente sobre la importancia del procedimiento. La narrativa es informativa, no valorativa",
            "3": "El texto valora positivamente algún proceso formal o respalda un fallo, pero esto se equilibra con otros marcos (pelea entre líderes, posturas ideológicas, etc.). Tono mixto, no puramente burocrático",
            "4": "El texto argumenta repetidamente que la validez de una decisión política depende de que se haya seguido el procedimiento. Tono predominantemente burocrático y neutral; si hay polémica, el foco está en si se respetaron las reglas, no en las personas",
            "5": "El texto defiende activamente el debido proceso como valor supremo. Hay condena explícita de vías de hecho, decretos por fuera del trámite legislativo, o saltos de la legalidad. La voluntad política individual se subordina al marco institucional",
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
            "Grado en que el texto usa retórica que divide a la sociedad en (pueblo puro/virtuoso) versus (élite corrupta), apelando directamente a la voluntad popular contra las instituciones tradicionales"
        ),
        "markers": [
            "Dicotomía explícita pueblo vs. élite (los de arriba, los de siempre, la oligarquía, el pueblo)",
            "Lenguaje anti-establecimiento y deslegitimación de instituciones existentes",
            "Apelación emocional directa a las masas",
            "Simplificación de problemas complejos en buenos vs malos",
            "Demonización de adversarios políticos",
            "Uso de (nosotros) inclusivo contra (ellos) corrupto/privilegiado",
            "Se apela a la (voluntad popular) o (el mandato del pueblo) para justificar acciones",
            "Se invocan emociones de agravio, injusticia histórica o reivindicación colectiva",
        ],
        "scale": {
            "1": "Texto técnico, neutral o diplomatico, sin apelación emocional ni dicotomías. No se detecta la división pueblo-élite; los actores se presentan sin esa carga antagónica",
            "2": "Alguna referencia a desigualdad pero sin antagonismo explícito",
            "3": "La narrativa establece tensión entre sectores populares y élites, pero de forma descriptiva más que movilizadora",
            "4": "El texto articula explícitamente la división pueblo/élite y la usa como marco interpretativo central",
            "5": "Todo el mensaje se articula en torno a esa oposición; el pueblo es exaltado como la única fuente de virtud y la élite es demonizada como responsable de todos los males, con alta simplificación y afectividad",
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
            "Grado en que el texto presenta posiciones políticas como derivadas de un cuerpo ideológico rígido y cerrado (de cualquier signo), al que se apela como autoridad o guía, mostrando resistencia a la adaptación pragmática o al diálogo con posturas distintas"
        ),
        "markers": [
            "Uso frecuente de palabras (-ismos) (socialismo, neoliberalismo, marxismo, uribismo)",
            "Citas a teóricos, manifiestos o doctrinas políticas",
            "Se invocan principios o textos doctrinarios (constitucionales, religiosos, marxistas, libertarios, etc.) como argumento de autoridad inapelable",
            "Abstracción ideológica elevada, alejada de lo concreto",
            "Dogmatismo: rechazo absoluto de posiciones intermedias",
            "Marco teórico como lente único para interpretar la realidad",
            "Lenguaje prescriptivo basado en doctrina (según la teoría de...)",
            "El lenguaje es categórico, sin matices: (siempre, nunca, es imposible que, la única vía es)",
        ],
        "scale": {
            "1": "No hay presencia de doctrinas rígidas; el texto es pragmático o acepta matices",
            "2": "Alguna referencia a principios ideológicos, pero sin presentarlos como inapelables o excluyentes sino de forma pragmatica",
            "3": "Se advierten referencias recurrentes a un ideario definido, pero se admiten otros enfoques",
            "4": "El texto articula sus argumentos principalmente desde una posición ideológica rígida y descalifica posturas alternativas",
            "5": "El texto es un manifiesto doctrinal puro; todo se subordina a la pureza ideológica y cualquier concesión es tratada como traición; lenguaje categórico (principios innegociables, traición a los fundamentos)",
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
            "Grado en que el texto prioriza la autonomía, la integridad territorial y la autodeterminación de Colombia frente a actores externos (organismos internacionales, potencias extranjeras, empresas transnacionales, migrantes), presentando la soberanía nacional como valor político supremo"
        ),
        "markers": [
            "Defensa de fronteras y soberanía territorial",
            "Proteccionismo económico (producción nacional, industria local)",
            "Rechazo a injerencia extranjera (no nos van a imponer)",
            "Nacionalismo y orgullo patrio",
            "Enfasis en recursos naturales propios y su control",
            "Se apela a identidad nacional, recursos naturales propios o fronteras como bienes a defender",
            "Rechazo a injerencia externa en el contexto colombiano: en la izquierda -> proteccionismo agrario, crítica a la política antidrogas de EE.UU. y a los TLCs; en la derecha -> defensa territorial en San Andrés y rechazo a organismos como la ONU o la CIDH frente al orden público",
        ],
        "scale": {
            "1": "No hay alusiones a la soberanía ni a injerencia externa; la interacción internacional se presenta como cooperación natural",
            "2": "Mención puntual a soberanía o actores externos, sin que articule el argumento principal del texto",
            "3": "Se expresan varias inquietudes sobre presiones externas o se defiende la capacidad de decidir, sin ser el tema central",
            "4": "La protección de la soberanía y la crítica a intervenciones foráneas son parte central del discurso; lenguaje cargado de (defensa nacional)",
            "5": "El texto se estructura como una defensa frontal de la soberanía, denunciando amenazas externas (embajadas, ONG, organismos multilaterales) y exigiendo decisiones sin ataduras foráneas",
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
            "Grado en que el texto valora la cooperación internacional, la adhesión a normas globales y la interdependencia como herramientas para abordar problemas políticos"
        ),
        "markers": [
            "Mención de organismos internacionales (ONU, OCDE, FMI, BID, OMS)",
            "Tratados de libre comercio y apertura económica",
            "Cooperación internacional y ayuda multilateral",
            "Estándares y normativas globales",
            "Inversión extranjera como valor positivo",
            "Integración regional (CAN, Alianza del Pacífico, Mercosur)",
            "Se compara la situación colombiana con tendencias o normas de otros países o regiones",
            "Se apela a compromisos de Colombia ante la comunidad internacional",
        ],
        "scale": {
            "1": "No hay mención de organismos internacionales, normas globales ni cooperación; el enfoque es puramente doméstico",
            "2": "Mención incidental a contexto internacional, sin que sea argumento ni eje narrativo",
            "3": "Las referencias a la comunidad internacional o a tratados complementan el análisis, pero no son el eje",
            "4": "La cooperación internacional, los estándares multilaterales o las alianzas globales son un pilar repetido del discurso",
            "5": "Todo el mensaje está basado en la necesidad de alinearse a la comunidad internacional, cumplir tratados y recurrir a mecanismos globales; se usan expresiones como (compromiso internacional, estándares globales, responsabilidad compartida) y se descalifica el aislacionismo",
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
            "Grado en que el texto enfatiza valores tradicionales, orden social, seguridad, mano dura, propiedad privada, familia tradicional, religion, gradualismo y escepticismo ante cambios rápidos (especialmente en paz, tierras, drogas)"
        ),
        "markers": [
            "Defensa de la propiedad privada y libre mercado",
            "Valores familiares tradicionales",
            "Religiosidad y moral cristiana como fundamento social",
            "Autoridad, orden, seguridad y mano dura",
            "Resistencia al cambio social (así siempre ha sido, tradiciones)",
            "Defensa del estatus quo y estabilidad institucional",
            "Se defiende el orden público, la autoridad estatal o el control del crimen como prioridades políticas",
            "Conservadurismo colombiano apoyado en tres pilares: ortodoxia institucional/económica (propiedad privada, libre empresa), exigencia de orden y autoridad (mano dura frente al crimen o la protesta, respaldo irrestricto a la Fuerza Pública), y moral tradicional/religiosa (familia clásica como núcleo de la sociedad)",
            "Se asocian posiciones progresistas o reformistas con riesgo, caos o pérdida de valores",
        ],
        "scale": {
            "1": "No hay apelación a la tradición, al orden ni a la autoridad; el texto puede ser neutral o proclive al cambio",
            "2": "Alguna referencia al orden o valores conservadores, pero sin que articule el enfoque del artículo",
            "3": "Aparecen varias referencias a la estabilidad, la moral tradicional o la fuerza pública como elementos relevantes, pero no lo son todo",
            "4": "La defensa de la familia, la fe, el orden público y la autoridad es un tema central y constante; el cambio se califica como amenaza",
            "5": "Texto saturado de retórica de mano dura, valores tradicionales y rechazo al cambio social",
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
            "Grado en que el texto impulsa transformaciones del statu quo en favor de mayor igualdad, justicia social, derechos de grupos históricamente marginados (mujeres, comunidades étnicas, LGBTQ+, víctimas del conflicto, campesinado) o protección ambiental, usando estas causas como marco de legitimación política"
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
            "Se visibilizan voces o demandas de grupos marginados como sujetos políticos",
            "Se identifican estructuras o sistemas como fuente de desigualdad a transformar (sistema de salud, modelo agrario, etc)",
            "Se critica el statu quo como reproductor de inequidad y se proponen cambios estructurales",
        ],
        "scale": {
            "1": "No hay reivindicaciones de cambio social, igualdad o derechos; el texto es neutro o conservador",
            "2": "Mención a temas sociales o grupos vulnerables, sin que sea el argumento central del texto",
            "3": "El texto incluye varias menciones a justicia social, inclusión o reforma, combinadas con otros temas",
            "4": "La narrativa está orientada explícitamente a transformar inequidades; los derechos o la justicia social son ejes centrales.",
            "5": "Todo el texto es una proclama de transformación radical, exigiendo cambios estructurales y reivindicando derechos de grupos oprimidos",
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
    "Los ejes conceptualmente opuestos (Populismo vs. Institucionalismo; Personalismo "
    "vs. Doctrinarismo; Soberanismo vs. Globalismo; Conservadurismo vs. Progresismo) "
    "NO son mutuamente excluyentes. Un texto puede tener scores altos en ambos si "
    "expone con fuerza ambas posturas (por ejemplo, un debate donde chocan dos "
    "visiones, o un decreto justificado con retórica caudillista).",
    # 4. Medición de intensidad, no de postura
    "Los scores miden la INTENSIDAD RETÓRICA del marcador en el texto, no si el "
    "artículo está a favor o en contra de dicha postura. Si un texto critica "
    "fuertemente el populismo describiendo sus tácticas, el texto contiene lenguaje "
    "populista y debe puntuar en ese eje.",
    # 5. SUJETO GRAMATICAL ≠ CENTRALIDAD DEL EJE (aplica a TODOS los ejes)
    "Que una entidad aparezca como sujeto gramatical (ej. 'el Congreso aprobó', "
    "'el presidente decidió', 'el pueblo rechazó', 'el FMI recomienda') NO implica "
    "score alto en su eje. El score alto requiere que el texto ARGUMENTE desde ese "
    "marco, no solo que lo mencione descriptivamente. Una noticia que reporta "
    "'la Corte declaró inexequible X' es informativa (score bajo en institucionalismo), "
    "no institucionalista. Para que sea institucionalismo alto, el texto debe defender "
    "que la Corte HIZO BIEN en seguir el procedimiento, o condenar a quienes "
    "intentaron saltárselo. Lo mismo para personalismo, populismo, globalismo, etc.: "
    "exaltación o defensa explícita > mención como sujeto.",
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
# Regla de la clase DOMINANTE (anteproyecto: clasificación categórica)
# ---------------------------------------------------------------------------
# La metodología aprobada (Fase 1, Etiquetado Asistido) exige asignar "la
# clasificación categórica de la ideología política predominante a cada
# artículo". Los 8 scores de intensidad se conservan como señal secundaria
# (auditoría, análisis), pero la etiqueta de entrenamiento es la dominante.

DOMINANT_RULES: str = """\
Además de los 8 scores de intensidad, DEBES elegir exactamente UNA clase
dominante: la ideología cuyo encuadre ESTRUCTURA el argumento del texto (el
marco desde el que está narrada la noticia), no necesariamente la que más
menciones tiene.

Criterios de desempate (en orden):
1. ¿Qué marco organiza el titular y el primer tercio del texto?
2. ¿Qué retórica usa el texto en su propia voz (no en citas de terceros)?
3. Si dos marcos empatan genuinamente, elige el que motivaría el titular.

La dominante debe ser una de las 8 clases exactas (en minúsculas):
personalismo, institucionalismo, populismo, doctrinarismo, soberanismo,
globalismo, conservadurismo, progresismo."""


# ---------------------------------------------------------------------------
# Construcción del system prompt
# ---------------------------------------------------------------------------


def build_system_prompt(
    include_examples: bool = False,
    with_dominant: bool = True,
) -> str:
    """Construye el system prompt para el LLM-as-a-Judge.

    Args:
        include_examples: Si True, incluye los ejemplos de calibración
            (requiere que los [TBD] estén completados).
        with_dominant: Si True (default, requerido por el anteproyecto),
            el juez además elige la clase categórica dominante.
    """
    axes_section = ""
    for name, axis in AXIS_DEFINITIONS.items():
        axes_section += f"\n### {name.upper()}\n"
        axes_section += f"**Definición:** {axis['definition']}\n\n"

        axes_section += "**Marcadores lingüísticos:**\n"
        for marker in axis["markers"]:
            if not marker.startswith("[TBD"):
                axes_section += f"- {marker}\n"

        # Referencias semánticas en [0, 1]. Los niveles 1-5 del codebook
        # se muestran como aproximaciones: el LLM puede dar cualquier
        # valor continuo, no solo los anclajes.
        _LEVEL_TO_UNIT_REF = {"1": "0.00", "2": "0.25", "3": "0.50", "4": "0.75", "5": "1.00"}
        axes_section += "\n**Referencias semánticas (no anclajes obligatorios):**\n"
        for range_key, description in axis["scale"].items():
            level_name = SCALE_LEVELS.get(range_key, "")
            ref_unit = _LEVEL_TO_UNIT_REF.get(range_key, "")
            axes_section += f"- **≈ {ref_unit} ({level_name}):** {description}\n"

        if include_examples and not axis["examples_high"].startswith("[TBD"):
            axes_section += f"\n**Ejemplo score alto:**\n> {axis['examples_high']}\n"
            axes_section += f"\n**Ejemplo score bajo:**\n> {axis['examples_low']}\n"

    rules_section = ""
    for i, rule in enumerate(CALIBRATION_RULES, 1):
        if not rule.startswith("[TBD"):
            rules_section += f"{i}. {rule}\n"

    dominant_section = ""
    dominant_field = ""
    dominant_task = ""
    if with_dominant:
        dominant_section = f"\n## CLASE DOMINANTE (etiqueta categórica)\n\n{DOMINANT_RULES}\n"
        dominant_field = ',\n    "dominant": "personalismo"'
        dominant_task = (
            " y elegir la clase ideológica DOMINANTE del artículo (una sola, "
            "campo \"dominant\")"
        )

    return f"""Eres un analista político experto en el contexto colombiano. Tu tarea es
evaluar una noticia colombiana POLÍTICA, asignar un puntaje de intensidad
ideológica en 8 dimensiones{dominant_task}. Las noticias no-políticas ya fueron
descartadas aguas arriba por el filter LLM, así que asume que el texto SIEMPRE
es político.

Devuelve un JSON con 8 campos numéricos (uno por eje) DIRECTAMENTE EN [0.0, 1.0].
Usa cualquier valor en el rango (0.02, 0.34, 0.71, etc.); no te limites a
valores "redondos". Refleja con precisión los matices que percibes en el texto.

Los 5 niveles del codebook son SOLO referencias semánticas aproximadas, NO
anclajes obligatorios:
    0.00 ≈ Ausente     0.50 ≈ Moderado     1.00 ≈ Dominante
    0.25 ≈ Leve        0.75 ≈ Marcado

## EJES IDEOLÓGICOS
{axes_section}

## REGLAS DE CALIBRACIÓN
{rules_section}{dominant_section}

## FORMATO DE RESPUESTA (solo JSON, nada más)

{{{{
    "personalismo": 0.78,
    "institucionalismo": 0.23,
    "populismo": 0.61,
    "doctrinarismo": 0.04,
    "soberanismo": 0.12,
    "globalismo": 0.03,
    "conservadurismo": 0.42,
    "progresismo": 0.31{dominant_field}
}}}}"""
