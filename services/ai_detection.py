"""
Detección de imágenes generadas por IA via SightEngine API.
Free tier: 500 operaciones/mes.
"""
import json
import urllib.request
import urllib.parse
import os

API_USER = os.getenv("SIGHTENGINE_USER", "")
API_SECRET = os.getenv("SIGHTENGINE_SECRET", "")


def check_ai_image(image_url):
    """Analiza una imagen por URL con SightEngine. Retorna dict con scores."""
    result = {
        "ai_score": 0.0,
        "ai_type": "unknown",
        "error": None,
    }
    
    if not API_USER or not API_SECRET:
        result["error"] = "SightEngine no configurado"
        return result
    
    try:
        params = urllib.parse.urlencode({
            "url": image_url,
            "models": "genai",
            "api_user": API_USER,
            "api_secret": API_SECRET,
        })
        
        url = f"https://api.sightengine.com/1.0/check.json?{params}"
        req = urllib.request.Request(url, headers={"User-Agent": "AntiCatfish/1.0"})
        resp = urllib.request.urlopen(req, timeout=15)
        data = json.loads(resp.read())
        
        if data.get("status") == "success":
            ai_data = data.get("type", {})
            ai_score = ai_data.get("ai_generated", 0)
            
            result["ai_score"] = round(float(ai_score), 3)
            if result["ai_score"] > 0.5:
                result["ai_type"] = "AI Generated"
            else:
                result["ai_type"] = "Likely Real"
        else:
            result["error"] = data.get("error", {}).get("message", "API error")
    
    except Exception as e:
        result["error"] = str(e)
        print(f"[AI] Error: {e}")
    
    return result


def check_ai_bytes(image_bytes):
    """Analiza bytes de imagen subiendo a SightEngine."""
    result = {
        "ai_score": 0.0,
        "ai_type": "unknown",
        "error": None,
    }
    
    if not API_USER or not API_SECRET:
        result["error"] = "SightEngine no configurado"
        return result
    
    try:
        import uuid
        boundary = uuid.uuid4().hex
        body = b""
        
        # api_user
        body += f"--{boundary}\r\nContent-Disposition: form-data; name=\"api_user\"\r\n\r\n{API_USER}\r\n".encode()
        # api_secret
        body += f"--{boundary}\r\nContent-Disposition: form-data; name=\"api_secret\"\r\n\r\n{API_SECRET}\r\n".encode()
        # models
        body += f"--{boundary}\r\nContent-Disposition: form-data; name=\"models\"\r\n\r\ngenai\r\n".encode()
        # media
        body += f"--{boundary}\r\nContent-Disposition: form-data; name=\"media\"; filename=\"image.jpg\"\r\nContent-Type: image/jpeg\r\n\r\n".encode()
        body += image_bytes
        body += f"\r\n--{boundary}--\r\n".encode()
        
        req = urllib.request.Request(
            "https://api.sightengine.com/1.0/check.json",
            data=body,
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "User-Agent": "AntiCatfish/1.0",
            },
        )
        resp = urllib.request.urlopen(req, timeout=20)
        data = json.loads(resp.read())
        
        if data.get("status") == "success":
            ai_data = data.get("type", {})
            result["ai_score"] = round(float(ai_data.get("ai_generated", 0)), 3)
            result["ai_type"] = "AI Generated" if result["ai_score"] > 0.5 else "Likely Real"
        else:
            result["error"] = data.get("error", {}).get("message", "API error")
    
    except Exception as e:
        result["error"] = str(e)
        print(f"[AI] Bytes error: {e}")
    
    return result
