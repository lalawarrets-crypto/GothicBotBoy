"""
Busqueda inversa de imagenes — detecta si una foto existe en internet.
Usa Yandex Images + Google Lens.
"""
import urllib.request
import urllib.parse
import re


def reverse_search_yandex(image_url):
    """Busca una imagen en Yandex. Retorna hasta 10 fuentes."""
    result = {"found": False, "matches": 0, "sources": [], "error": None}

    try:
        encoded_url = urllib.parse.quote(image_url, safe="")
        search_url = f"https://yandex.com/images/search?rpt=imageview&url={encoded_url}"

        req = urllib.request.Request(search_url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.9",
        })
        resp = urllib.request.urlopen(req, timeout=15)
        html = resp.read().decode("utf-8", errors="ignore")

        sites_found = []
        site_patterns = [
            r'"siteUrl":"(https?://[^"]+)"',
            r'"url":"(https?://[^"]+)"',
            r'href="(https?://[^"]*(?:instagram|facebook|twitter|tiktok|pinterest|reddit|vk\.com|tumblr|flickr|deviantart|imgur)[^"]*)"',
            r'class="serp-item__link"[^>]*href="(https?://[^"]+)"',
            r'"pageURL":"(https?://[^"]+)"',
        ]
        for pattern in site_patterns:
            matches = re.findall(pattern, html)
            for m in matches:
                m_lower = m.lower()
                if "yandex" not in m_lower and "google" not in m_lower and len(m) > 10:
                    sites_found.append(m)

        # Deduplicar por dominio
        seen_domains = set()
        unique = []
        for url in sites_found:
            try:
                domain = url.split("//")[1].split("/")[0].replace("www.", "")
            except:
                domain = url
            if domain not in seen_domains:
                seen_domains.add(domain)
                unique.append(url)

        if unique:
            result["found"] = True
            result["matches"] = len(unique)
            result["sources"] = unique[:10]

    except Exception as e:
        result["error"] = str(e)[:80]
        print(f"[Yandex] Error: {e}")

    return result


def reverse_search_google_lens(image_url):
    """Busqueda en Google Lens como respaldo."""
    result = {"found": False, "matches": 0, "sources": [], "error": None}

    try:
        encoded_url = urllib.parse.quote(image_url, safe="")
        lens_url = f"https://lens.google.com/uploadbyurl?url={encoded_url}"

        req = urllib.request.Request(lens_url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html",
        })
        resp = urllib.request.urlopen(req, timeout=15)
        html = resp.read().decode("utf-8", errors="ignore")

        all_urls = re.findall(r'"(https?://[^"]{15,200})"', html)
        filtered = []
        seen = set()
        for url in all_urls:
            low = url.lower()
            if any(x in low for x in ["google", "gstatic", "googleapis", "schema.org"]):
                continue
            try:
                domain = url.split("//")[1].split("/")[0].replace("www.", "")
            except:
                domain = url
            if domain not in seen and len(url) > 15:
                seen.add(domain)
                filtered.append(url)

        if filtered:
            result["found"] = True
            result["matches"] = len(filtered)
            result["sources"] = filtered[:10]

    except Exception as e:
        result["error"] = str(e)[:80]

    return result


def search_image(image_url):
    """Ejecuta busqueda inversa con Yandex + Google Lens. Retorna hasta 10 fuentes."""
    all_sources = []

    yandex = reverse_search_yandex(image_url)
    if yandex["sources"]:
        all_sources.extend(yandex["sources"])

    google = reverse_search_google_lens(image_url)
    if google["sources"]:
        all_sources.extend(google["sources"])

    # Deduplicar por dominio
    seen = set()
    unique = []
    for url in all_sources:
        try:
            domain = url.split("//")[1].split("/")[0].replace("www.", "")
        except:
            domain = url
        if domain not in seen:
            seen.add(domain)
            unique.append(url)

    if unique:
        engine = []
        if yandex["sources"]:
            engine.append("Yandex")
        if google["sources"]:
            engine.append("Google")
        return {
            "found": True,
            "engine": " + ".join(engine),
            "matches": len(unique),
            "sources": unique[:10],
            "error": None,
        }

    return {
        "found": False,
        "engine": "Yandex+Google",
        "matches": 0,
        "sources": [],
        "error": yandex.get("error") or google.get("error"),
    }
