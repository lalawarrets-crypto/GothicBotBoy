"""
Tracker de comportamiento — detecta patrones de catfish.
"""
from database.db import get_user_images, get_name_changes


def analyze_behavior(discord_id, message_count=0, image_count=0):
    """Analiza patrones de comportamiento sospechoso."""
    flags = []
    score = 0

    # Ratio imágenes vs texto
    if message_count > 0 and image_count > 0:
        ratio = image_count / max(message_count, 1)
        if ratio > 0.7:
            flags.append("⚠️ Solo manda fotos, casi no habla")
            score += 10
        elif ratio > 0.5:
            flags.append("🟡 Más fotos que texto")
            score += 5

    # Cambios de nombre frecuentes
    changes = get_name_changes(discord_id, days=7)
    if len(changes) >= 5:
        flags.append(f"🔴 Cambió nombre {len(changes)} veces en 7 días")
        score += 20
    elif len(changes) >= 3:
        flags.append(f"🟡 Cambió nombre {len(changes)} veces en 7 días")
        score += 10

    # Imágenes previas
    images = get_user_images(discord_id, limit=50)
    if images:
        no_exif = sum(1 for img in images if not img.get("has_exif"))
        total = len(images)
        exif_ratio = no_exif / total if total else 0

        if exif_ratio > 0.8 and total >= 3:
            flags.append(f"🔴 {int(exif_ratio*100)}% fotos sin EXIF ({no_exif}/{total})")
            score += 15

        # IA detections
        ai_flags = sum(1 for img in images if img.get("ai_score", 0) > 0.5)
        if ai_flags >= 2:
            flags.append(f"🔴 {ai_flags} fotos detectadas como IA")
            score += 25

        # Duplicados
        dups = sum(1 for img in images if img.get("duplicate_of"))
        if dups >= 1:
            flags.append(f"🔴 {dups} fotos duplicadas de otros usuarios")
            score += 30

    return {"flags": flags, "score": score}
