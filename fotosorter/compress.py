"""Creates smaller copies of photos for storage, entirely alongside the
originals - nothing here ever deletes or overwrites a source file. A
compressed copy of DATA/<year>/<country>/SAVED/DSC_0001.JPG lands in a
sibling DATA/<year>/<country>/SAVED_compressed/DSC_0001.jpg.
"""
import io
import shutil
from pathlib import Path

from PIL import Image, ImageOps

from . import config

_ORIENTATION_TAG = 274


def compressed_sibling_dir(original: Path) -> Path:
    return original.parent.parent / f"{original.parent.name}_compressed"


def _encode(img: Image.Image, exif_bytes: bytes, quality: int, optimize: bool) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality, optimize=optimize, exif=exif_bytes)
    return buf.getvalue()


def _search_quality(img: Image.Image, exif_bytes: bytes, target_bytes: int, min_quality: int) -> tuple[int, bytes]:
    """Binary search for the highest JPEG quality whose encoded size is <=
    target_bytes. Returns (quality, encoded_bytes) - encoded_bytes may still
    be over target_bytes if even min_quality doesn't fit."""
    lo, hi = min_quality, 95
    best_quality, best_data = lo, _encode(img, exif_bytes, lo, optimize=False)
    if len(best_data) > target_bytes:
        return best_quality, best_data  # even the floor doesn't fit - caller may downscale

    while lo <= hi:
        mid = (lo + hi) // 2
        data = _encode(img, exif_bytes, mid, optimize=False)
        if len(data) <= target_bytes:
            best_quality, best_data = mid, data
            lo = mid + 1
        else:
            hi = mid - 1
    return best_quality, best_data


def compress_to_target(source: Path, target_bytes: int, allow_downscale: bool, settings: dict) -> dict:
    dest_dir = compressed_sibling_dir(source)
    source_size = source.stat().st_size

    if source_size <= target_bytes:
        dest = dest_dir / source.name
        if dest.exists():
            return {"skipped": True, "reason": "exists", "path": dest}
        dest_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)
        return {"skipped": True, "reason": "already small", "path": dest, "new_size": source_size}

    dest = dest_dir / (source.stem + ".jpg")
    if dest.exists():
        return {"skipped": True, "reason": "exists", "path": dest}

    with Image.open(source) as raw:
        exif = raw.getexif()
        img = ImageOps.exif_transpose(raw).convert("RGB")
    if _ORIENTATION_TAG in exif:
        del exif[_ORIENTATION_TAG]
    exif_bytes = exif.tobytes() if exif else b""

    min_quality = settings["compress_min_quality"]
    quality, data = _search_quality(img, exif_bytes, target_bytes, min_quality)

    if len(data) > target_bytes and allow_downscale:
        min_dim = settings["compress_min_dim"]
        while len(data) > target_bytes and max(img.size) > min_dim:
            new_size = (round(img.width * 0.85), round(img.height * 0.85))
            img = img.resize(new_size, Image.LANCZOS)
            quality, data = _search_quality(img, exif_bytes, target_bytes, min_quality)

    data = _encode(img, exif_bytes, quality, optimize=True)

    dest_dir.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    return {
        "skipped": False,
        "path": dest,
        "original_size": source_size,
        "new_size": len(data),
        "quality": quality,
        "dimensions": img.size,
        "hit_target": len(data) <= target_bytes,
    }


def iter_compressible_files(folder: Path, supported_extensions: set[str]):
    for path in Path(folder).rglob("*"):
        if not path.is_file() or path.suffix.lower() not in supported_extensions:
            continue
        if any(part.endswith("_compressed") for part in path.parts):
            continue
        yield path


def find_compressed_pairs(root: Path, supported_extensions: set[str]) -> list[tuple[Path, Path]]:
    """Recursively finds (original, compressed) pairs under root using the
    same '..._compressed' sibling-folder convention as compress_to_target.
    Matches by filename stem, since a recompressed file is always '.jpg' but
    an already-small file keeps its original extension."""
    pairs = []
    compressed_listing_cache: dict[Path, dict[str, Path]] = {}
    for orig in sorted(Path(root).rglob("*")):
        if not orig.is_file() or orig.suffix.lower() not in supported_extensions:
            continue
        if any(part.endswith("_compressed") for part in orig.parts):
            continue
        compressed_dir = compressed_sibling_dir(orig)
        if compressed_dir not in compressed_listing_cache:
            if compressed_dir.is_dir():
                compressed_listing_cache[compressed_dir] = {
                    p.stem.lower(): p for p in compressed_dir.iterdir() if p.is_file()
                }
            else:
                compressed_listing_cache[compressed_dir] = {}
        match = compressed_listing_cache[compressed_dir].get(orig.stem.lower())
        if match:
            pairs.append((orig, match))
    return pairs


def compress_folder(folder: Path, target_bytes: int, allow_downscale: bool, settings: dict, progress=None) -> dict:
    """Batch-compress every photo under folder (skipping '..._compressed'
    directories). Used by the "Compress folder..." tool."""
    files = list(iter_compressible_files(folder, config.SUPPORTED_EXTENSIONS))
    compressed, copied, already_done, errors = 0, 0, 0, 0
    original_bytes, new_bytes = 0, 0

    for i, path in enumerate(files, start=1):
        try:
            result = compress_to_target(path, target_bytes, allow_downscale, settings)
            if result.get("reason") == "exists":
                already_done += 1
            elif result["skipped"]:
                copied += 1
                new_bytes += result["new_size"]
                original_bytes += result["new_size"]
            else:
                compressed += 1
                original_bytes += result["original_size"]
                new_bytes += result["new_size"]
        except Exception:
            errors += 1
        if progress:
            progress("compress", i, len(files))

    return {
        "total": len(files), "compressed": compressed, "copied": copied,
        "already_done": already_done, "errors": errors,
        "original_bytes": original_bytes, "new_bytes": new_bytes,
    }
