"""EXIF extraction and normalized image loading, shared by JPEG/PNG/HEIC."""
import hashlib
from datetime import datetime
from pathlib import Path

import pillow_heif
from PIL import ExifTags, Image, ImageOps

pillow_heif.register_heif_opener()

_DATE_TAGS = ("DateTimeOriginal", "DateTimeDigitized", "DateTime")
_GPS_TAG_ID = next(k for k, v in ExifTags.TAGS.items() if v == "GPSInfo")


def content_hash(path: Path) -> str:
    """Cheap fingerprint (size + partial content) - good enough to spot exact
    re-imports of the same file without hashing entire multi-MB photos."""
    h = hashlib.md5()
    size = path.stat().st_size
    h.update(str(size).encode())
    with path.open("rb") as f:
        h.update(f.read(65536))
        if size > 65536:
            f.seek(-65536, 2)
            h.update(f.read(65536))
    return h.hexdigest()


def _to_degrees(value) -> float:
    d, m, s = (float(x) for x in value)
    return d + m / 60.0 + s / 3600.0


def read_exif(path: Path) -> dict:
    """Returns date_taken (datetime|None), date_is_estimated (bool),
    gps (tuple|None), make/model (str|None), width/height (int)."""
    result = {
        "date_taken": None,
        "date_is_estimated": True,
        "gps_lat": None,
        "gps_lon": None,
        "camera_make": None,
        "camera_model": None,
        "width": None,
        "height": None,
    }
    with Image.open(path) as img:
        result["width"], result["height"] = img.size
        exif = img.getexif()
        tags = {ExifTags.TAGS.get(k, k): v for k, v in exif.items()}
        result["camera_make"] = tags.get("Make", "").strip() or None
        result["camera_model"] = tags.get("Model", "").strip() or None

        for tag in _DATE_TAGS:
            raw = tags.get(tag)
            if raw:
                try:
                    result["date_taken"] = datetime.strptime(raw, "%Y:%m:%d %H:%M:%S")
                    result["date_is_estimated"] = tag != "DateTimeOriginal"
                    break
                except ValueError:
                    continue

        gps_ifd = exif.get_ifd(_GPS_TAG_ID)
        if gps_ifd:
            gps = {ExifTags.GPSTAGS.get(k, k): v for k, v in gps_ifd.items()}
            lat = gps.get("GPSLatitude")
            lon = gps.get("GPSLongitude")
            if lat and lon:
                lat_deg = _to_degrees(lat)
                lon_deg = _to_degrees(lon)
                if gps.get("GPSLatitudeRef") == "S":
                    lat_deg = -lat_deg
                if gps.get("GPSLongitudeRef") == "W":
                    lon_deg = -lon_deg
                result["gps_lat"], result["gps_lon"] = lat_deg, lon_deg

    if result["date_taken"] is None:
        result["date_taken"] = datetime.fromtimestamp(path.stat().st_mtime)
        result["date_is_estimated"] = True

    return result


def load_normalized(path: Path, max_dim: int | None = None) -> Image.Image:
    """Open an image, apply EXIF orientation, and optionally downscale so
    the longest edge is at most max_dim. Used for quality metrics and as the
    zoom source (full native resolution is not decoded for every cell)."""
    img = Image.open(path)
    img = ImageOps.exif_transpose(img)
    img = img.convert("RGB")
    if max_dim and max(img.size) > max_dim:
        img.thumbnail((max_dim, max_dim), Image.LANCZOS)
    return img
