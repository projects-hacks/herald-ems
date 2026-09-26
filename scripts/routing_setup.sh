#!/usr/bin/env bash
# One-time road routing data for drive times and the ETA (herald/transport): the county's OpenStreetMap extract,
# prepared for the OSRM car profile. Runs offline afterwards; OSRM serves it on this box only (127.0.0.1).
#
#   scripts/routing_setup.sh             download (if missing) and prepare data/routing/<county>.osrm*
#   scripts/routing_setup.sh --refresh   download the latest extract again and re-prepare
#
# Source: openstreetmap.fr per-county extracts (Geofabrik's host is not reachable from this box), checked against
# the published md5. Preparing Santa Clara County takes ~10 s and peaks under 1 GB of memory (measured 2026-09-26).
# Map data (c) OpenStreetMap contributors, ODbL.
set -euo pipefail
cd "$(dirname "$0")/.."
COUNTY="${HERALD_ROUTING_COUNTY:-santa_clara}"
SOURCE="${HERALD_ROUTING_SOURCE:-https://download.openstreetmap.fr/extracts/north-america/us-west/california}"
IMAGE="${HERALD_OSRM_IMAGE:-ghcr.io/project-osrm/osrm-backend:v6.0.0}"
DIR="data/routing"
mkdir -p "$DIR"
if [ "${1:-}" = "--refresh" ] || [ ! -s "$DIR/$COUNTY.osm.pbf" ]; then
  echo "==> downloading $COUNTY road map"
  curl -sfL --max-time 900 -o "$DIR/$COUNTY.osm.pbf.part" "$SOURCE/$COUNTY.osm.pbf"
  curl -sfL --max-time 60 -o "$DIR/$COUNTY.osm.pbf.md5" "$SOURCE/$COUNTY.osm.pbf.md5"
  want="$(cut -d' ' -f1 "$DIR/$COUNTY.osm.pbf.md5")"; got="$(md5sum "$DIR/$COUNTY.osm.pbf.part" | cut -d' ' -f1)"
  [ "$want" = "$got" ] || { rm -f "$DIR/$COUNTY.osm.pbf.part"; echo "checksum mismatch ($got != $want)" >&2; exit 1; }
  mv "$DIR/$COUNTY.osm.pbf.part" "$DIR/$COUNTY.osm.pbf"
  curl -sfL --max-time 60 "$SOURCE/$COUNTY.state.txt" -o "$DIR/$COUNTY.state.txt" || true
fi
docker image inspect "$IMAGE" >/dev/null 2>&1 || docker pull "$IMAGE"
echo "==> preparing routes (OSRM car profile, multi-level Dijkstra)"
for step in "osrm-extract -p /opt/car.lua /data/$COUNTY.osm.pbf" "osrm-partition /data/$COUNTY.osrm" "osrm-customize /data/$COUNTY.osrm"; do
  docker run --rm -m 4g -v "$PWD/$DIR:/data" "$IMAGE" $step >/dev/null
done
echo "==> ready: $DIR/$COUNTY.osrm ($(grep -o 'timestamp=.*' "$DIR/$COUNTY.state.txt" 2>/dev/null || echo 'map date unknown'))"
