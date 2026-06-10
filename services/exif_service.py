"""
Extracción de metadatos EXIF de imágenes.
"""
import io
from PIL import Image
from PIL.ExifTags import TAGS


def extract_exif(image_bytes):
    """Extrae EXIF de bytes de imagen. Retorna dict con info relevante."""
    result = {
        "has_exif": False,
        "camera": None,
        "software": None,
        "date": None,
        "gps": False,
    }
    
    try:
        img = Image.open(io.BytesIO(image_bytes))
        exif_data = img._getexif()
        
        if not exif_data:
            return result
        
        result["has_exif"] = True
        decoded = {}
        for tag_id, value in exif_data.items():
            tag = TAGS.get(tag_id, tag_id)
            decoded[tag] = value
        
        # Modelo de cámara/teléfono
        model = decoded.get("Model", "")
        make = decoded.get("Make", "")
        if make or model:
            result["camera"] = f"{make} {model}".strip()
        
        # Software (Photoshop, Lightroom, etc.)
        software = decoded.get("Software", "")
        if software:
            result["software"] = str(software)
        
        # Fecha
        date = decoded.get("DateTimeOriginal", decoded.get("DateTime", ""))
        if date:
            result["date"] = str(date)
        
        # GPS
        if "GPSInfo" in decoded:
            result["gps"] = True
    
    except Exception as e:
        print(f"[EXIF] Error: {e}")
    
    return result
