from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from django.conf import settings
from django.contrib.staticfiles import finders
from django.templatetags.static import static


@dataclass(frozen=True)
class DemoTripCoverImage:
    slot: str
    static_path: str
    source_url: str
    photographer: str
    source_name: str
    preferred_trip_types: tuple[str, ...]
    keywords: tuple[str, ...]
    alt_text: str


@dataclass(frozen=True)
class DemoTripCoverAssignment:
    file_name: str
    source: str
    changed: bool


REQUIRED_DEMO_COVER_SLOTS: tuple[str, ...] = (
    "coastal",
    "trekking",
    "desert",
    "city",
    "food-culture",
    "culture-heritage",
    "wildlife",
    "road-trip",
    "camping",
    "wellness",
)

DEMO_TRIP_COVER_IMAGES: tuple[DemoTripCoverImage, ...] = (
    DemoTripCoverImage(
        slot="coastal",
        static_path="img/demo-covers/coastal-goa-beach.jpg",
        source_url="https://www.pexels.com/photo/goa-beach-23630487/",
        photographer="Kiran Patel",
        source_name="Pexels",
        preferred_trip_types=("coastal",),
        keywords=("goa", "beach", "coast", "island", "maldives", "santorini", "ocean"),
        alt_text="Aerial view of a Goa beach village and coastline.",
    ),
    DemoTripCoverImage(
        slot="trekking",
        static_path="img/demo-covers/trekking-patagonia.jpg",
        source_url="https://www.pexels.com/photo/person-hiking-in-mountains-in-patagonia-21837481/",
        photographer="Marina Zvada",
        source_name="Pexels",
        preferred_trip_types=("trekking",),
        keywords=("patagonia", "hiking", "trek", "mountain", "himalayan", "kedarnath", "roopkund"),
        alt_text="Solo hiker walking through dramatic Patagonia mountain scenery.",
    ),
    DemoTripCoverImage(
        slot="desert",
        static_path="img/demo-covers/desert-morocco-camp.jpg",
        source_url="https://www.pexels.com/photo/luxury-desert-camp-in-the-moroccan-sahara-30757368/",
        photographer="Kristen Haennel",
        source_name="Pexels",
        preferred_trip_types=("desert",),
        keywords=("morocco", "merzouga", "sahara", "desert", "rajasthan", "jaisalmer"),
        alt_text="Luxury tents set in the Moroccan Sahara desert.",
    ),
    DemoTripCoverImage(
        slot="city",
        static_path="img/demo-covers/city-skyline-mumbai.jpg",
        source_url="https://www.pexels.com/photo/city-skyline-2062477/",
        photographer="Rizwan Sayyed",
        source_name="Pexels",
        preferred_trip_types=("city",),
        keywords=("city", "mumbai", "skyline", "tokyo", "singapore", "london", "urban"),
        alt_text="Modern city skyline reflected across calm water.",
    ),
    DemoTripCoverImage(
        slot="food-culture",
        static_path="img/demo-covers/food-culture-tokyo-ramen.jpg",
        source_url="https://www.pexels.com/photo/authentic-tokyo-street-ramen-shop-at-night-30278344/",
        photographer="Valeria Drozdova",
        source_name="Pexels",
        preferred_trip_types=("food-culture",),
        keywords=("food", "ramen", "kyoto", "tokyo", "izakaya", "culinary", "street food"),
        alt_text="Warmly lit Tokyo street food shop at night.",
    ),
    DemoTripCoverImage(
        slot="culture-heritage",
        static_path="img/demo-covers/culture-heritage-temple.jpg",
        source_url="https://www.pexels.com/photo/view-of-a-temple-15065351/",
        photographer="Tokuo Nobuhiro",
        source_name="Pexels",
        preferred_trip_types=("culture-heritage",),
        keywords=("heritage", "temple", "hampi", "borobudur", "palace", "historical", "culture"),
        alt_text="Ancient temple architecture beneath dramatic clouds.",
    ),
    DemoTripCoverImage(
        slot="wildlife",
        static_path="img/demo-covers/wildlife-safari-herd.jpg",
        source_url="https://www.pexels.com/photo/herd-of-animals-on-a-safari-8150758/",
        photographer="Vik Joshi",
        source_name="Pexels",
        preferred_trip_types=("wildlife",),
        keywords=("wildlife", "safari", "mara", "kenya", "savannah", "animals"),
        alt_text="Large safari herd crossing an open savannah.",
    ),
    DemoTripCoverImage(
        slot="road-trip",
        static_path="img/demo-covers/road-trip-patagonia.jpg",
        source_url="https://www.pexels.com/photo/landscape-with-mountains-and-road-4596525/",
        photographer="Ton Souza",
        source_name="Pexels",
        preferred_trip_types=("road-trip",),
        keywords=("road", "drive", "spiti", "chalten", "fitz roy", "highway", "route"),
        alt_text="Open road leading toward mountains near El Chalten.",
    ),
    DemoTripCoverImage(
        slot="camping",
        static_path="img/demo-covers/camping-lake-tent.jpg",
        source_url="https://www.pexels.com/photo/4276016/",
        photographer="Elina Sazonova",
        source_name="Pexels",
        preferred_trip_types=("camping",),
        keywords=("camp", "tent", "lake", "spiti", "winter", "expedition", "outdoor"),
        alt_text="Tent pitched near a lake with trees and mountains beyond.",
    ),
    DemoTripCoverImage(
        slot="wellness",
        static_path="img/demo-covers/wellness-yoga-beach.jpg",
        source_url="https://www.pexels.com/photo/4811133/",
        photographer="Rainer Eck",
        source_name="Pexels",
        preferred_trip_types=("wellness",),
        keywords=("wellness", "yoga", "retreat", "meditation", "beach", "goa"),
        alt_text="Yoga pose on a beach at sunrise.",
    ),
)

BLOG_COVER_TRIP_TYPE_ALIASES: dict[str, str] = {
    "africa": "wildlife",
    "architecture": "culture-heritage",
    "beach": "coastal",
    "beaches": "coastal",
    "budget-travel": "city",
    "coastal": "coastal",
    "culture": "culture-heritage",
    "desert": "desert",
    "driving": "road-trip",
    "food": "food-culture",
    "golden-hour": "culture-heritage",
    "gorilla": "wildlife",
    "hawker": "food-culture",
    "health": "wellness",
    "heritage": "culture-heritage",
    "himalaya": "trekking",
    "hotels": "city",
    "luxury": "wellness",
    "maldives": "coastal",
    "motorcycle": "road-trip",
    "palaces": "culture-heritage",
    "packing": "road-trip",
    "photography": "culture-heritage",
    "rail": "road-trip",
    "roadtrip": "road-trip",
    "safari": "wildlife",
    "shopping": "culture-heritage",
    "solo-travel": "road-trip",
    "street-food": "food-culture",
    "tapas": "food-culture",
    "temple": "culture-heritage",
    "temples": "culture-heritage",
    "trains": "road-trip",
    "trekking": "trekking",
    "wellness": "wellness",
    "wildlife": "wildlife",
    "yoga": "wellness",
}


def normalize_trip_type(value: object) -> str:
    return str(value or "").strip().lower()


def curated_demo_trip_cover_static_paths() -> set[str]:
    return {entry.static_path for entry in DEMO_TRIP_COVER_IMAGES}


@lru_cache(maxsize=1)
def validate_demo_trip_cover_manifest() -> None:
    slots = tuple(entry.slot for entry in DEMO_TRIP_COVER_IMAGES)
    if len(slots) != len(REQUIRED_DEMO_COVER_SLOTS):
        raise ValueError("Demo trip cover manifest must contain exactly 10 image slots.")
    if set(slots) != set(REQUIRED_DEMO_COVER_SLOTS):
        missing = sorted(set(REQUIRED_DEMO_COVER_SLOTS) - set(slots))
        extra = sorted(set(slots) - set(REQUIRED_DEMO_COVER_SLOTS))
        raise ValueError(f"Demo trip cover manifest slot mismatch. missing={missing}, extra={extra}")
    if len(slots) != len(set(slots)):
        raise ValueError("Demo trip cover manifest slots must be unique.")
    if len(curated_demo_trip_cover_static_paths()) != len(DEMO_TRIP_COVER_IMAGES):
        raise ValueError("Demo trip cover static paths must be unique.")

    mapped_types = {
        normalize_trip_type(trip_type)
        for entry in DEMO_TRIP_COVER_IMAGES
        for trip_type in entry.preferred_trip_types
    }
    missing_types = sorted(set(REQUIRED_DEMO_COVER_SLOTS) - mapped_types)
    if missing_types:
        raise ValueError(f"Demo trip cover manifest is missing trip type mappings: {missing_types}")

    for entry in DEMO_TRIP_COVER_IMAGES:
        if not entry.static_path.startswith("img/demo-covers/"):
            raise ValueError(f"Demo trip cover {entry.slot} must live under img/demo-covers/.")
        if finders.find(entry.static_path) is None:
            raise ValueError(f"Demo trip cover static asset missing: {entry.static_path}")
        if not entry.source_url.startswith("https://www.pexels.com/photo/"):
            raise ValueError(f"Demo trip cover {entry.slot} must keep its Pexels source page.")
        if not entry.photographer.strip():
            raise ValueError(f"Demo trip cover {entry.slot} must include photographer metadata.")


def demo_trip_cover_for_trip(*, title: object, destination: object, trip_type: object) -> DemoTripCoverImage:
    validate_demo_trip_cover_manifest()
    normalized_trip_type = normalize_trip_type(trip_type)
    for entry in DEMO_TRIP_COVER_IMAGES:
        if normalized_trip_type in entry.preferred_trip_types:
            return entry

    haystack = " ".join(str(value or "").lower() for value in (title, destination, trip_type))
    for entry in DEMO_TRIP_COVER_IMAGES:
        if any(keyword in haystack for keyword in entry.keywords):
            return entry

    return next(entry for entry in DEMO_TRIP_COVER_IMAGES if entry.slot == "road-trip")


def demo_trip_cover_url_for_trip(*, title: object, destination: object, trip_type: object) -> str:
    cover = demo_trip_cover_for_trip(title=title, destination=destination, trip_type=trip_type)
    return demo_cover_static_url(cover.static_path)


def demo_cover_static_url(static_path: str) -> str:
    try:
        return str(static(static_path) or _raw_static_url(static_path))
    except ValueError:
        # Cloud Run seed jobs run before the web container has created a
        # staticfiles manifest. Store the stable static URL and let the web
        # service serve it after its collectstatic-on-boot step.
        return _raw_static_url(static_path)


def _raw_static_url(static_path: str) -> str:
    static_url = str(getattr(settings, "STATIC_URL", "/static/") or "/static/")
    if not static_url.endswith("/"):
        static_url = static_url + "/"
    return static_url + static_path.lstrip("/")


def demo_blog_cover_trip_type(*, title: str, location: str, tags: list[str]) -> str:
    values = [*tags, title, location]
    for value in values:
        normalized = str(value or "").strip().lower()
        if normalized in BLOG_COVER_TRIP_TYPE_ALIASES:
            return BLOG_COVER_TRIP_TYPE_ALIASES[normalized]

    haystack = " ".join(str(value or "").lower() for value in values)
    for keyword, trip_type in BLOG_COVER_TRIP_TYPE_ALIASES.items():
        if keyword in haystack:
            return trip_type
    return ""


def demo_blog_cover_url_for_blog(*, title: str, location: str, tags: list[str]) -> str:
    trip_type = demo_blog_cover_trip_type(title=title, location=location, tags=tags)
    destination = " ".join([str(location or "").strip(), *tags]).strip()
    return demo_trip_cover_url_for_trip(title=title, destination=destination, trip_type=trip_type)


def assign_demo_trip_banner(trip: Any) -> DemoTripCoverAssignment:
    title = str(getattr(trip, "title", "") or "").strip()
    destination = str(getattr(trip, "destination", "") or "").strip()
    trip_type = normalize_trip_type(getattr(trip, "trip_type", ""))
    cover = demo_trip_cover_for_trip(title=title, destination=destination, trip_type=trip_type)

    current_name = str(getattr(getattr(trip, "banner_image", None), "name", "") or "").strip()
    changed = bool(current_name)
    if changed:
        trip.banner_image.name = ""
        trip.save(update_fields=["banner_image"])

    return DemoTripCoverAssignment(
        file_name=cover.static_path,
        source=f"static:{cover.slot}",
        changed=changed,
    )
