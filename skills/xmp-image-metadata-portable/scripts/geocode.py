#!/usr/bin/env python3
"""Reverse-geocode image GPS coordinates into reviewable XMP location candidates.

Never changes an image or JSON spec. Uses ExifTool's bundled offline GeoNames
database by default; online providers require explicit consent, a descriptive
user agent, and a local cache.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common  # noqa: E402  (local sibling module)

DEFAULT_ENDPOINT = "https://nominatim.openstreetmap.org/reverse"
MAPSCO_ENDPOINT = "https://geocode.maps.co/reverse"
ATTRIBUTION = "Data © OpenStreetMap contributors, ODbL 1.0. https://osm.org/copyright"
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def fail(message: str) -> None:
    raise ValueError(message)


def exiftool_cmd() -> list[str]:
    cmd = _common.find_exiftool()
    if not cmd:
        raise ValueError("ExifTool is required; run inspect_image.py --check")
    return cmd


def image_coordinates(image: str) -> tuple[float, float]:
    try:
        proc = subprocess.run(
            [
                *exiftool_cmd(),
                "-n",
                "-j",
                "-GPSLatitude",
                "-GPSLongitude",
                _common.safe_arg(image),
            ],
            text=True,
            capture_output=True,
            check=True,
            timeout=120,
        )
        data = json.loads(proc.stdout)[0]
    except (subprocess.CalledProcessError, json.JSONDecodeError, IndexError) as exc:
        raise ValueError(f"could not read GPS coordinates from {image}: {exc}") from exc
    if "GPSLatitude" not in data or "GPSLongitude" not in data:
        raise ValueError("the image has no numeric GPSLatitude/GPSLongitude metadata")
    return float(data["GPSLatitude"]), float(data["GPSLongitude"])


def validate_coordinates(lat: float, lon: float) -> None:
    if not -90 <= lat <= 90:
        fail("latitude must be between -90 and 90")
    if not -180 <= lon <= 180:
        fail("longitude must be between -180 and 180")


def validate_endpoint(endpoint: str) -> None:
    parsed = urlparse(endpoint)
    host = (parsed.hostname or "").lower()
    if parsed.scheme == "https":
        return
    if parsed.scheme == "http" and host in _LOCAL_HOSTS:
        return
    fail("use an https endpoint, or http only for an explicit localhost/127.0.0.1 host")


def cache_key(
    provider: str, endpoint: str, lat: float, lon: float, zoom: int, language: str
) -> str:
    return "|".join(
        (
            provider,
            endpoint.rstrip("/"),
            f"{lat:.7f}",
            f"{lon:.7f}",
            str(zoom),
            language or "",
        )
    )


def load_cache(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read cache {path}: {exc}") from exc


def save_cache(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def exiftool_reverse(lat: float, lon: float, geodir: str | None) -> dict[str, str]:
    """Use ExifTool's local Geolocation database; makes no network request."""
    command = list(exiftool_cmd())
    if geodir:
        command.extend(["-api", f"GeoDir={geodir}"])
    command.extend(["-api", f"geolocation={lat},{lon}"])
    try:
        proc = subprocess.run(
            command,
            text=True,
            capture_output=True,
            check=True,
            timeout=120,
        )
    except subprocess.CalledProcessError as exc:
        raise ValueError(
            f"ExifTool Geolocation lookup failed: {exc.stderr.strip() or exc}"
        ) from exc
    labels = {
        "Geolocation City": "city",
        "Geolocation Region": "state",
        "Geolocation Subregion": "subregion",
        "Geolocation Country": "country",
        "Geolocation Country Code": "country_code",
        "Geolocation Time Zone": "timezone",
        "Geolocation Feature Code": "feature_code",
        "Geolocation Feature Type": "feature_type",
        "Geolocation Population": "population",
        "Geolocation Position": "matched_position",
        "Geolocation Distance": "distance",
        "Geolocation Bearing": "bearing",
    }
    result: dict[str, str] = {}
    for line in proc.stdout.splitlines():
        if " : " in line:
            label, value = line.split(" : ", 1)
            if label.strip() in labels and value.strip():
                result[labels[label.strip()]] = value.strip()
    if not any(result.get(key) for key in ("city", "country", "country_code")):
        raise ValueError(
            "ExifTool returned no geolocation candidate; install/select its GeoLocation "
            "database, or use an approved online provider"
        )
    if result.get("country_code"):
        result["country_code"] = result["country_code"].upper()
    return result


def fetch(
    provider: str,
    endpoint: str,
    lat: float,
    lon: float,
    zoom: int,
    user_agent: str,
    language: str,
    email: str | None,
    api_key: str,
    timeout: float,
) -> dict[str, Any]:
    validate_endpoint(endpoint)
    query: dict[str, Any] = {
        "format": "jsonv2",
        "lat": lat,
        "lon": lon,
        "zoom": zoom,
        "addressdetails": 1,
    }
    if provider == "nominatim":
        query["layer"] = "address"
    if email:
        query["email"] = email
    headers = {"User-Agent": user_agent, "Accept": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    if language:
        headers["Accept-Language"] = language
    request = Request(endpoint + "?" + urlencode(query), headers=headers)
    try:
        with urlopen(
            request, timeout=timeout
        ) as response:  # noqa: S310 (scheme validated)
            payload = json.loads(response.read().decode("utf-8"))
            return dict(payload)
    except HTTPError as exc:
        raise ValueError(
            f"geocoding service returned HTTP {exc.code}; do not retry in a loop"
        ) from exc
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise ValueError(f"geocoding request failed: {exc}") from exc


def first(address: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = address.get(key)
        if value:
            return str(value)
    return ""


def candidate(
    response: dict[str, Any],
    lat: float,
    lon: float,
    endpoint: str,
    zoom: int,
    cache_status: str,
    provider: str,
) -> dict[str, Any]:
    address = response.get("address") or {}
    fields = {
        "city": first(
            address, "city", "town", "village", "municipality", "hamlet", "locality"
        ),
        "state": first(address, "state", "state_district", "region"),
        "country": str(address.get("country") or ""),
        "country_code": str(address.get("country_code") or "").upper(),
    }
    fields = {key: value for key, value in fields.items() if value}
    return {
        "status": "candidate_only",
        "warning": "Reverse geocoding returns a nearby OpenStreetMap object, not proof of where the image was captured or what it depicts. Review and confirm before copying any field into an XMP spec.",
        "privacy_note": "Exact coordinates were sent to the selected geocoding endpoint. Do not publish GPS or a precise address without approval.",
        "source": {
            "provider": provider,
            "endpoint": endpoint,
            "attribution": ATTRIBUTION,
        },
        "query": {
            "latitude": lat,
            "longitude": lon,
            "zoom": zoom,
            "cache_status": cache_status,
        },
        "suggested_spec_fields": fields,
        "location_created_candidate": fields,
        "provider_address": address,
        "display_name": response.get("display_name", ""),
        "retrieved_at": dt.datetime.now(dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat(),
    }


def exiftool_candidate(
    response: dict[str, str], lat: float, lon: float
) -> dict[str, Any]:
    fields = {
        key: response[key]
        for key in ("city", "state", "country", "country_code")
        if response.get(key)
    }
    return {
        "status": "candidate_only",
        "warning": "ExifTool selected the nearest matching GeoNames feature, not proof of where the image was captured or what it depicts. Review and confirm before copying any field into an XMP spec.",
        "privacy_note": "This lookup used ExifTool's local GeoLocation database; no coordinates were sent online.",
        "source": {
            "provider": "ExifTool GeoLocation database (GeoNames-based)",
            "endpoint": "offline",
        },
        "query": {
            "latitude": lat,
            "longitude": lon,
            "cache_status": "offline_exiftool",
        },
        "suggested_spec_fields": fields,
        "location_created_candidate": fields,
        "exiftool_geolocation": response,
        "retrieved_at": dt.datetime.now(dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat(),
    }


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Reverse-geocode GPS to reviewable XMP candidates; never writes an image or spec."
    )
    origin = ap.add_mutually_exclusive_group(required=True)
    origin.add_argument(
        "--image", help="Read numeric GPSLatitude/GPSLongitude with ExifTool."
    )
    origin.add_argument("--lat", type=float, help="WGS84 latitude; requires --lon.")
    ap.add_argument("--lon", type=float, help="WGS84 longitude; requires --lat.")
    ap.add_argument(
        "--provider", choices=("exiftool", "nominatim", "mapsco"), default="exiftool"
    )
    ap.add_argument(
        "--endpoint",
        help="Override the online reverse endpoint (self-hosted Nominatim, etc.).",
    )
    ap.add_argument(
        "--geodir", help="Optional ExifTool alternate GeoLocation database directory."
    )
    ap.add_argument(
        "--zoom", type=int, default=10, choices=range(0, 19), metavar="0..18"
    )
    ap.add_argument(
        "--language", default="", help="Optional Accept-Language, e.g. en or ka,en."
    )
    ap.add_argument(
        "--user-agent", help="Required descriptive user agent for a live request."
    )
    ap.add_argument("--email", help="Optional contact for the provider.")
    ap.add_argument(
        "--cache", help="Required writable local cache JSON for any live request."
    )
    ap.add_argument(
        "--api-key-env",
        default="GEOCODE_MAPS_CO_API_KEY",
        help="Environment variable holding mapsco's API key; never pass keys on the CLI.",
    )
    ap.add_argument(
        "--allow-network",
        action="store_true",
        help="Explicit acknowledgement that exact coordinates may be sent to the endpoint.",
    )
    ap.add_argument(
        "--response-file", help="Offline Nominatim JSON response for review/testing."
    )
    ap.add_argument(
        "--timeout", type=float, default=20, help="Network timeout seconds."
    )
    ap.add_argument("--out", help="Write candidate JSON here; otherwise print it.")
    args = ap.parse_args()
    try:
        if args.image:
            if args.lon is not None:
                fail("--lon may be used only with --lat")
            lat, lon = image_coordinates(args.image)
        else:
            if args.lon is None:
                fail("--lat requires --lon")
            lat, lon = args.lat, args.lon
        validate_coordinates(lat, lon)

        if args.response_file:
            with open(args.response_file, encoding="utf-8") as handle:
                response = json.load(handle)
            endpoint = args.endpoint or DEFAULT_ENDPOINT
            result = candidate(
                response,
                lat,
                lon,
                endpoint,
                args.zoom,
                "offline_response",
                "offline Nominatim-compatible response",
            )
        elif args.provider == "exiftool":
            result = exiftool_candidate(
                exiftool_reverse(lat, lon, args.geodir), lat, lon
            )
        else:
            if not args.allow_network:
                fail(
                    "network access is disabled: obtain user approval, then pass --allow-network"
                )
            if not args.user_agent:
                fail("--user-agent is required for a live request")
            if not args.cache:
                fail(
                    "--cache is required for a live request to prevent repeated queries"
                )
            endpoint = args.endpoint or (
                MAPSCO_ENDPOINT if args.provider == "mapsco" else DEFAULT_ENDPOINT
            )
            api_key = (
                os.environ.get(args.api_key_env, "")
                if args.provider == "mapsco"
                else ""
            )
            if args.provider == "mapsco" and not api_key:
                fail(
                    f"mapsco requires an API key in environment variable {args.api_key_env}"
                )
            cache_path = Path(args.cache)
            cache = load_cache(cache_path)
            key = cache_key(args.provider, endpoint, lat, lon, args.zoom, args.language)
            if key in cache:
                response = cache[key]["response"]
                status = "cache_hit"
            else:
                response = fetch(
                    args.provider,
                    endpoint,
                    lat,
                    lon,
                    args.zoom,
                    args.user_agent,
                    args.language,
                    args.email,
                    api_key,
                    args.timeout,
                )
                cache[key] = {
                    "cached_at": dt.datetime.now(dt.timezone.utc)
                    .replace(microsecond=0)
                    .isoformat(),
                    "response": response,
                }
                save_cache(cache_path, cache)
                status = "network_cached"
            result = candidate(
                response,
                lat,
                lon,
                endpoint,
                args.zoom,
                status,
                args.provider + " reverse API",
            )
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        ap.error(str(exc))
    text = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
