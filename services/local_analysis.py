"""
Análisis local avanzado — detecta fotos sospechosas SIN APIs externas.
Heurísticas basadas en patrones de imágenes de internet, screenshots, y IA.
"""
import io
import struct
from PIL import Image


def analyze_local(image_bytes):
    """Análisis completo local sin APIs."""
    result = {
        "flags": [],
        "score": 0,
        "is_screenshot": False,
        "is_download": False,
        "resolution_suspicious": False,
        "perfect_dimensions": False,
        "color_anomaly": False,
    }

    try:
        img = Image.open(io.BytesIO(image_bytes))
        w, h = img.size
        mode = img.mode

        # === 1. Detección de SCREENSHOT ===
        # Screenshots tienen dimensiones exactas de pantalla
        screen_sizes = [
            (1920, 1080), (1080, 1920), (2560, 1440), (1440, 2560),
            (1366, 768), (768, 1366), (1280, 720), (720, 1280),
            (2048, 1152), (1152, 2048), (3840, 2160), (2160, 3840),
            (750, 1334), (1334, 750),  # iPhone 6/7/8
            (1125, 2436), (2436, 1125),  # iPhone X/11
            (1170, 2532), (2532, 1170),  # iPhone 12/13
            (1290, 2796), (2796, 1290),  # iPhone 14 Pro
            (1080, 2400), (2400, 1080),  # Android común
            (1440, 3200), (3200, 1440),  # Android high-end
            (1080, 2340), (2340, 1080),  # Android
        ]
        if (w, h) in screen_sizes:
            result["is_screenshot"] = True
            result["flags"].append(f"📱 Dimensiones de screenshot ({w}x{h})")
            result["score"] += 8

        # === 2. Dimensiones perfectas de IA ===
        # Las IAs generan imágenes con dimensiones múltiplo de 64/128/256
        ai_dims = [512, 768, 1024, 1536, 2048]
        if w in ai_dims and h in ai_dims:
            result["perfect_dimensions"] = True
            result["flags"].append(f"🤖 Dimensiones típicas de IA ({w}x{h})")
            result["score"] += 15

        # Ratio perfecto 1:1 (común en IA pero no en fotos reales)
        if w == h and w >= 512:
            result["flags"].append(f"🤖 Ratio 1:1 perfecto ({w}x{h}) — común en IA")
            result["score"] += 10

        # === 3. Resolución sospechosa ===
        # Fotos muy pequeñas = descargadas y recomprimidas
        total_pixels = w * h
        if total_pixels < 200000:  # < ~450x450
            result["resolution_suspicious"] = True
            result["flags"].append(f"⚠️ Resolución muy baja ({w}x{h}) — probable recorte/descarga")
            result["score"] += 8

        # === 4. Análisis de formato/compresión ===
        fmt = img.format
        if fmt == "PNG" and total_pixels > 2000000:
            # PNG de alta resolución sin EXIF = probable descarga
            result["flags"].append("⚠️ PNG alta resolución — inusual para foto de cámara")
            result["score"] += 5

        if fmt == "WEBP":
            result["flags"].append("⚠️ Formato WebP — probable descarga de web")
            result["score"] += 8
            result["is_download"] = True

        # === 5. Análisis de color para IA ===
        if mode == "RGB":
            # Muestrear pixels para detectar patrones de IA
            pixels = list(img.resize((100, 100)).getdata())
            
            # Varianza de color — IA tiende a tener distribución más uniforme
            r_vals = [p[0] for p in pixels]
            g_vals = [p[1] for p in pixels]
            b_vals = [p[2] for p in pixels]
            
            avg_r = sum(r_vals) / len(r_vals)
            avg_g = sum(g_vals) / len(g_vals)
            avg_b = sum(b_vals) / len(b_vals)
            
            # Varianza
            var_r = sum((x - avg_r)**2 for x in r_vals) / len(r_vals)
            var_g = sum((x - avg_g)**2 for x in g_vals) / len(g_vals)
            var_b = sum((x - avg_b)**2 for x in b_vals) / len(b_vals)
            
            # Fotos reales: varianza alta (muchos colores diferentes)
            # IA/renders: varianza puede ser anormalmente baja en áreas de piel
            total_var = (var_r + var_g + var_b) / 3
            
            if total_var < 500:
                result["color_anomaly"] = True
                result["flags"].append("🤖 Distribución de color anormal — posible IA/render")
                result["score"] += 10

            # === 6. Detección de bordes de recorte ===
            # Si los bordes son de un solo color = recortado
            top_row = pixels[:100]
            bottom_row = pixels[-100:]
            
            top_uniform = all(abs(p[0] - top_row[0][0]) < 5 and 
                            abs(p[1] - top_row[0][1]) < 5 and 
                            abs(p[2] - top_row[0][2]) < 5 for p in top_row[:20])
            
            if top_uniform:
                result["flags"].append("⚠️ Borde superior uniforme — posible recorte/edición")
                result["score"] += 5

        # === 7. Tamaño de archivo vs resolución ===
        file_size = len(image_bytes)
        if total_pixels > 0:
            bytes_per_pixel = file_size / total_pixels
            # JPEG de cámara: ~0.5-2 bytes/pixel
            # Recomprimido muchas veces: < 0.3
            # Screenshot PNG: > 3
            if bytes_per_pixel < 0.2 and fmt in ("JPEG", "JPG"):
                result["flags"].append("⚠️ Compresión excesiva — imagen reenviada múltiples veces")
                result["score"] += 8

        # === 8. Chunks PNG sospechosos ===
        if fmt == "PNG":
            try:
                raw = image_bytes
                # Buscar texto en chunks tEXt/iTXt
                text_chunks = []
                pos = 8  # skip PNG header
                while pos < len(raw) - 12:
                    chunk_len = struct.unpack('>I', raw[pos:pos+4])[0]
                    chunk_type = raw[pos+4:pos+8].decode('ascii', errors='ignore')
                    if chunk_type in ('tEXt', 'iTXt', 'zTXt'):
                        chunk_data = raw[pos+8:pos+8+chunk_len].decode('ascii', errors='ignore')
                        text_chunks.append(chunk_data)
                        # Detectar herramientas de IA
                        lower = chunk_data.lower()
                        if any(x in lower for x in ['stable diffusion', 'midjourney', 'dall-e',
                                'comfyui', 'automatic1111', 'novelai', 'nai diffusion']):
                            result["flags"].append(f"🔴 METADATO IA: {chunk_data[:80]}")
                            result["score"] += 40
                        elif any(x in lower for x in ['photoshop', 'gimp', 'canva']):
                            result["flags"].append(f"🟡 Editado con: {chunk_data[:50]}")
                            result["score"] += 10
                    pos += 12 + chunk_len
            except:
                pass

    except Exception as e:
        print(f"[LocalAnalysis] Error: {e}")

    return result
