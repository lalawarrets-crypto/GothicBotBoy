"""
Busqueda inversa de imagenes — sin APIs externas.
Usa Bing Visual Search + Google searchbyimage directamente.
"""
import urllib.request
import urllib.parse
import re
import json


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,es;q=0.8",
}


def _bing_search(image_url):
    """Bing Visual Search — scraping de resultados."""
    sources = []
    try:
        encoded = urllib.parse.quote(image_url, safe="")
        url = f"https://www.bing.com/images/search?view=detailv2&iss=sbi&form=SBIVSP&sbisrc=UrlPaste&q=imgurl:{encoded}"
        
        req = urllib.request.Request(url, headers=HEADERS)
        resp = urllib.request.urlopen(req, timeout=15)
        html = resp.read().decode("utf-8", errors="ignore")

        # Buscar "Pages with this image" / resultados
        # Bing pone los resultados en elementos con data-url o href
        patterns = [
            r'<a[^>]*href="(https?://(?!www\.bing|bing\.com|microsoft)[^"]{20,200})"[^>]*>([^<]{5,100})</a>',
            r'"purl":"(https?://[^"]{20,200})"',
            r'"pageUrl":"(https?://[^"]{20,200})"',
            r'"hostPageUrl":"(https?://[^"]{20,200})"',
            r'"contentUrl":"(https?://[^"]{20,200})"',
        ]
        
        found_urls = {}
        for pattern in patterns:
            matches = re.findall(pattern, html)
            for match in matches:
                if isinstance(match, tuple):
                    url_found, title = match[0], match[1] if len(match) > 1 else ""
                else:
                    url_found, title = match, ""
                
                low = url_found.lower()
                if any(x in low for x in ["bing.com", "microsoft.com", "msn.com", "javascript:", "bing.net"]):
                    continue
                
                try:
                    domain = url_found.split("//")[1].split("/")[0].replace("www.", "")
                except:
                    domain = url_found
                
                if domain not in found_urls:
                    clean_title = re.sub(r'<[^>]+>', '', title).strip() if title else domain
                    found_urls[domain] = {
                        "title": clean_title[:60] or domain,
                        "url": url_found,
                        "source": domain,
                    }

        sources = list(found_urls.values())[:10]
        
    except Exception as e:
        print(f"[Bing] Error: {e}")
    
    return sources


def _google_search(image_url):
    """Google Reverse Image Search — scraping de resultados."""
    sources = []
    try:
        encoded = urllib.parse.quote(image_url, safe="")
        url = f"https://www.google.com/searchbyimage?image_url={encoded}&safe=off"
        
        req = urllib.request.Request(url, headers=HEADERS)
        # Google redirige — seguir
        resp = urllib.request.urlopen(req, timeout=15)
        html = resp.read().decode("utf-8", errors="ignore")

        # Google pone resultados en <div class="g"> con <a href="url">
        # También buscar en el JSON embebido
        patterns = [
            r'<a href="(https?://(?!google|gstatic|youtube|schema\.org|accounts\.google)[^"]{20,200})"[^>]*><h3[^>]*>([^<]+)</h3>',
            r'<a href="/url\?q=(https?://(?!google)[^&"]{20,200})[&"]',
            r'"url":"(https?://(?!google|gstatic|googleapis)[^"]{20,200})"',
        ]
        
        found_urls = {}
        for pattern in patterns:
            matches = re.findall(pattern, html)
            for match in matches:
                if isinstance(match, tuple):
                    url_found = match[0]
                    title = match[1] if len(match) > 1 else ""
                else:
                    url_found = match
                    title = ""
                
                url_found = urllib.parse.unquote(url_found)
                
                try:
                    domain = url_found.split("//")[1].split("/")[0].replace("www.", "")
                except:
                    domain = url_found
                
                if domain not in found_urls:
                    clean_title = re.sub(r'<[^>]+>', '', title).strip() if title else domain
                    found_urls[domain] = {
                        "title": clean_title[:60] or domain,
                        "url": url_found,
                        "source": domain,
                    }

        sources = list(found_urls.values())[:10]

        # Buscar "best guess" de Google — qué cree que es la imagen
        guess_match = re.search(r'Best guess for this image:.*?<a[^>]*>([^<]+)</a>', html)
        if guess_match:
            sources.insert(0, {
                "title": f"📌 Google dice: {guess_match.group(1)}",
                "url": "",
                "source": "Google",
            })

    except Exception as e:
        print(f"[Google] Error: {e}")
    
    return sources


def search_image(image_url):
    """Busqueda inversa combinando Bing + Google. Retorna hasta 10 fuentes."""
    all_sources = []
    engines = []

    # Bing primero (más fácil de scrapear)
    bing = _bing_search(image_url)
    if bing:
        all_sources.extend(bing)
        engines.append("Bing")

    # Google como complemento
    google = _google_search(image_url)
    if google:
        engines.append("Google")
        # Agregar los que no estén ya
        existing_domains = {s["source"] for s in all_sources}
        for s in google:
            if s["source"] not in existing_domains:
                all_sources.append(s)

    # Manual links de respaldo
    encoded = urllib.parse.quote(image_url, safe="")
    manual = {
        "Google Lens": f"https://lens.google.com/uploadbyurl?url={encoded}",
        "Yandex": f"https://yandex.com/images/search?rpt=imageview&url={encoded}",
        "TinEye": f"https://tineye.com/search?url={encoded}",
    }

    return {
        "found": len(all_sources) > 0,
        "engine": " + ".join(engines) if engines else "ninguno",
        "sources": all_sources[:10],
        "manual_links": manual,
        "error": None if all_sources else "Sin resultados",
    }
