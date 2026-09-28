"""Load/save tunable settings and the manual date-range -> location mapping."""
import json
from datetime import date
from pathlib import Path

DEFAULT_SETTINGS = {
    # Photos taken within this many seconds of each other are candidates for
    # the same duplicate/burst group.
    "time_window_seconds": 300,
    # Max perceptual-hash Hamming distance (0-64) between two time-adjacent
    # photos to link them into the same group. Raised from an initial 10
    # after real-world data showed even photos 0-10s apart (near-certainly
    # the same burst) have a median distance of ~14 and 75th percentile
    # ~24 - real handheld vacation photography has enough natural motion
    # that a strict threshold fragments genuine bursts. 24 was calibrated
    # against the actual distribution of adjacent-photo distances.
    "phash_hamming_threshold": 24,
    # A group larger than this (a long genuinely-continuous burst) is split
    # into consecutive time-ordered chunks of at most this size, since a
    # huge group is impractical to visually compare even with scrolling.
    "max_group_size": 12,
    # Variance-of-Laplacian below this is considered blurry. This is camera/
    # resolution dependent - tune it in the settings dialog if it's too
    # aggressive or too lax for your camera. Lowered from an initial 80.0
    # after real-world use showed ~90% false positives (photos shot through
    # glass/fences/telescopes are legitimately soft but not "blurry") - 15.0
    # was calibrated against the actual flagged-photo distribution to match
    # roughly the truly-unusable ~10%.
    "sharpness_threshold": 15.0,
    # Mean luminance (0-255) below/above which a photo is flagged as too
    # dark / too bright.
    "exposure_dark_mean_threshold": 25.0,
    "exposure_bright_mean_threshold": 235.0,
    # Fraction of pixels clipped at pure black or pure white above which a
    # photo is flagged as badly exposed.
    "exposure_clip_fraction_threshold": 0.55,
    # Longest edge (px) used for quality metrics and for the zoom source
    # image - keeps memory/CPU bounded without sacrificing visible detail.
    "zoom_source_max_dim": 2800,
    "zoom_max_level": 6,
    # Review grid never uses more columns than this - beyond it, photos
    # stack into extra scrollable rows instead of columns getting narrower.
    "max_grid_columns": 3,
    # Compression: creates a smaller copy of a saved/discarded photo in a
    # sibling "..._compressed" folder - never touches the original.
    "compress_target_kb": 1024,
    "compress_allow_downscale": True,
    "compress_min_quality": 35,
    "compress_min_dim": 1600,
    "compress_on_save": False,
}

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".heic", ".heif"}


def load_settings(config_dir: Path) -> dict:
    path = Path(config_dir) / "settings.json"
    settings = dict(DEFAULT_SETTINGS)
    if path.exists():
        try:
            saved = json.loads(path.read_text())
            settings.update(saved)
        except (json.JSONDecodeError, OSError):
            pass
    else:
        save_settings(config_dir, settings)
    return settings


def save_settings(config_dir: Path, settings: dict) -> None:
    path = Path(config_dir) / "settings.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings, indent=2))


def load_location_rules(config_dir: Path) -> list[dict]:
    path = Path(config_dir) / "location_rules.json"
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return []


def save_location_rules(config_dir: Path, rules: list[dict]) -> None:
    path = Path(config_dir) / "location_rules.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rules, indent=2))


def lookup_location(rules: list[dict], taken_date: date) -> str | None:
    """Return the label of the first rule whose [start, end] range covers taken_date."""
    for rule in rules:
        start = date.fromisoformat(rule["start"])
        end = date.fromisoformat(rule["end"])
        if start <= taken_date <= end:
            return rule["label"]
    return None
