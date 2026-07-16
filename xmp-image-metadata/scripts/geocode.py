#!/usr/bin/env python3
"""Reverse-geocode image GPS coordinates into reviewable XMP location candidates.

This script never changes an image or JSON spec. It uses ExifTool's bundled
GeoNames-based database offline by default; online providers require explicit
consent, a descriptive user agent, and a local cache.
"""
import argparse
import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

DEFAULT_ENDPOINT = "https://nominatim.openstreetmap.org/reverse"
MAPSCO_ENDPOINT = "https://geocode.maps.co/reverse"
ATTRIBUTION = "Data © OpenStreetMap contributors, ODbL 1.0. https://osm.org/copyright"

def fail(message):
    raise ValueError(message)

def exiftool_command():
    return os.environ.get("ET_EXIFTOOL") or "exiftool"

def image_coordinates(image):
    try:
        run = subprocess.run(
            [exiftool_command(), "-n", "-j", "-GPSLatitude", "-GPSLongitude", image],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True,
        )
        data = json.loads(run.stdout)[0]
    except FileNotFoundError as exc:
        raise ValueError("ExifTool is required to read GPS from --image; run inspect_image.py --check") from exc
    except (subprocess.CalledProcessError, json.JSONDecodeError, IndexError) as exc:
        raise ValueError(f"could not read GPS coordinates from {image}: {exc}") from exc
    if "GPSLatitude" not in data or "GPSLongitude" not in data:
        raise ValueError("the image has no numeric GPSLatitude/GPSLongitude metadata")
    return float(data["GPSLatitude"]), float(data["GPSLongitude"])

def validate_coordinates(lat, lon):
    if not -90 <= lat <= 90:
        fail("latitude must be between -90 and 90")
    if not -180 <= lon <= 180:
        fail("longitude must be between -180 and 180")

def cache_key(provider, endpoint, lat, lon, zoom, language):
    return "|".join((provider, endpoint.rstrip("/"), f"{lat:.7f}", f"{lon:.7f}", str(zoom), language or ""))

def load_cache(path):
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read cache {path}: {exc}") from exc

def save_cache(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

def exiftool_reverse(lat, lon, geodir):
    """Use ExifTool's local Geolocation database; it makes no network request."""
    command = [exiftool_command()]
    if geodir:
        command.extend(["-api", f"GeoDir={geodir}"])
    command.extend(["-api", f"geolocation={lat},{lon}"])
    try:
        run = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    except FileNotFoundError as exc:
        raise ValueError("ExifTool is required for --provider exiftool; run inspect_image.py --check") from exc
    except subprocess.CalledProcessError as exc:
        raise ValueError(f"ExifTool Geolocation lookup failed: {exc.stderr.strip() or exc}") from exc
    labels = {
        "Geolocation City": "city", "Geolocation Region": "state",
        "Geolocation Subregion": "subregion", "Geolocation Country": "country",
        "Geolocation Country Code": "country_code", "Geolocation Time Zone": "timezone",
        "Geolocation Feature Code": "feature_code", "Geolocation Feature Type": "feature_type",
        "Geolocation Population": "population", "Geolocation Position": "matched_position",
        "Geolocation Distance": "distance", "Geolocation Bearing": "bearing",
    }
    result = {}
    for line in run.stdout.splitlines():
        if " : " in line:
            label, value = line.split(" : ", 1)
            if label.strip() in labels and value.strip():
                result[labels[label.strip()]] = value.strip()
    if not any(result.get(key) for key in ("city", "country", "country_code")):
        raise ValueError("ExifTool returned no geolocation candidate; install or select its GeoLocation database, or use an approved online provider")
    if result.get("country_code"):
        result["country_code"] = result["country_code"].upper()
    return result

def fetch(provider, endpoint, lat, lon, zoom, user_agent, language, email, api_key, timeout):
    if not endpoint.startswith("https://") and "localhost" not in endpoint and "127.0.0.1" not in endpoint:
        fail("use an HTTPS endpoint, or an explicitly local self-hosted endpoint")
    query = {"format": "jsonv2", "lat": lat, "lon": lon, "zoom": zoom, "addressdetails": 1}
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
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise ValueError(f"geocoding service returned HTTP {exc.code}; do not retry in a loop") from exc
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise ValueError(f"geocoding request failed: {exc}") from exc

def first(address, *keys):
    for key in keys:
        value = address.get(key)
        if value:
            return value
    return ""

def candidate(response, lat, lon, endpoint, zoom, cache_status, provider):
    address = response.get("address") or {}
    country_code = str(address.get("country_code") or "").upper()
    fields = {
        "city": first(address, "city", "town", "village", "municipality", "hamlet", "locality"),
        "state": first(address, "state", "state_district", "region"),
        "country": str(address.get("country") or ""),
        "country_code": country_code,
    }
    fields = {key: value for key, value in fields.items() if value}
    return {
        "status": "candidate_only",
        "warning": "Reverse geocoding returns a nearby OpenStreetMap object, not proof of where the image was captured or what it depicts. Review and confirm before copying any field into an XMP spec.",
        "privacy_note": "Exact coordinates were sent to the selected geocoding endpoint. Do not publish GPS or a precise address without approval.",
        "source": {"provider": provider, "endpoint": endpoint, "attribution": ATTRIBUTION},
        "query": {"latitude": lat, "longitude": lon, "zoom": zoom, "cache_status": cache_status},
        "suggested_spec_fields": fields,
        "location_created_candidate": fields,
        "provider_address": address,
        "display_name": response.get("display_name", ""),
        "retrieved_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
    }

def exiftool_candidate(response, lat, lon):
    fields = {key: response[key] for key in ("city", "state", "country", "country_code") if response.get(key)}
    return {
        "status": "candidate_only",
        "warning": "ExifTool selected the nearest matching GeoNames feature, not proof of where the image was captured or what it depicts. Review and confirm before copying any field into an XMP spec.",
        "privacy_note": "This lookup used ExifTool's local GeoLocation database; no coordinates were sent online.",
        "source": {"provider": "ExifTool GeoLocation database (GeoNames-based)", "endpoint": "offline"},
        "query": {"latitude": lat, "longitude": lon, "cache_status": "offline_exiftool"},
        "suggested_spec_fields": fields,
        "location_created_candidate": fields,
        "exiftool_geolocation": response,
        "retrieved_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
    }

def main():
    ap = argparse.ArgumentParser(description="Reverse-geocode GPS to reviewable XMP candidates; never writes an image or spec.")
    origin = ap.add_mutually_exclusive_group(required=True)
    origin.add_argument("--image", help="Read numeric GPSLatitude/GPSLongitude with ExifTool.")
    origin.add_argument("--lat", type=float, help="WGS84 latitude; requires --lon.")
    ap.add_argument("--lon", type=float, help="WGS84 longitude; requires --lat.")
    ap.add_argument("--provider", choices=("exiftool", "nominatim", "mapsco"), default="exiftool", help="Offline ExifTool database by default; online providers are opt-in.")
    ap.add_argument("--endpoint", help="Override the online reverse endpoint, for example a self-hosted Nominatim instance.")
    ap.add_argument("--geodir", help="Optional ExifTool alternate GeoLocation database directory (offline provider only).")
    ap.add_argument("--zoom", type=int, default=10, choices=range(0, 19), metavar="0..18", help="10 (city) by default; 18 can reveal a precise address.")
    ap.add_argument("--language", default="", help="Optional Accept-Language, for example en or ka,en.")
    ap.add_argument("--user-agent", help="Required descriptive application/user agent for a live request.")
    ap.add_argument("--email", help="Optional contact for the provider; avoid personal email unless approved.")
    ap.add_argument("--cache", help="Required writable local cache JSON for any live request.")
    ap.add_argument("--api-key-env", default="GEOCODE_MAPS_CO_API_KEY", help="Environment variable holding mapsco's API key; never pass keys on the command line.")
    ap.add_argument("--allow-network", action="store_true", help="Explicit acknowledgement that the exact coordinates may be sent to the endpoint.")
    ap.add_argument("--response-file", help="Offline Nominatim JSON response for review/testing; makes no network request.")
    ap.add_argument("--timeout", type=float, default=20, help="Network timeout seconds.")
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
            response = json.loads(Path(args.response_file).read_text(encoding="utf-8"))
            status = "offline_response"
            endpoint = args.endpoint or DEFAULT_ENDPOINT
            result = candidate(response, lat, lon, endpoint, args.zoom, status, "offline Nominatim-compatible response")
        elif args.provider == "exiftool":
            result = exiftool_candidate(exiftool_reverse(lat, lon, args.geodir), lat, lon)
        else:
            if not args.allow_network:
                fail("network access is disabled: obtain user approval, then pass --allow-network")
            if not args.user_agent:
                fail("--user-agent is required for a live request (for example: 'my-metadata-tool/1.0 (contact: team@example.org)')")
            if not args.cache:
                fail("--cache is required for a live request to prevent repeated queries")
            endpoint = args.endpoint or (MAPSCO_ENDPOINT if args.provider == "mapsco" else DEFAULT_ENDPOINT)
            api_key = os.environ.get(args.api_key_env, "") if args.provider == "mapsco" else ""
            if args.provider == "mapsco" and not api_key:
                fail(f"mapsco requires an API key in environment variable {args.api_key_env}; do not put it in a command or spec")
            cache_path = Path(args.cache)
            cache = load_cache(cache_path)
            key = cache_key(args.provider, endpoint, lat, lon, args.zoom, args.language)
            if key in cache:
                response = cache[key]["response"]
                status = "cache_hit"
            else:
                response = fetch(args.provider, endpoint, lat, lon, args.zoom, args.user_agent, args.language, args.email, api_key, args.timeout)
                cache[key] = {"cached_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(), "response": response}
                save_cache(cache_path, cache)
                status = "network_cached"
            result = candidate(response, lat, lon, endpoint, args.zoom, status, args.provider + " reverse API")
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        ap.error(str(exc))
    text = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        sys.stdout.write(text)

if __name__ == "__main__":
    main()
