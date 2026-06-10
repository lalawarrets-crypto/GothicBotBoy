"""
Busqueda inversa via SerpAPI (Google Lens).
100 busquedas/mes gratis. Retorna fuentes reales.
"""
import os
import json
import urllib.request
import urllib.parse

SERPAPI_KEY = os.getenv("SERPAPI_KEY", "")


def search_image(image_url):
    """Busca imagen con Google Lens via SerpAPI."""
    result = {
        "found": False,
        "sources": [],
        "guess": "",
        "error": None,
        "manual_links": _manual_links(image_url),
    }

    if not SERPAPI_KEY:
        result["error"] = "SERPAPI_KEY no configurada"
        return result

    try:
        params = urllib.parse.urlencode({
            "engine": "google_lens",
            "url": image_url,
            "api_key": SERPAPI_KEY,
        })
        url = f"https://serpapi.com/search.json?{params}"
        req = urllib.request.Request(url, headers={"User-Agent": "AntiCatfish/1.0"})
        resp = urllib.request.urlopen(req, timeout=25)
        data = json.loads(resp.read())

        sources = []

        # Visual matches — paginas donde aparece la imagen
        for match in data.get("visual_matches", []):
            title = match.get("title", "")[:60]
            link = match.get("link", "")
            source_name = match.get("source", "")[:30]

            if not link:
                continue
            if any(x in link.lower() for x in ["google.com", "gstatic", "googleapis"]):
                continue

            try:
                domain = link.split("//")[1].split("/")[0].replace("www.", "")
            except:
                domain = source_name

            sources.append({
                "title": title or source_name or domain,
                "url": link,
                "source": domain,
            })

        # Knowledge graph
        kg = data.get("knowledge_graph", {})
        if isinstance(kg, dict) and kg.get("title"):
            result["guess"] = kg["title"]
        elif isinstance(kg, list):
            for item in kg[:2]:
                if item.get("title"):
                    result["guess"] = item["title"]
                    break

        # Reverse image search results
        for item in data.get("reverse_image_search", {}).get("results", []):
            link = item.get("link", "")
            title = item.get("title", "")[:60]
            if link and "google" not in link.lower():
                try:
                    domain = link.split("//")[1].split("/")[0].replace("www.", "")
                except:
                    domain = ""
                sources.append({
                    "title": title or domain,
                    "url": link,
                    "source": domain,
                })

        # Deduplicar por dominio
        seen = set()
        unique = []
        for s in sources:
            if s["source"] not in seen:
                seen.add(s["source"])
                unique.append(s)

        if unique:
            result["found"] = True
            result["sources"] = unique[:10]

    except Exception as e:
        result["error"] = str(e)[:80]
        print(f"[SerpAPI] Error: {e}")

    return result


def _manual_links(image_url):
    encoded = urllib.parse.quote(image_url, safe="")
    return {
        "Google Lens": f"https://lens.google.com/uploadbyurl?url={encoded}",
        "Yandex": f"https://yandex.com/images/search?rpt=imageview&url={encoded}",
        "TinEye": f"https://tineye.com/search?url={encoded}",
    }
