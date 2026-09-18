"""Port the editor's district authoring for town into the canonical region.

`world.get_district` resolves a room's district from
`region.properties.districts[*].members`, and `description_generator` uses it for
the room title and the room -> district -> region atmosphere chain. The editor's
districts work (5 districts, kind/shape/seed/colour, full membership) was
authored against the mirror, so canonical town.json still carries the legacy
block: one district, four rooms, the old `rooms` key. In play, town rooms
therefore show no district and take no district atmosphere.

This ports the district authoring and nothing else. It deliberately does **not**
touch the two files' differing room descriptions, exits or NPC placements: the
mirror rewrote 38 of the 46 rooms and is missing 8 that canonical has (including
`community_garden`, where the opening commission sends you), so adopting it
wholesale would delete content. Which prose wins is an editorial call, reported
rather than made.

    python toolkit/port_town_districts.py --check
    python toolkit/port_town_districts.py
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CANONICAL = REPOSITORY_ROOT / "content_sets" / "fantasy_frontier" / "data" / "regions" / "town.json"
MIRROR = REPOSITORY_ROOT / "mud-world-editor" / "data" / "regions" / "town.json"

# District fields worth carrying: the geometry/identity the editor's generators
# and the UI rely on, plus anything atmospheric an author added.
DISTRICT_FIELDS = ("name", "kind", "shape", "seed", "color", "members", "rooms")


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="report, change nothing")
    args = parser.parse_args()

    canonical = load(CANONICAL)
    mirror = load(MIRROR)
    canonical_rooms = set((canonical.get("rooms") or {}).keys())
    mirror_districts = (mirror.get("properties") or {}).get("districts") or {}
    legacy_districts = (canonical.get("properties") or {}).get("districts") or {}

    print("canonical: %d rooms, %d district(s)" % (len(canonical_rooms), len(legacy_districts)))
    print("mirror   : %d rooms, %d districts" % (len(mirror.get("rooms") or {}), len(mirror_districts)))

    ported: dict[str, dict] = {}
    dropped: list[str] = []
    for district_id, district in mirror_districts.items():
        if not isinstance(district, dict):
            continue
        entry = {key: district[key] for key in DISTRICT_FIELDS if key in district}
        members = list(entry.get("members") or entry.get("rooms") or [])
        # Union with whatever the canonical file already said about this
        # district: the mirror's lists are newer, but dropping a room the
        # shipped file assigned would lose information rather than update it.
        legacy = legacy_districts.get(district_id)
        if isinstance(legacy, dict):
            for room in legacy.get("members") or legacy.get("rooms") or []:
                if room not in members:
                    members.append(room)
        kept = [room for room in members if room in canonical_rooms]
        missing = [room for room in members if room not in canonical_rooms]
        entry["members"] = kept
        entry.pop("rooms", None)
        ported[district_id] = entry
        dropped.extend(missing)

        print("  %-16s %d members kept, %d not in canonical" % (district_id, len(kept), len(missing)))
        if missing:
            print("        not in canonical: %s" % ", ".join(missing[:8]))

    unassigned = sorted(canonical_rooms - {room for d in ported.values() for room in d["members"]})
    print("\ncanonical rooms in no district after the port: %d" % len(unassigned))
    for room in unassigned[:12]:
        print("    %s" % room)

    # Room-level tags the editor maintains alongside the district lists.
    tag_updates = 0
    for room_id, room in (mirror.get("rooms") or {}).items():
        if room_id not in canonical_rooms or not isinstance(room, dict):
            continue
        district_id = (room.get("properties") or {}).get("_district_id")
        if district_id:
            tag_updates += 1
    print("\nroom-level _district_id tags available from the mirror: %d" % tag_updates)

    if args.check:
        print("\n--check: nothing written.")
        return 0

    canonical.setdefault("properties", {})["districts"] = ported
    for room_id, room in (mirror.get("rooms") or {}).items():
        if room_id not in canonical_rooms or not isinstance(room, dict):
            continue
        district_id = (room.get("properties") or {}).get("_district_id")
        if not district_id:
            continue
        target = canonical["rooms"][room_id]
        target.setdefault("properties", {})["_district_id"] = district_id

    CANONICAL.write_text(json.dumps(canonical, indent=2) + "\n", encoding="utf-8")
    print("\nWrote %s" % CANONICAL.relative_to(REPOSITORY_ROOT))
    print("  districts: %d, tagged rooms: %d" % (len(ported), tag_updates))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
