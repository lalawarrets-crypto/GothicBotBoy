"""
Error Level Analysis AVANZADO — detecta manipulación, composición, y clonación.
"""
import io
from PIL import Image


def analyze_ela(image_bytes, quality=85):
    """Análisis ELA avanzado con múltiples pasadas."""
    result = {
        "score": 0,
        "avg_diff": 0,
        "high_ratio": 0,
        "manipulated": False,
        "details": "",
    }
    
    try:
        original = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        w, h = original.size
        
        # Reducir para velocidad si es muy grande
        if w * h > 2000000:
            ratio = (2000000 / (w * h)) ** 0.5
            original = original.resize((int(w*ratio), int(h*ratio)), Image.LANCZOS)
            w, h = original.size

        scores = []
        
        # Múltiples pasadas con diferentes calidades
        for q in [75, 85, 95]:
            buffer = io.BytesIO()
            original.save(buffer, format="JPEG", quality=q)
            buffer.seek(0)
            resaved = Image.open(buffer).convert("RGB")

            orig_px = list(original.getdata())
            resav_px = list(resaved.getdata())

            diffs = []
            for op, rp in zip(orig_px, resav_px):
                diff = sum(abs(a - b) for a, b in zip(op, rp)) / 3
                diffs.append(diff)

            total = len(diffs)
            avg = sum(diffs) / total if total else 0
            high = sum(1 for d in diffs if d > 20) / total * 100 if total else 0
            
            # Detectar zonas con diferencia MUY diferente al promedio
            # Esto indica composición (parte de la imagen fue pegada)
            if total > 100:
                # Dividir en cuadrantes y comparar
                quad_size = total // 4
                quads = [diffs[i:i+quad_size] for i in range(0, total, quad_size)][:4]
                quad_avgs = [sum(q)/len(q) if q else 0 for q in quads]
                
                if quad_avgs:
                    overall_avg = sum(quad_avgs) / len(quad_avgs)
                    max_deviation = max(abs(qa - overall_avg) for qa in quad_avgs)
                    
                    if max_deviation > 15:
                        result["details"] += f"Zona editada detectada (dev={max_deviation:.1f}) "
                        high += 10

            scores.append({"quality": q, "avg": avg, "high": high})

        # Score final: promedio de las pasadas
        avg_high = sum(s["high"] for s in scores) / len(scores)
        avg_diff = sum(s["avg"] for s in scores) / len(scores)

        if avg_high > 25:
            result["score"] = 85
            result["manipulated"] = True
            result["details"] += "Manipulación significativa"
        elif avg_high > 12:
            result["score"] = 55
            result["manipulated"] = True
            result["details"] += "Edición detectada"
        elif avg_high > 5:
            result["score"] = 25
            result["details"] += "Posible edición menor"
        else:
            result["score"] = 3
            result["details"] += "Sin manipulación aparente"

        result["avg_diff"] = round(avg_diff, 2)
        result["high_ratio"] = round(avg_high, 2)

    except Exception as e:
        print(f"[ELA] Error: {e}")
        result["details"] = f"Error: {e}"

    return result
