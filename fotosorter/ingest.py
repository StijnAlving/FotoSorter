"""Orchestrates the pipeline: scan RAW/ -> metadata+quality -> group -> file.

Called on every app launch (`sync`). Every step only touches rows in the
relevant DB status, so it's safe to run repeatedly as more photos land in
RAW/ between sessions. Note: run it after an import/copy finishes rather
than while a card is still copying - photos that arrive in a later run
can't retroactively join a burst that was already auto-saved as a single.
"""
import json
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

from . import compress, config, db, geocode, metadata, quality, similarity


def iter_supported_files(raw_dirs: list[Path]):
    for raw_dir in raw_dirs:
        for path in Path(raw_dir).rglob("*"):
            if path.is_file() and path.suffix.lower() in config.SUPPORTED_EXTENSIONS:
                yield path


def _move_unique(src: Path, dest_dir: Path) -> Path:
    dest = dest_dir / src.name
    if dest.exists():
        i = 1
        while dest.exists():
            dest = dest_dir / f"{src.stem}_{i}{src.suffix}"
            i += 1
    shutil.move(str(src), str(dest))
    return dest


def scan_new_files(conn: sqlite3.Connection, raw_dirs: list[Path], progress=None) -> int:
    known = db.known_paths(conn)
    paths = list(iter_supported_files(raw_dirs))
    added = 0
    for i, path in enumerate(paths, start=1):
        if str(path) not in known:
            try:
                db.insert_new_file(conn, str(path), metadata.content_hash(path))
                added += 1
            except sqlite3.IntegrityError:
                pass
        if progress and paths:
            progress("scan", i, len(paths))
    return added


def process_new_files(conn: sqlite3.Connection, settings: dict, data_dir: Path, progress=None) -> dict:
    rows = db.get_by_status(conn, "new")
    low_quality, ok = 0, 0
    for i, row in enumerate(rows, start=1):
        path = Path(row["path"])
        try:
            meta = metadata.read_exif(path)
            img = metadata.load_normalized(path, max_dim=settings["zoom_source_max_dim"])
            gray = quality.to_gray_array(img)
            sharpness = quality.compute_sharpness(gray)
            exposure = quality.compute_exposure(gray)
            is_low_quality, reasons = quality.classify_quality(sharpness, exposure, settings)
            phash = similarity.compute_phash(img)
        except Exception as exc:  # corrupt/unsupported file - don't crash the whole batch
            db.update_file(conn, row["id"], status="error", error=str(exc))
            if progress:
                progress("analyze", i, len(rows))
            continue

        db.update_file(
            conn, row["id"],
            date_taken=meta["date_taken"].isoformat(),
            date_is_estimated=int(meta["date_is_estimated"]),
            width=meta["width"], height=meta["height"],
            camera_make=meta["camera_make"], camera_model=meta["camera_model"],
            gps_lat=meta["gps_lat"], gps_lon=meta["gps_lon"],
            phash=phash, sharpness=sharpness,
            quality_flag="low_quality" if is_low_quality else "ok",
            quality_reasons=json.dumps(reasons),
        )

        if is_low_quality:
            dest_dir = Path(data_dir) / str(meta["date_taken"].year) / "lowQuality"
            dest_dir.mkdir(parents=True, exist_ok=True)
            new_path = _move_unique(path, dest_dir)
            db.update_file(conn, row["id"], path=str(new_path), status="done")
            low_quality += 1
        else:
            db.update_file(conn, row["id"], status="pending_group")
            ok += 1
        if progress:
            progress("analyze", i, len(rows))
    return {"low_quality": low_quality, "pending_group": ok}


def recheck_low_quality(conn: sqlite3.Connection, settings: dict, progress=None) -> dict:
    """Re-classifies already-filed lowQuality photos against the current
    sharpness_threshold, without re-decoding images: sharpness is already
    stored from the original pass, and since exposure thresholds aren't
    being changed here, a photo's original exposure-based reasons (if any)
    are still valid as-is. (If exposure thresholds are ever tuned too, this
    would need to re-decode and recompute exposure instead of trusting the
    stored reasons.) Photos that no longer qualify are flipped back to
    'pending_group' - the file itself isn't moved yet, that happens the
    next time run_grouping/finalize_file runs over pending_group rows."""
    rows = conn.execute(
        "SELECT * FROM files WHERE quality_flag = 'low_quality' AND status = 'done'"
    ).fetchall()
    recovered, still_flagged = 0, 0
    for i, row in enumerate(rows, start=1):
        reasons = json.loads(row["quality_reasons"]) if row["quality_reasons"] else []
        has_exposure_issue = any("exposed" in r or "clipped" in r for r in reasons)
        still_blurry = row["sharpness"] is not None and row["sharpness"] < settings["sharpness_threshold"]
        if has_exposure_issue or still_blurry:
            still_flagged += 1
        else:
            db.update_file(conn, row["id"], quality_flag="ok", status="pending_group", quality_reasons="[]")
            recovered += 1
        if progress:
            progress("recheck", i, len(rows))
    return {"checked": len(rows), "recovered": recovered, "still_flagged": still_flagged}


def finalize_file(conn: sqlite3.Connection, row: sqlite3.Row, data_dir: Path, config_dir: Path, kept: bool, settings: dict | None = None) -> dict:
    """Resolve year/country and move the file into SAVED or DISCARDED.
    Returns {"filed": False, "compressed": False} (and parks the row as
    needs_location) if country can't be resolved yet - the caller should
    prompt for a location rule. "compressed" reports whether a compressed
    sibling copy now exists, so callers can tell the user what actually
    happened rather than leaving it ambiguous."""
    taken = datetime.fromisoformat(row["date_taken"])
    year = taken.year
    country = geocode.resolve_country(row["gps_lat"], row["gps_lon"], taken, config_dir)
    if country is None:
        db.update_file(conn, row["id"], status="needs_location", year=year, kept=int(kept))
        return {"filed": False, "compressed": False}

    subfolder = "SAVED" if kept else "DISCARDED"
    dest_dir = Path(data_dir) / str(year) / country / subfolder
    dest_dir.mkdir(parents=True, exist_ok=True)
    new_path = _move_unique(Path(row["path"]), dest_dir)
    db.update_file(conn, row["id"], path=str(new_path), status="done", year=year, country=country, kept=int(kept))

    compressed = False
    if settings and settings.get("compress_on_save"):
        compress.compress_to_target(
            new_path, settings["compress_target_kb"] * 1024, settings["compress_allow_downscale"], settings,
        )
        compressed = True
    return {"filed": True, "compressed": compressed}


def run_grouping(conn: sqlite3.Connection, settings: dict, data_dir: Path, config_dir: Path, progress=None) -> dict:
    rows = db.get_by_status(conn, "pending_group")
    if not rows:
        return {"auto_saved": 0, "groups_created": 0}

    records = [{"id": r["id"], "date_taken": datetime.fromisoformat(r["date_taken"]), "phash": r["phash"]} for r in rows]
    groups = similarity.group_photos(
        records, settings["time_window_seconds"], settings["phash_hamming_threshold"], settings.get("max_group_size"),
    )
    row_by_id = {r["id"]: r for r in rows}

    auto_saved, groups_created = 0, 0
    for i, group_ids in enumerate(groups, start=1):
        if len(group_ids) == 1:
            finalize_file(conn, row_by_id[group_ids[0]], data_dir, config_dir, kept=True, settings=settings)
            auto_saved += 1
        else:
            db.create_group(conn, group_ids)
            groups_created += 1
        if progress:
            progress("auto_save", i, len(groups))
    return {"auto_saved": auto_saved, "groups_created": groups_created}


def resolve_pending_locations(conn: sqlite3.Connection, data_dir: Path, config_dir: Path, settings: dict | None = None, progress=None) -> int:
    rows = db.get_needs_location(conn)
    resolved = 0
    for i, row in enumerate(rows, start=1):
        if finalize_file(conn, row, data_dir, config_dir, kept=bool(row["kept"]), settings=settings)["filed"]:
            resolved += 1
        if progress:
            progress("locate", i, len(rows))
    return resolved


def resolve_group_choice(conn: sqlite3.Connection, group_id: int, kept_ids: set[int], data_dir: Path, config_dir: Path, settings: dict | None = None, progress=None) -> dict:
    members = db.get_group_members(conn, group_id)
    kept_count, discarded_count, compressed_count = 0, 0, 0
    for i, row in enumerate(members, start=1):
        is_kept = row["id"] in kept_ids
        result = finalize_file(conn, row, data_dir, config_dir, kept=is_kept, settings=settings)
        if result["filed"]:
            if is_kept:
                kept_count += 1
            else:
                discarded_count += 1
            if result["compressed"]:
                compressed_count += 1
        if progress:
            progress("save", i, len(members))
    db.mark_group_resolved(conn, group_id)
    return {"kept": kept_count, "discarded": discarded_count, "compressed": compressed_count, "total": len(members)}


def sync(conn: sqlite3.Connection, raw_dirs: list[Path], data_dir: Path, config_dir: Path, settings: dict, progress=None) -> dict:
    """Run the full incremental pipeline once. Safe to call on every launch."""
    added = scan_new_files(conn, raw_dirs, progress)
    processed = process_new_files(conn, settings, data_dir, progress)
    grouped = run_grouping(conn, settings, data_dir, config_dir, progress)
    resolved = resolve_pending_locations(conn, data_dir, config_dir, settings, progress)
    return {"new_files_found": added, **processed, **grouped, "locations_resolved": resolved}
