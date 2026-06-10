"""
Hashing perceptual de imágenes para detectar duplicados.
"""
import io
from PIL import Image
import imagehash


def compute_phash(image_bytes):
    """Calcula perceptual hash de una imagen. Retorna string hex."""
    try:
        img = Image.open(io.BytesIO(image_bytes))
        h = imagehash.phash(img)
        return str(h)
    except Exception as e:
        print(f"[Hash] Error: {e}")
        return None


def hash_distance(hash1, hash2):
    """Distancia hamming entre dos hashes string."""
    if not hash1 or not hash2 or len(hash1) != len(hash2):
        return 999
    return sum(c1 != c2 for c1, c2 in zip(hash1, hash2))
