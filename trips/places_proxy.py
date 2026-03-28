from __future__ import annotations

import hashlib
import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Final, TypedDict, cast

from django.conf import settings
from django.core.cache import cache

PLACES_AUTOCOMPLETE_ENDPOINT: Final[str] = "https://places.googleapis.com/v1/places:autocomplete"
PLACES_DETAILS_ENDPOINT_TEMPLATE: Final[str] = "https://places.googleapis.com/v1/{place_name}"

DEFAULT_TIMEOUT_SECONDS: Final[float] = 4.5
DEFAULT_AUTOCOMPLETE_LIMIT: Final[int] = 6
DEFAULT_AUTOCOMPLETE_CACHE_TTL_SECONDS: Final[int] = 120
DEFAULT_DETAILS_CACHE_TTL_SECONDS: Final[int] = 86_400
MAX_QUERY_LENGTH: Final[int] = 160
MAX_SESSION_TOKEN_LENGTH: Final[int] = 128

AUTOCOMPLETE_FIELD_MASK: Final[str] = (
    "suggestions.placePrediction.placeId,"
    "suggestions.placePrediction.place,"
    "suggestions.placePrediction.text.text,"
    "suggestions.placePrediction.structuredFormat.mainText.text,"
    "suggestions.placePrediction.structuredFormat.secondaryText.text"
)
DETAILS_FIELD_MASK: Final[str] = (
    "id,displayName.text,formattedAddress,location,viewport,addressComponents.longText,addressComponents.types"
)


class PlacesProxyError(RuntimeError):
    def __init__(self, message: str, *, code: str, status_code: int = 502) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code


class PlaceViewport(TypedDict):
    south: float
    west: float
    north: float
    east: float


class DestinationSuggestion(TypedDict):
    place_id: str
    label: str
    main_text: str
    secondary_text: str


class DestinationDetails(TypedDict):
    place_id: str
    label: str
    latitude: float
    longitude: float
    viewport: PlaceViewport | None


def configured_places_api_key() -> str:
    direct_key = str(getattr(settings, "GOOGLE_PLACES_API_KEY", "") or "").strip()
    if direct_key:
        return direct_key
    return str(getattr(settings, "GOOGLE_MAPS_API_KEY", "") or "").strip()


def places_timeout_seconds() -> float:
    raw = getattr(settings, "TAPNE_TRIP_DESTINATION_PROXY_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS)
    try:
        parsed = float(raw)
    except (TypeError, ValueError):
        parsed = DEFAULT_TIMEOUT_SECONDS
    if parsed <= 0:
        return DEFAULT_TIMEOUT_SECONDS
    return min(parsed, 10.0)


def places_autocomplete_limit() -> int:
    raw = getattr(settings, "TAPNE_TRIP_DESTINATION_AUTOCOMPLETE_LIMIT", DEFAULT_AUTOCOMPLETE_LIMIT)
    try:
        parsed = int(raw)
    except (TypeError, ValueError):
        parsed = DEFAULT_AUTOCOMPLETE_LIMIT
    if parsed < 1:
        return DEFAULT_AUTOCOMPLETE_LIMIT
    return min(parsed, 10)


def places_autocomplete_cache_ttl_seconds() -> int:
    raw = getattr(
        settings,
        "TAPNE_TRIP_DESTINATION_AUTOCOMPLETE_CACHE_TTL_SECONDS",
        DEFAULT_AUTOCOMPLETE_CACHE_TTL_SECONDS,
    )
    try:
        parsed = int(raw)
    except (TypeError, ValueError):
        parsed = DEFAULT_AUTOCOMPLETE_CACHE_TTL_SECONDS
    if parsed < 0:
        return 0
    return min(parsed, 3_600)


def places_details_cache_ttl_seconds() -> int:
    raw = getattr(
        settings,
        "TAPNE_TRIP_DESTINATION_DETAILS_CACHE_TTL_SECONDS",
        DEFAULT_DETAILS_CACHE_TTL_SECONDS,
    )
    try:
        parsed = int(raw)
    except (TypeError, ValueError):
        parsed = DEFAULT_DETAILS_CACHE_TTL_SECONDS
    if parsed < 0:
        return 0
    return min(parsed, 172_800)


def _normalize_query(value: object) -> str:
    return " ".join(str(value or "").split())[:MAX_QUERY_LENGTH]


def _normalize_session_token(value: object) -> str:
    token = str(value or "").strip()
    return token[:MAX_SESSION_TOKEN_LENGTH]


def _extract_text(value: object) -> str:
    if isinstance(value, dict):
        value_map = cast(dict[str, object], value)
        nested = value_map.get("text")
        if isinstance(nested, str):
            return " ".join(nested.split()).strip()

    if value is None:
        fallback = ""
    elif isinstance(value, str):
        fallback = value
    else:
        fallback = str(cast(object, value))
    return " ".join(fallback.split()).strip()


def _coerce_float(raw_value: Any) -> float | None:
    value: float
    if isinstance(raw_value, bool):
        value = float(raw_value)
    elif isinstance(raw_value, (int, float)):
        value = float(raw_value)
    elif isinstance(raw_value, str):
        text = raw_value.strip()
        if not text:
            return None
        try:
            value = float(text)
        except ValueError:
            return None
    else:
        return None

    if not (value == value):
        return None
    return value


def _cache_key(prefix: str, value: str) -> str:
    digest = hashlib.sha1(value.encode("utf-8")).hexdigest()[:20]
    return f"tapne:trips:destination:{prefix}:{digest}"


def _get_cached_value(cache_key: str) -> object | None:
    try:
        return cache.get(cache_key)
    except Exception:
        return None


def _set_cached_value(cache_key: str, payload: object, *, ttl_seconds: int) -> None:
    if ttl_seconds <= 0:
        return
    try:
        cache.set(cache_key, payload, timeout=ttl_seconds)
    except Exception:
        pass


def _request_json(
    *,
    url: str,
    method: str,
    api_key: str,
    payload: dict[str, Any] | None = None,
    field_mask: str = "",
) -> dict[str, Any]:
    headers = {
        "X-Goog-Api-Key": api_key,
    }
    if field_mask:
        headers["X-Goog-FieldMask"] = field_mask

    body_bytes: bytes | None = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        body_bytes = json.dumps(payload).encode("utf-8")

    request = urllib.request.Request(
        url=url,
        data=body_bytes,
        headers=headers,
        method=method,
    )

    try:
        with urllib.request.urlopen(request, timeout=places_timeout_seconds()) as response:
            raw_payload = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        if exc.code in {401, 403}:
            raise PlacesProxyError(
                "Google Places credentials were rejected.",
                code="invalid-api-key",
                status_code=503,
            ) from exc
        raise PlacesProxyError(
            "Google Places request failed.",
            code="google-upstream-error",
            status_code=502,
        ) from exc
    except urllib.error.URLError as exc:
        raise PlacesProxyError(
            "Could not reach Google Places service.",
            code="google-upstream-unreachable",
            status_code=502,
        ) from exc

    try:
        parsed = json.loads(raw_payload or "{}")
    except (TypeError, ValueError) as exc:
        raise PlacesProxyError(
            "Google Places returned invalid JSON.",
            code="google-invalid-json",
            status_code=502,
        ) from exc

    if not isinstance(parsed, dict):
        raise PlacesProxyError(
            "Google Places response format was unexpected.",
            code="google-invalid-shape",
            status_code=502,
        )
    return cast(dict[str, Any], parsed)


def _extract_city_country(components: Any) -> str:
    if not isinstance(components, list):
        return ""

    city = ""
    country = ""
    for item in cast(list[Any], components):
        if not isinstance(item, dict):
            continue
        component_map = cast(dict[str, Any], item)
        component_types = component_map.get("types")
        if not isinstance(component_types, list):
            continue
        normalized_types: set[str] = set()
        for raw_type in cast(list[Any], component_types):
            type_text = str(raw_type).strip()
            if type_text:
                normalized_types.add(type_text)
        component_value = _extract_text(component_map.get("longText"))
        if not component_value:
            continue
        if not city and ("locality" in normalized_types or "postal_town" in normalized_types):
            city = component_value
        if not country and "country" in normalized_types:
            country = component_value

    if city and country:
        return f"{city}, {country}"
    return city or country


def _extract_viewport(raw_viewport: Any) -> PlaceViewport | None:
    if not isinstance(raw_viewport, dict):
        return None
    viewport_map = cast(dict[str, Any], raw_viewport)

    low = viewport_map.get("low")
    high = viewport_map.get("high")
    if not isinstance(low, dict) or not isinstance(high, dict):
        return None

    low_map = cast(dict[str, Any], low)
    high_map = cast(dict[str, Any], high)
    south = _coerce_float(low_map.get("latitude"))
    west = _coerce_float(low_map.get("longitude"))
    north = _coerce_float(high_map.get("latitude"))
    east = _coerce_float(high_map.get("longitude"))
    if south is None or west is None or north is None or east is None:
        return None

    return {
        "south": south,
        "west": west,
        "north": north,
        "east": east,
    }


def autocomplete_places(query: object, *, session_token: object = "") -> list[DestinationSuggestion]:
    normalized_query = _normalize_query(query)
    if len(normalized_query) < 2:
        return []

    cache_key = _cache_key("autocomplete", normalized_query.lower())
    cached = _get_cached_value(cache_key)
    if isinstance(cached, list):
        return cast(list[DestinationSuggestion], cached)

    api_key = configured_places_api_key()
    if not api_key:
        raise PlacesProxyError(
            "Google Places key is not configured.",
            code="missing-api-key",
            status_code=503,
        )

    payload: dict[str, Any] = {
        "input": normalized_query,
        "includeQueryPredictions": False,
        "languageCode": "en",
    }
    normalized_token = _normalize_session_token(session_token)
    if normalized_token:
        payload["sessionToken"] = normalized_token

    try:
        response = _request_json(
            url=PLACES_AUTOCOMPLETE_ENDPOINT,
            method="POST",
            payload=payload,
            api_key=api_key,
            field_mask=AUTOCOMPLETE_FIELD_MASK,
        )
    except PlacesProxyError as exc:
        if exc.code != "google-upstream-error":
            raise
        response = _request_json(
            url=PLACES_AUTOCOMPLETE_ENDPOINT,
            method="POST",
            payload=payload,
            api_key=api_key,
            field_mask="",
        )

    suggestions_raw = response.get("suggestions")
    if not isinstance(suggestions_raw, list):
        return []

    suggestions: list[DestinationSuggestion] = []
    seen_place_ids: set[str] = set()
    for item in cast(list[Any], suggestions_raw):
        if not isinstance(item, dict):
            continue
        item_map = cast(dict[str, Any], item)
        place_prediction = item_map.get("placePrediction")
        if not isinstance(place_prediction, dict):
            continue
        prediction_map = cast(dict[str, Any], place_prediction)

        place_id = str(prediction_map.get("placeId", "") or "").strip()
        if not place_id:
            place_name = str(prediction_map.get("place", "") or "").strip()
            if place_name.startswith("places/"):
                place_id = place_name.split("/", 1)[1].strip()
        if not place_id or place_id in seen_place_ids:
            continue

        structured = prediction_map.get("structuredFormat")
        main_text = ""
        secondary_text = ""
        if isinstance(structured, dict):
            structured_map = cast(dict[str, Any], structured)
            main_text = _extract_text(structured_map.get("mainText"))
            secondary_text = _extract_text(structured_map.get("secondaryText"))

        label = ", ".join([chunk for chunk in [main_text, secondary_text] if chunk]).strip(", ")
        if not label:
            label = _extract_text(prediction_map.get("text"))
        if not label:
            label = place_id

        seen_place_ids.add(place_id)
        suggestions.append(
            {
                "place_id": place_id,
                "label": label,
                "main_text": main_text,
                "secondary_text": secondary_text,
            }
        )

        if len(suggestions) >= places_autocomplete_limit():
            break

    ttl_seconds = places_autocomplete_cache_ttl_seconds()
    _set_cached_value(cache_key, suggestions, ttl_seconds=ttl_seconds)
    return suggestions


def place_details(place_id: object, *, session_token: object = "") -> DestinationDetails:
    normalized_place_id = str(place_id or "").strip()
    if not normalized_place_id:
        raise PlacesProxyError(
            "A place identifier is required.",
            code="missing-place-id",
            status_code=400,
        )

    if normalized_place_id.startswith("places/"):
        place_name = normalized_place_id
        normalized_place_id = normalized_place_id.split("/", 1)[1].strip()
    else:
        place_name = f"places/{normalized_place_id}"

    if not normalized_place_id:
        raise PlacesProxyError(
            "A place identifier is required.",
            code="missing-place-id",
            status_code=400,
        )

    cache_key = _cache_key("details", normalized_place_id.lower())
    cached = _get_cached_value(cache_key)
    if isinstance(cached, dict):
        return cast(DestinationDetails, cached)

    api_key = configured_places_api_key()
    if not api_key:
        raise PlacesProxyError(
            "Google Places key is not configured.",
            code="missing-api-key",
            status_code=503,
        )

    endpoint = PLACES_DETAILS_ENDPOINT_TEMPLATE.format(
        place_name=urllib.parse.quote(place_name, safe="/"),
    )
    normalized_token = _normalize_session_token(session_token)
    if normalized_token:
        endpoint = f"{endpoint}?{urllib.parse.urlencode({'sessionToken': normalized_token})}"

    try:
        response = _request_json(
            url=endpoint,
            method="GET",
            payload=None,
            api_key=api_key,
            field_mask=DETAILS_FIELD_MASK,
        )
    except PlacesProxyError as exc:
        if exc.code != "google-upstream-error":
            raise
        response = _request_json(
            url=endpoint,
            method="GET",
            payload=None,
            api_key=api_key,
            field_mask="id,displayName,formattedAddress,location,viewport,addressComponents",
        )

    location = response.get("location")
    if not isinstance(location, dict):
        raise PlacesProxyError(
            "Place details did not include coordinates.",
            code="missing-location",
            status_code=502,
        )
    location_map = cast(dict[str, Any], location)
    latitude = _coerce_float(location_map.get("latitude"))
    longitude = _coerce_float(location_map.get("longitude"))
    if latitude is None or longitude is None:
        raise PlacesProxyError(
            "Place details coordinates are invalid.",
            code="invalid-location",
            status_code=502,
        )

    place_label = _extract_city_country(response.get("addressComponents"))
    if not place_label:
        place_label = str(response.get("formattedAddress", "") or "").strip()
    if not place_label:
        place_label = _extract_text(response.get("displayName"))
    if not place_label:
        place_label = normalized_place_id

    payload: DestinationDetails = {
        "place_id": normalized_place_id,
        "label": place_label,
        "latitude": latitude,
        "longitude": longitude,
        "viewport": _extract_viewport(response.get("viewport")),
    }

    ttl_seconds = places_details_cache_ttl_seconds()
    _set_cached_value(cache_key, payload, ttl_seconds=ttl_seconds)
    return payload
