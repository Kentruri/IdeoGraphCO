"""Verifica candidatos a fuente antes de registrarlos en src/scraper/sources.py.

Prueba cada dominio contra la MISMA pila que usa el scraper (trafilatura + el
User-Agent de src.scraper.config), así que un "include" significa que el
pipeline real va a poder extraer texto, no que la portada respondió 200.

Comprobaciones por candidato:
  1. Vivo tras redirects, con el UA que le corresponde al dominio.
  2. robots.txt: Disallow global y, sobre todo, NEGATIVA EXPLÍCITA AL
     ENTRENAMIENTO DE MODELOS (Content-Signal ai-train=no, o Disallow para
     ClaudeBot/GPTBot/CCBot/Google-Extended/Bytespider/...). Un sitio que
     prohíbe el uso para entrenar queda EXCLUIDO aunque sea scrapeable: es
     una decisión de consentimiento, no técnica.
  3. RSS: solo feeds que devuelven XML válido. Marca los que traen
     content:encoded (full-text: el scraper no necesita visitar el artículo).
  4. Sitemap: desde robots.txt o rutas comunes; cuenta <loc>.
  5. Permalinks: exige URLs propias por artículo. Los sitios que publican la
     prensa en una sola mega-página no sirven.
  6. Cuerpo real: corre trafilatura sobre un artículo de muestra. Es el único
     chequeo que descarta las SPA (Angular/Vue/Next sin SSR), que responden
     200 y no tienen texto en el HTML crudo.

Uso:
    python scripts/verify_sources.py candidatos.json -o verificados.json
    python scripts/verify_sources.py candidatos.json --workers 16 --emit-python
"""

import argparse
import json
import logging
import re
import sys
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urljoin, urlparse

import trafilatura

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.scraper.config import get_user_agent_for  # noqa: E402

logger = logging.getLogger("verify_sources")

TIMEOUT = 20
MIN_BODY_CHARS = 400          # mismo umbral que parser.extract_article
MIN_ARTICLE_URLS = 3          # menos que esto no es un corpus

RSS_PATHS = ["/feed/", "/feed", "/rss", "/rss.xml", "/index.xml", "/atom.xml",
             "/feed/rss", "/?feed=rss2", "/feeds/posts/default"]
SITEMAP_PATHS = ["/sitemap.xml", "/sitemap_index.xml", "/wp-sitemap.xml",
                 "/sitemap-index.xml", "/sitemap/sitemap-index.xml"]

# Crawlers que recolectan CORPUS DE ENTRENAMIENTO. Bloquearlos es una negativa
# al uso que hace este proyecto. No confundir con los agentes de navegacion
# (ChatGPT-User, Claude-Web, Perplexity-User), que buscan por peticion de un
# humano: bloquear esos no dice nada sobre entrenamiento.
TRAIN_BOTS = ["gptbot", "ccbot", "claudebot", "anthropic-ai", "google-extended",
              "bytespider", "amazonbot", "applebot-extended", "perplexitybot",
              "meta-externalagent", "facebookbot", "cohere-ai", "diffbot",
              "omgili", "timpibot", "webzio-extended", "img2dataset"]

# Categorias donde TODO el sitio es politico -> mode "direct", sin filtros.
ALL_POLITICAL = {"institucional", "judicial", "gremial", "opinion"}

# Si el sitio bloquea crawlers de entrenamiento, se excluye salvo --allow-ai-blocked.
RESPECT_AI_OPT_OUT = True

# Secciones que casi nunca aportan senal ideologica.
NOISE_SEGMENTS = {"deportes", "deporte", "futbol", "farandula", "entretenimiento",
                  "gente", "vida", "tecnologia", "salud", "cultura", "horoscopo",
                  "clasificados", "tramites", "directorio", "galeria", "eventos"}


def fetch(url: str, timeout: int = TIMEOUT) -> tuple[int, str, str]:
    """Descarga una URL. Devuelve (status, url_final, cuerpo). status 0 = fallo."""
    req = urllib.request.Request(url, headers={
        "User-Agent": get_user_agent_for(url),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "es-CO,es;q=0.9,en;q=0.8",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read(3_000_000)
            charset = resp.headers.get_content_charset() or "utf-8"
            return resp.status, resp.geturl(), raw.decode(charset, errors="replace")
    except Exception as exc:  # noqa: BLE001 - cualquier fallo de red es "no vivo"
        code = getattr(exc, "code", 0)
        return (code if isinstance(code, int) else 0), url, ""


def check_robots(base: str) -> dict:
    """Lee robots.txt y separa el bloqueo tecnico del rechazo al entrenamiento."""
    status, _, body = fetch(f"{base}/robots.txt", timeout=12)
    out = {"robots_status": status, "disallow_all": False,
           "ai_train_denied": False, "ai_denial_evidence": "", "ai_denial_kind": ""}
    if status != 200 or not body:
        return out

    low = body.lower()

    # Cloudflare inyecta un robots.txt gestionado, con un comentario legal
    # caracteristico y Content-Signal ai-train=no POR DEFECTO. Distinguirlo de
    # un bloqueo escrito a mano importa: el primero es una politica del CDN, el
    # segundo es una decision editorial del medio.
    cdn_default = "if a content-signal = yes, you may collect content" in low

    # Content-Signal (propuesta de Cloudflare): ai-train=no es rechazo al uso.
    if re.search(r"content-signal\s*:.*ai-train\s*=\s*no", low):
        out["ai_train_denied"] = True
        out["ai_denial_evidence"] = "Content-Signal: ai-train=no"
        out["ai_denial_kind"] = "cdn-default" if cdn_default else "explicito"

    # Bloques por user-agent.
    agent, blocked_ai = None, []
    for line in low.splitlines():
        line = line.split("#")[0].strip()
        if line.startswith("user-agent:"):
            agent = line.split(":", 1)[1].strip()
        elif line.startswith("disallow:") and agent is not None:
            path = line.split(":", 1)[1].strip()
            if path == "/":
                if agent == "*":
                    out["disallow_all"] = True
                elif any(bot in agent for bot in TRAIN_BOTS):
                    blocked_ai.append(agent)
    if blocked_ai:
        out["ai_train_denied"] = True
        extra = "Disallow: / para " + ", ".join(sorted(set(blocked_ai))[:6])
        out["ai_denial_evidence"] = (out["ai_denial_evidence"] + "; " + extra).strip("; ")
        # El robots.txt gestionado de Cloudflare ya trae su propia lista de bots
        # con Disallow: /, asi que un bloqueo nominal NO prueba autoria del sitio.
        # Solo es decision editorial si no aparece el boilerplate del CDN.
        if not cdn_default:
            out["ai_denial_kind"] = "explicito"
    return out


def discover_feeds(base: str, html: str) -> tuple[list[str], bool]:
    """Devuelve (feeds verificados, alguno trae content:encoded)."""
    candidates = [urljoin(base + "/", p.lstrip("/")) for p in RSS_PATHS]
    for match in re.finditer(r'<link[^>]+type=["\']application/(?:rss|atom)\+xml["\'][^>]*>', html, re.I):
        href = re.search(r'href=["\']([^"\']+)["\']', match.group(0), re.I)
        if href:
            candidates.insert(0, urljoin(base, href.group(1)))

    feeds, full_text = [], False
    seen = set()
    for url in candidates:
        if url in seen or len(feeds) >= 2:
            continue
        seen.add(url)
        status, final, body = fetch(url, timeout=15)
        head = body[:400].lstrip().lower()
        if status == 200 and ("<?xml" in head or "<rss" in head or "<feed" in head):
            if "<item" in body.lower() or "<entry" in body.lower():
                feeds.append(final)
                if "content:encoded" in body.lower():
                    full_text = True
    return feeds, full_text


def collect_locs(xml: str) -> list[str]:
    return re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", xml, re.I)


def discover_sitemap(base: str) -> tuple[str, list[str]]:
    """Devuelve (url del sitemap, URLs de articulo). Sigue un nivel de indice."""
    urls = []
    status, _, robots = fetch(f"{base}/robots.txt", timeout=12)
    if status == 200:
        urls += [m.strip() for m in re.findall(r"(?im)^\s*sitemap:\s*(\S+)", robots)]
    urls += [urljoin(base + "/", p.lstrip("/")) for p in SITEMAP_PATHS]

    for url in dict.fromkeys(urls):
        status, final, body = fetch(url, timeout=25)
        if status != 200 or "<loc" not in body.lower():
            continue
        locs = collect_locs(body)
        if not locs:
            continue
        if "<sitemapindex" in body[:2000].lower():
            # Es un indice: bajar a los hijos con mas pinta de noticias.
            children = sorted(locs, key=lambda u: (
                0 if re.search(r"post|news|noticia|article|publicacion", u, re.I) else 1))
            deep = []
            for child in children[:3]:
                cstatus, _, cbody = fetch(child, timeout=25)
                if cstatus == 200:
                    deep += collect_locs(cbody)
                if len(deep) > 400:
                    break
            if deep:
                return final, deep
            continue
        return final, locs
    return "", []


def looks_like_article(url: str) -> bool:
    path = urlparse(url).path.strip("/")
    if not path or path.count("/") > 6:
        return False
    last = path.split("/")[-1]
    if any(seg in NOISE_SEGMENTS for seg in path.lower().split("/")):
        return False
    # Un articulo suele tener slug largo con guiones, o terminar en id numerico.
    return ("-" in last and len(last) > 15) or bool(re.fullmatch(r"\d{3,}", last))


def links_from_home(base: str, html: str) -> list[str]:
    out = []
    host = urlparse(base).netloc
    for href in re.findall(r'href=["\']([^"\']+)["\']', html):
        full = urljoin(base, href)
        if urlparse(full).netloc == host and looks_like_article(full):
            out.append(full.split("#")[0])
    return list(dict.fromkeys(out))


def derive_filters(article_urls: list[str]) -> list[str]:
    """Prefijos de seccion que cubren la mayoria de los articulos."""
    segs = Counter()
    for url in article_urls:
        parts = [p for p in urlparse(url).path.split("/") if p]
        if len(parts) >= 2 and not re.fullmatch(r"\d{4}", parts[0]):
            segs[f"/{parts[0]}/"] += 1
    total = sum(segs.values())
    if not total:
        return []
    keep = [s for s, n in segs.most_common(6) if n / total >= 0.08]
    # Si un solo prefijo se lo lleva casi todo, el resto es ruido estadistico.
    return keep if len(keep) <= 5 else keep[:5]


def verify(cand: dict) -> dict:
    url = cand["url"].rstrip("/")
    parsed = urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    res = {**{k: cand.get(k) for k in
              ("key", "name", "url", "domain", "category", "region", "ideological_rationale")},
           "alive": False, "http_status": 0, "has_rss": False, "rss_feeds": [],
           "rss_full_text": False, "has_sitemap": False, "sitemap_url": "",
           "sitemap_locs": 0, "has_permalinks": False, "permalink_example": "",
           "body_chars": 0, "mode": "direct", "url_filters": [],
           "verdict": "exclude", "reason": ""}

    status, final, html = fetch(url)
    if status != 200:
        for alt in ({base.replace("://www.", "://")} if "://www." in base
                    else {base.replace("://", "://www.")}):
            status, final, html = fetch(alt)
            if status == 200:
                base = f"{urlparse(final).scheme}://{urlparse(final).netloc}"
                break
    res["http_status"] = status
    if status != 200 or not html:
        res["reason"] = f"raiz no responde (status {status})"
        return res
    res["alive"] = True
    res["url"] = base

    robots = check_robots(base)
    res.update({k: robots[k] for k in
                ("disallow_all", "ai_train_denied", "ai_denial_evidence", "ai_denial_kind")})
    if robots["disallow_all"]:
        res["reason"] = "robots.txt: Disallow / para todos los agentes"
        return res
    if robots["ai_train_denied"] and RESPECT_AI_OPT_OUT:
        res["reason"] = f"NEGATIVA EXPLICITA a entrenar modelos -> {robots['ai_denial_evidence']}"
        return res

    feeds, full_text = discover_feeds(base, html)
    res["rss_feeds"], res["has_rss"], res["rss_full_text"] = feeds, bool(feeds), full_text

    sitemap_url, locs = discover_sitemap(base)
    res["sitemap_url"], res["has_sitemap"], res["sitemap_locs"] = sitemap_url, bool(locs), len(locs)

    articles = [u for u in locs if looks_like_article(u)]
    if len(articles) < MIN_ARTICLE_URLS:
        articles = links_from_home(base, html)
    if len(articles) < MIN_ARTICLE_URLS and feeds:
        _, _, feed_body = fetch(feeds[0], timeout=15)
        articles = [u for u in re.findall(r"<link[^>]*>\s*([^<\s]+)\s*</link>", feed_body)
                    if looks_like_article(u)]
        articles += [u for u in re.findall(r'<link[^>]+href=["\']([^"\']+)["\']', feed_body)
                     if looks_like_article(u)]

    articles = list(dict.fromkeys(articles))
    if len(articles) < MIN_ARTICLE_URLS:
        res["reason"] = (f"sin URLs por articulo (sitemap {len(locs)} locs, "
                         f"{len(articles)} con forma de articulo): mega-pagina o SPA")
        return res
    res["has_permalinks"] = True

    # Prueba de extraccion real con trafilatura sobre hasta 3 articulos.
    best = 0
    for art in articles[:3]:
        _, _, art_html = fetch(art, timeout=25)
        if not art_html:
            continue
        text = trafilatura.extract(art_html, include_comments=False, include_tables=False)
        if text and len(text) > best:
            best, res["permalink_example"] = len(text), art
        if best >= MIN_BODY_CHARS:
            break
    res["body_chars"] = best

    if best < MIN_BODY_CHARS and not full_text:
        res["reason"] = (f"trafilatura extrae {best} chars (<{MIN_BODY_CHARS}): "
                         "cuerpo renderizado en cliente, en PDF, o solo video")
        return res

    if cand.get("category") in ALL_POLITICAL:
        res["mode"], res["url_filters"] = "direct", []
    else:
        filters = derive_filters(articles)
        res["mode"] = "sitemap"
        res["url_filters"] = filters

    res["verdict"] = "include"
    res["reason"] = (f"{status} OK | sitemap {len(locs)} locs, {len(articles)} articulos | "
                     f"trafilatura {best} chars | RSS {len(feeds)}"
                     f"{' (full-text)' if full_text else ''}")
    return res


def to_python(rows: list[dict]) -> str:
    """Emite las entradas en el formato exacto de src/scraper/sources.py."""
    out = []
    for r in sorted(rows, key=lambda x: (x["category"], x["key"])):
        note = ""
        if r["body_chars"] < 800:
            note = "  # OJO: cuerpo corto en la muestra"
        elif r["sitemap_locs"] and r["sitemap_locs"] < 60:
            note = "  # OJO: archivo pequeno"
        out.append(
            f'    "{r["key"]}": {{{note}\n'
            f'        "url": "{r["url"]}",\n'
            f'        "category": "{r["category"]}",\n'
            f'        "mode": "{r["mode"]}",\n'
            f'        "url_filters": {json.dumps(r["url_filters"])},\n'
            f'        "rss_feeds": {json.dumps(r["rss_feeds"])},\n'
            f"    }},"
        )
    return "\n".join(out)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("candidates", help="JSON con la lista de candidatos")
    ap.add_argument("-o", "--output", default=None, help="JSON de salida")
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--emit-python", action="store_true",
                    help="Imprime las entradas listas para sources.py")
    ap.add_argument("--allow-ai-blocked", action="store_true",
                    help="Registra tambien los sitios que bloquean crawlers de "
                         "entrenamiento. Por defecto se excluyen: es una decision "
                         "de consentimiento y conviene poder defenderla en la tesis.")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    for noisy in ("trafilatura", "courlan", "htmldate"):
        logging.getLogger(noisy).setLevel(logging.ERROR)

    global RESPECT_AI_OPT_OUT
    RESPECT_AI_OPT_OUT = not args.allow_ai_blocked

    cands = json.loads(Path(args.candidates).read_text(encoding="utf-8"))
    logger.info("Verificando %d candidatos con %d workers...", len(cands), args.workers)

    rows, done = [], 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(verify, c): c for c in cands}
        for fut in as_completed(futures):
            cand = futures[fut]
            try:
                rows.append(fut.result())
            except Exception as exc:  # noqa: BLE001
                rows.append({**cand, "alive": False, "verdict": "exclude",
                             "body_chars": 0, "sitemap_locs": 0,
                             "reason": f"error de verificacion: {type(exc).__name__}"})
            done += 1
            if done % 20 == 0:
                logger.info("  %d/%d", done, len(cands))

    ok = [r for r in rows if r["verdict"] == "include"]
    logger.info("\n%d incluidos, %d descartados", len(ok), len(rows) - len(ok))
    denied = [r for r in rows if r.get("ai_train_denied")]
    if denied:
        logger.info("EXCLUIDOS POR NEGARSE AL ENTRENAMIENTO (%d): %s",
                    len(denied), ", ".join(r["domain"] for r in denied))

    if args.output:
        Path(args.output).write_text(json.dumps(rows, ensure_ascii=False, indent=1),
                                     encoding="utf-8")
        logger.info("-> %s", args.output)
    if args.emit_python:
        print("\n" + to_python(ok))


if __name__ == "__main__":
    main()
