"""
Parser de metadatos de video MP4 — sin dependencias externas.
Parsea boxes MP4 manualmente para extraer info forense.
"""
import struct
import io
from datetime import datetime, timedelta


def _read_box(data, offset):
    if offset + 8 > len(data):
        return None, None, offset
    size = struct.unpack('>I', data[offset:offset+4])[0]
    box_type = data[offset+4:offset+8].decode('ascii', errors='ignore')
    if size == 0:
        size = len(data) - offset
    elif size == 1 and offset + 16 <= len(data):
        size = struct.unpack('>Q', data[offset+8:offset+16])[0]
    return box_type, size, offset


def _parse_mvhd(data):
    """Parse Movie Header Box para timestamps."""
    try:
        version = data[0]
        if version == 0:
            creation = struct.unpack('>I', data[4:8])[0]
            modification = struct.unpack('>I', data[8:12])[0]
            timescale = struct.unpack('>I', data[12:16])[0]
            duration = struct.unpack('>I', data[16:20])[0]
        else:
            creation = struct.unpack('>Q', data[4:12])[0]
            modification = struct.unpack('>Q', data[12:20])[0]
            timescale = struct.unpack('>I', data[20:24])[0]
            duration = struct.unpack('>Q', data[24:32])[0]

        # MP4 epoch: 1904-01-01
        epoch = datetime(1904, 1, 1)
        created = epoch + timedelta(seconds=creation) if creation else None
        modified = epoch + timedelta(seconds=modification) if modification else None
        dur_sec = duration / timescale if timescale else 0

        return {
            "creation_time": created.isoformat() if created and creation > 0 else None,
            "modification_time": modified.isoformat() if modified and modification > 0 else None,
            "duration_sec": round(dur_sec, 2),
            "timescale": timescale,
            "timestamps_zero": creation == 0 and modification == 0,
        }
    except:
        return None


def analyze_video(video_bytes):
    """Analiza metadatos forenses de un video MP4."""
    result = {
        "duration": 0,
        "creation_time": None,
        "modification_time": None,
        "timestamps_zero": True,
        "codec": "unknown",
        "resolution": "unknown",
        "suspicious": False,
        "flags": [],
    }

    try:
        data = video_bytes
        offset = 0
        while offset < len(data) - 8:
            box_type, size, _ = _read_box(data, offset)
            if box_type is None or size < 8:
                break

            box_data = data[offset+8:offset+size]

            if box_type == 'moov':
                # Parse sub-boxes
                sub_offset = 0
                while sub_offset < len(box_data) - 8:
                    sub_type, sub_size, _ = _read_box(box_data, sub_offset)
                    if sub_type is None or sub_size < 8:
                        break
                    if sub_type == 'mvhd':
                        mvhd = _parse_mvhd(box_data[sub_offset+8:sub_offset+sub_size])
                        if mvhd:
                            result["duration"] = mvhd["duration_sec"]
                            result["creation_time"] = mvhd["creation_time"]
                            result["modification_time"] = mvhd["modification_time"]
                            result["timestamps_zero"] = mvhd["timestamps_zero"]
                    sub_offset += sub_size

            elif box_type == 'ftyp':
                brand = box_data[:4].decode('ascii', errors='ignore')
                result["codec"] = brand

            offset += size

        # Análisis forense
        if result["timestamps_zero"]:
            result["flags"].append("⚠️ Timestamps en 0 — video reenviado/procesado")
            result["suspicious"] = True

        if result["duration"] > 0 and result["duration"] < 5:
            result["flags"].append("⚠️ Video muy corto (<5s) — posible clip robado")
            result["suspicious"] = True

        if result["duration"] == 0:
            result["flags"].append("⚠️ No se pudo leer duración")

    except Exception as e:
        result["flags"].append(f"Error: {e}")

    return result
