"""
Busqueda inversa de imagenes.
Genera links directos a Yandex, Google Lens y TinEye
para que el moderador verifique manualmente.
"""
import urllib.parse


def search_image(image_url):
    """Genera URLs de busqueda inversa para verificación manual."""
    encoded = urllib.parse.quote(image_url, safe="")

    links = {
        "🔍 Google Lens": f"https://lens.google.com/uploadbyurl?url={encoded}",
        "🔎 Yandex": f"https://yandex.com/images/search?rpt=imageview&url={encoded}",
        "🔎 TinEye": f"https://tineye.com/search?url={encoded}",
    }

    return {
        "links": links,
        "found": True,  # siempre genera links
    }
