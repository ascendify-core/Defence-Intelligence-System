"""
Metadata Extractor
==================
Extracts image metadata: filename, timestamp, resolution,
GPS coordinates, and device/camera information from EXIF data.
"""

import os
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Any

from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS


# EXIF tag IDs we care about
_EXIF_FIELDS = {
    271: "make",              # Camera make
    272: "model",             # Camera model
    305: "software",          # Software
    306: "datetime_modified", # DateTime
    315: "artist",
    36867: "datetime_original",
    36868: "datetime_digitized",
    37377: "shutter_speed",
    37378: "aperture",
    37379: "brightness",
    37380: "exposure_bias",
    37381: "max_aperture",
    37383: "metering_mode",
    37385: "flash",
    37386: "focal_length",
    41986: "exposure_mode",
    41987: "white_balance",
    41990: "scene_capture_type",
    33434: "exposure_time",
    33437: "f_number",
    34855: "iso",
    40961: "color_space",
    40962: "pixel_x_dimension",
    40963: "pixel_y_dimension",
    37500: "maker_note",       # Manufacturer-specific
}

_GPS_TAG_ID = 34853  # GPSInfo tag


def _dms_to_decimal(dms, ref) -> float | None:
    """Convert GPS degrees/minutes/seconds tuple to decimal degrees."""
    try:
        d, m, s = dms
        # IFDRational or tuple
        d = float(d)
        m = float(m)
        s = float(s)
        decimal = d + m / 60 + s / 3600
        if ref in ("S", "W"):
            decimal = -decimal
        return round(decimal, 7)
    except Exception:
        return None


def _parse_gps(gps_info: dict) -> dict:
    """Parse raw GPS EXIF data into a clean dict."""
    result: dict[str, Any] = {}

    gps = {}
    for key, val in gps_info.items():
        tag_name = GPSTAGS.get(key, str(key))
        gps[tag_name] = val

    lat_dms = gps.get("GPSLatitude")
    lat_ref = gps.get("GPSLatitudeRef")
    lon_dms = gps.get("GPSLongitude")
    lon_ref = gps.get("GPSLongitudeRef")

    if lat_dms and lat_ref:
        result["latitude"] = _dms_to_decimal(lat_dms, lat_ref)
        result["latitude_ref"] = lat_ref
    if lon_dms and lon_ref:
        result["longitude"] = _dms_to_decimal(lon_dms, lon_ref)
        result["longitude_ref"] = lon_ref

    alt = gps.get("GPSAltitude")
    alt_ref = gps.get("GPSAltitudeRef")
    if alt is not None:
        alt_val = float(alt)
        if alt_ref == b"\x01":
            alt_val = -alt_val
        result["altitude_meters"] = round(alt_val, 2)

    speed = gps.get("GPSSpeed")
    speed_ref = gps.get("GPSSpeedRef")
    if speed is not None:
        result["speed"] = float(speed)
        result["speed_unit"] = {"K": "km/h", "M": "mph", "N": "knots"}.get(speed_ref, speed_ref)

    timestamp = gps.get("GPSTimeStamp")
    datestamp = gps.get("GPSDateStamp")
    if timestamp:
        h, m, s = [float(x) for x in timestamp]
        result["gps_time_utc"] = f"{int(h):02d}:{int(m):02d}:{float(s):06.3f}"
    if datestamp:
        result["gps_date"] = datestamp

    img_dir = gps.get("GPSImgDirection")
    if img_dir is not None:
        result["image_direction_degrees"] = round(float(img_dir), 2)

    if result.get("latitude") and result.get("longitude"):
        result["google_maps_url"] = (
            f"https://maps.google.com/?q={result['latitude']},{result['longitude']}"
        )

    return result


class MetadataExtractor:
    """Extracts EXIF, file-level, and GPS metadata from JPEG images."""

    def extract(self, image_path: Path) -> dict:
        """Return a metadata record for a single image."""
        record: dict[str, Any] = {
            "filename": image_path.name,
            "filepath": str(image_path.resolve()),
            "file_size_bytes": None,
            "file_size_human": None,
            "sha256": None,
            "timestamp": {},
            "resolution": {},
            "gps": None,
            "device": {},
            "camera_settings": {},
            "color": {},
            "errors": [],
        }

        # ── File-level info ────────────────────────────────────────────────
        try:
            stat = os.stat(image_path)
            size_bytes = stat.st_size
            record["file_size_bytes"] = size_bytes
            record["file_size_human"] = _human_size(size_bytes)

            mtime = datetime.fromtimestamp(stat.st_mtime)
            record["timestamp"]["file_modified"] = mtime.isoformat()
            ctime = datetime.fromtimestamp(stat.st_ctime)
            record["timestamp"]["file_created"] = ctime.isoformat()
        except Exception as e:
            record["errors"].append(f"File stat error: {e}")

        # ── SHA-256 hash ───────────────────────────────────────────────────
        try:
            h = hashlib.sha256()
            with open(image_path, "rb") as f:
                for chunk in iter(lambda: f.read(65536), b""):
                    h.update(chunk)
            record["sha256"] = h.hexdigest()
        except Exception as e:
            record["errors"].append(f"Hash error: {e}")

        # ── PIL / EXIF ─────────────────────────────────────────────────────
        try:
            with Image.open(image_path) as img:
                record["resolution"]["width"] = img.width
                record["resolution"]["height"] = img.height
                record["resolution"]["megapixels"] = round(img.width * img.height / 1_000_000, 2)
                record["resolution"]["aspect_ratio"] = _aspect(img.width, img.height)
                record["resolution"]["mode"] = img.mode
                record["color"]["mode"] = img.mode

                exif_data = img._getexif()
                if exif_data:
                    self._parse_exif(exif_data, record)
                else:
                    record["errors"].append("No EXIF data found in image.")
        except Exception as e:
            record["errors"].append(f"PIL/EXIF error: {e}")

        # Normalize: remove empty dicts
        for key in ["device", "camera_settings", "color", "timestamp"]:
            if not record.get(key):
                record[key] = None

        return record

    def _parse_exif(self, exif_data: dict, record: dict):
        device = {}
        camera_settings = {}
        color = {}

        for tag_id, value in exif_data.items():
            field = _EXIF_FIELDS.get(tag_id)

            # ── GPS ────────────────────────────────────────────────────────
            if tag_id == _GPS_TAG_ID:
                try:
                    record["gps"] = _parse_gps(value)
                except Exception as e:
                    record["errors"].append(f"GPS parse error: {e}")
                continue

            if field is None:
                continue

            # Convert IFDRational / bytes to plain types
            value = _coerce(value)

            if field in ("make", "model", "software", "artist"):
                device[field] = value
            elif field == "datetime_original":
                record["timestamp"]["captured"] = _parse_exif_dt(value)
            elif field == "datetime_digitized":
                record["timestamp"]["digitized"] = _parse_exif_dt(value)
            elif field == "datetime_modified":
                record["timestamp"]["exif_modified"] = _parse_exif_dt(value)
            elif field in ("shutter_speed", "aperture", "brightness", "exposure_bias",
                           "max_aperture", "metering_mode", "flash", "focal_length",
                           "exposure_mode", "white_balance", "scene_capture_type",
                           "exposure_time", "f_number", "iso"):
                camera_settings[field] = value
            elif field in ("color_space",):
                cs_map = {1: "sRGB", 65535: "Uncalibrated"}
                color["color_space"] = cs_map.get(value, str(value))
            elif field in ("pixel_x_dimension", "pixel_y_dimension"):
                pass  # We already have this from PIL

        record["device"] = device or None
        record["camera_settings"] = camera_settings or None
        record["color"] = {**record.get("color", {}), **color} or None


# ── Helpers ────────────────────────────────────────────────────────────────────

def _human_size(size_bytes: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def _aspect(w: int, h: int) -> str:
    from math import gcd
    g = gcd(w, h)
    return f"{w // g}:{h // g}"


def _parse_exif_dt(value: str) -> str | None:
    """Parse EXIF datetime string 'YYYY:MM:DD HH:MM:SS' to ISO 8601."""
    try:
        if isinstance(value, bytes):
            value = value.decode("utf-8", errors="replace")
        value = value.strip().strip("\x00")
        dt = datetime.strptime(value, "%Y:%m:%d %H:%M:%S")
        return dt.isoformat()
    except Exception:
        return value  # Return raw if unparseable


def _coerce(value):
    """Convert EXIF values to JSON-serializable types."""
    import fractions
    if hasattr(value, "numerator") and hasattr(value, "denominator"):
        # IFDRational
        try:
            return float(value)
        except Exception:
            return str(value)
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace").strip("\x00").strip()
    if isinstance(value, tuple):
        return [_coerce(v) for v in value]
    return value
