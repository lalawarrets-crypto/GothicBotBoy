"""
Error Level Analysis — detecta zonas editadas/manipuladas en imágenes.
"""
import io
from PIL import Image

def analyze_ela(image_bytes, quality=90, threshold=25):
    """Analiza ELA. Retorna score de manipulación 0-100."""
    try:
        original = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        w, h = original.size

        # Resalvar con compresión
        buffer = io.BytesIO()
        original.save(buffer, format="JPEG", quality=quality)
        buffer.seek(0)
        resaved = Image.open(buffer).convert("RGB")

        # Calcular diferencia pixel a pixel
        orig_pixels = list(original.getdata())
        resav_pixels = list(resaved.getdata())

        total_diff = 0
        high_diff_count = 0
        total_pixels = len(orig_pixels)

        for op, rp in zip(orig_pixels, resav_pixels):
            diff = sum(abs(a - b) for a, b in zip(op, rp)) / 3
            total_diff += diff
            if diff > threshold:
                high_diff_count += 1

        avg_diff = total_diff / total_pixels if total_pixels else 0
        high_ratio = (high_diff_count / total_pixels * 100) if total_pixels else 0

        # Score: zonas con diferencia alta = posible edición
        # Imágenes normales: high_ratio < 5%
        # Editadas: high_ratio > 15%
        if high_ratio > 30:
            score = 90
        elif high_ratio > 15:
            score = 60
        elif high_ratio > 5:
            score = 30
        else:
            score = 5

        return {
            "score": score,
            "avg_diff": round(avg_diff, 2),
            "high_ratio": round(high_ratio, 2),
            "manipulated": score > 40,
        }
    except Exception as e:
        print(f"[ELA] Error: {e}")
        return {"score": 0, "avg_diff": 0, "high_ratio": 0, "manipulated": False}
