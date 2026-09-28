"""Perceptual-hash + time-window clustering of near-duplicate/burst photos."""
import imagehash
from PIL import Image


def compute_phash(img: Image.Image) -> str:
    return str(imagehash.phash(img))


def hamming_distance(hash_a: str, hash_b: str) -> int:
    return imagehash.hex_to_hash(hash_a) - imagehash.hex_to_hash(hash_b)


class _UnionFind:
    def __init__(self, ids):
        self.parent = {i: i for i in ids}

    def find(self, x):
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[ra] = rb


def group_photos(
    records: list[dict], time_window_seconds: int, hash_threshold: int, max_group_size: int | None = None,
) -> list[list[int]]:
    """records: list of {"id": int, "date_taken": datetime, "phash": str}.
    Two time-CONSECUTIVE photos are linked if they're within the time
    window and their hashes are close enough; linked photos transitively
    join one group, so a whole burst joins together even though only
    neighbors are compared directly.

    Only comparing immediate neighbors (not every pair within the window of
    a given anchor photo) matters: comparing every later photo against a
    fixed anchor adds edges that don't reflect real similarity chains, and
    on real vacation photos that reliably "chains" an entire steadily-shot
    session - tens or hundreds of unrelated photos - into one runaway
    cluster, while simultaneously still fragmenting a genuine short burst
    the moment any single adjacent pair happens to vary a bit more (a
    person moving, a slight pan). Comparing neighbors only avoids the first
    problem; being reasonably lenient on hash_threshold avoids the second.

    If a resulting group is still bigger than max_group_size (a long
    genuinely-continuous burst), it's split into consecutive time-ordered
    chunks of at most that size - a big group is impractical to visually
    compare in one screen even with scrolling."""
    records = sorted(records, key=lambda r: r["date_taken"])
    ids = [r["id"] for r in records]
    uf = _UnionFind(ids)

    n = len(records)
    for i in range(n - 1):
        delta = (records[i + 1]["date_taken"] - records[i]["date_taken"]).total_seconds()
        if delta <= time_window_seconds and hamming_distance(records[i]["phash"], records[i + 1]["phash"]) <= hash_threshold:
            uf.union(records[i]["id"], records[i + 1]["id"])

    clusters: dict[int, list[int]] = {}
    for r in records:
        root = uf.find(r["id"])
        clusters.setdefault(root, []).append(r["id"])
    groups = list(clusters.values())

    if not max_group_size:
        return groups

    order = {r["id"]: idx for idx, r in enumerate(records)}
    final_groups = []
    for group in groups:
        if len(group) <= max_group_size:
            final_groups.append(group)
            continue
        group.sort(key=lambda file_id: order[file_id])
        for start in range(0, len(group), max_group_size):
            final_groups.append(group[start:start + max_group_size])
    return final_groups
