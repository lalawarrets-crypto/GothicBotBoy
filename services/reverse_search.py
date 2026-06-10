"""
Busqueda inversa de imagenes — detecta si una foto existe en internet.
Usa Yandex Images + Google Lens.
"""
import urllib.request
import urllib.parse
import re


def reverse_search_yandex(image_url):
    """Busca una imagen en Yandex."""
    result = {"found": False, "matches": 0, "source": "", "error": None}

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
            r'class="serp-item__link"[^>]*href="(https?://[^"]+)"',
        ]
        for pattern in site_patterns:
            matches = re.findall(pattern, html)
            for m in matches:
                if "yandex" not in m.lower() and "google" not in m.lower():
                    sites_found.append(m)

        has_results = any(x in html.lower() for x in [
            "similar images", "sites containing",
            "other sizes", "results found",
            "serp-item", "thumb-image",
        ])

        unique_sites = list(set(sites_found))[:10]

        if unique_sites or has_results:
            result["found"] = True
            result["matches"] = max(len(unique_sites), 1)
            if unique_sites:
                result["source"] = unique_sites[0][:100]

    except Exception as e:
        result["error"] = str(e)[:80]
        print(f"[Yandex] Error: {e}")

    return result


def reverse_search_google_lens(image_url):
    """Busqueda en Google Lens como respaldo."""
    result = {"found": False, "matches": 0, "source": "", "error": None}

    try:
        encoded_url = urllib.parse.quote(image_url, safe="")
        lens_url = f"https://lens.google.com/uploadbyurl?url={encoded_url}"

        req = urllib.request.Request(lens_url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html",
        })
        resp = urllib.request.urlopen(req, timeout=15)
        html = resp.read().decode("utf-8", errors="ignore")

        social_matches = re.findall(
            r'"(https?://(?:www\.)?(?:instagram|facebook|twitter|tiktok|pinterest|reddit|vk\.com)[^"]+)"',
            html)

        if social_matches:
            result["found"] = True
            result["matches"] = len(social_matches)
            result["source"] = social_matches[0][:100]
        elif "visual_matches" in html or "search_results" in html:
            result["found"] = True
            result["matches"] = 1

    except Exception as e:
        result["error"] = str(e)[:80]

    return result


def search_image(image_url):
    """Ejecuta busqueda inversa con Yandex + Google Lens."""
    yandex = reverse_search_yandex(image_url)
    if yandex["found"]:
        return {
            "found": True,
            "engine": "Yandex",
            "matches": yandex["matches"],
            "source": yandex["source"],
            "error": None,
        }

    google = reverse_search_google_lens(image_url)
    if google["found"]:
        return {
            "found": True,
            "engine": "Google Lens",
            "matches": google["matches"],
            "source": google["source"],
            "error": None,
        }

    return {
        "found": False,
        "engine": "Yandex+Google",
        "matches": 0,
        "source": "",
        "error": yandex.get("error") or google.get("error"),
    }
