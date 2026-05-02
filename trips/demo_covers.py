from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import TypeAlias
from urllib.error import URLError
from urllib.request import Request, urlopen

from PIL import Image, ImageDraw, ImageFont, ImageOps, UnidentifiedImageError
from django.core.files.base import ContentFile
from django.core.files.storage import Storage, default_storage
from django.utils.text import slugify

from .models import Trip

DemoFont: TypeAlias = ImageFont.ImageFont | ImageFont.FreeTypeFont

DEMO_COVER_WIDTH = 1600
DEMO_COVER_HEIGHT = 900
MAX_SOURCE_IMAGE_BYTES = 15 * 1024 * 1024


@dataclass(frozen=True)
class DemoTripCoverImage:
    slot: str
    storage_path: str
    download_url: str
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


@dataclass(frozen=True)
class DemoTripCoverSyncResult:
    slot: str
    file_name: str
    status: str
    bytes_written: int = 0
    error: str = ""


TRIP_IMAGE_PALETTES: dict[str, tuple[tuple[int, int, int], tuple[int, int, int]]] = {
    "city": ((29, 78, 216), (126, 34, 206)),
    "culture-heritage": ((180, 83, 9), (120, 53, 15)),
    "food-culture": ((220, 38, 38), (249, 115, 22)),
    "trekking": ((22, 101, 52), (21, 128, 61)),
    "coastal": ((8, 145, 178), (14, 116, 144)),
    "desert": ((217, 119, 6), (120, 53, 15)),
    "wildlife": ((62, 94, 24), (22, 101, 52)),
    "road-trip": ((55, 65, 81), (15, 23, 42)),
    "camping": ((67, 56, 202), (30, 64, 175)),
    "wellness": ((13, 148, 136), (5, 150, 105)),
    "adventure-sports": ((190, 24, 93), (157, 23, 77)),
}

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
        storage_path="trip_banners/demo/curated/coastal-goa-beach.jpg",
        download_url="https://images.pexels.com/photos/23630487/pexels-photo-23630487.jpeg?auto=compress&cs=tinysrgb&w=1800",
        source_url="https://www.pexels.com/photo/goa-beach-23630487/",
        photographer="Kiran Patel",
        source_name="Pexels",
        preferred_trip_types=("coastal",),
        keywords=("goa", "beach", "coast", "island", "maldives", "santorini", "ocean"),
        alt_text="Aerial view of a Goa beach village and coastline.",
    ),
    DemoTripCoverImage(
        slot="trekking",
        storage_path="trip_banners/demo/curated/trekking-patagonia.jpg",
        download_url="https://images.pexels.com/photos/21837481/pexels-photo-21837481.jpeg?auto=compress&cs=tinysrgb&w=1800",
        source_url="https://www.pexels.com/photo/person-hiking-in-mountains-in-patagonia-21837481/",
        photographer="Marina Zvada",
        source_name="Pexels",
        preferred_trip_types=("trekking",),
        keywords=("patagonia", "hiking", "trek", "mountain", "himalayan", "kedarnath", "roopkund"),
        alt_text="Solo hiker walking through dramatic Patagonia mountain scenery.",
    ),
    DemoTripCoverImage(
        slot="desert",
        storage_path="trip_banners/demo/curated/desert-morocco-camp.jpg",
        download_url="https://images.pexels.com/photos/30757368/pexels-photo-30757368.jpeg?auto=compress&cs=tinysrgb&w=1800",
        source_url="https://www.pexels.com/photo/luxury-desert-camp-in-the-moroccan-sahara-30757368/",
        photographer="Kristen Haennel",
        source_name="Pexels",
        preferred_trip_types=("desert",),
        keywords=("morocco", "merzouga", "sahara", "desert", "rajasthan", "jaisalmer"),
        alt_text="Luxury tents set in the Moroccan Sahara desert.",
    ),
    DemoTripCoverImage(
        slot="city",
        storage_path="trip_banners/demo/curated/city-skyline-mumbai.jpg",
        download_url="https://images.pexels.com/photos/2062477/pexels-photo-2062477.jpeg?auto=compress&cs=tinysrgb&w=1800",
        source_url="https://www.pexels.com/photo/city-skyline-2062477/",
        photographer="Rizwan Sayyed",
        source_name="Pexels",
        preferred_trip_types=("city",),
        keywords=("city", "mumbai", "skyline", "tokyo", "singapore", "london", "urban"),
        alt_text="Modern city skyline reflected across calm water.",
    ),
    DemoTripCoverImage(
        slot="food-culture",
        storage_path="trip_banners/demo/curated/food-culture-tokyo-ramen.jpg",
        download_url="https://images.pexels.com/photos/30278344/pexels-photo-30278344.jpeg?auto=compress&cs=tinysrgb&w=1800",
        source_url="https://www.pexels.com/photo/authentic-tokyo-street-ramen-shop-at-night-30278344/",
        photographer="Valeria Drozdova",
        source_name="Pexels",
        preferred_trip_types=("food-culture",),
        keywords=("food", "ramen", "kyoto", "tokyo", "izakaya", "culinary", "street food"),
        alt_text="Warmly lit Tokyo street food shop at night.",
    ),
    DemoTripCoverImage(
        slot="culture-heritage",
        storage_path="trip_banners/demo/curated/culture-heritage-temple.jpg",
        download_url="https://images.pexels.com/photos/15065351/pexels-photo-15065351.jpeg?auto=compress&cs=tinysrgb&w=1800",
        source_url="https://www.pexels.com/photo/view-of-a-temple-15065351/",
        photographer="Tokuo Nobuhiro",
        source_name="Pexels",
        preferred_trip_types=("culture-heritage",),
        keywords=("heritage", "temple", "hampi", "borobudur", "palace", "historical", "culture"),
        alt_text="Ancient temple architecture beneath dramatic clouds.",
    ),
    DemoTripCoverImage(
        slot="wildlife",
        storage_path="trip_banners/demo/curated/wildlife-safari-herd.jpg",
        download_url="https://images.pexels.com/photos/8150758/pexels-photo-8150758.jpeg?auto=compress&cs=tinysrgb&w=1800",
        source_url="https://www.pexels.com/photo/herd-of-animals-on-a-safari-8150758/",
        photographer="Vik Joshi",
        source_name="Pexels",
        preferred_trip_types=("wildlife",),
        keywords=("wildlife", "safari", "mara", "kenya", "savannah", "animals"),
        alt_text="Large safari herd crossing an open savannah.",
    ),
    DemoTripCoverImage(
        slot="road-trip",
        storage_path="trip_banners/demo/curated/road-trip-patagonia.jpg",
        download_url="https://images.pexels.com/photos/4596525/pexels-photo-4596525.jpeg?auto=compress&cs=tinysrgb&w=1800",
        source_url="https://www.pexels.com/photo/landscape-with-mountains-and-road-4596525/",
        photographer="Ton Souza",
        source_name="Pexels",
        preferred_trip_types=("road-trip",),
        keywords=("road", "drive", "spiti", "chalten", "fitz roy", "highway", "route"),
        alt_text="Open road leading toward mountains near El Chalten.",
    ),
    DemoTripCoverImage(
        slot="camping",
        storage_path="trip_banners/demo/curated/camping-lake-tent.jpg",
        download_url="https://images.pexels.com/photos/4276016/pexels-photo-4276016.jpeg?auto=compress&cs=tinysrgb&w=1800",
        source_url="https://www.pexels.com/photo/4276016/",
        photographer="Elina Sazonova",
        source_name="Pexels",
        preferred_trip_types=("camping",),
        keywords=("camp", "tent", "lake", "spiti", "winter", "expedition", "outdoor"),
        alt_text="Tent pitched near a lake with trees and mountains beyond.",
    ),
    DemoTripCoverImage(
        slot="wellness",
        storage_path="trip_banners/demo/curated/wellness-yoga-beach.jpg",
        download_url="https://images.pexels.com/photos/4811133/pexels-photo-4811133.jpeg?auto=compress&cs=tinysrgb&w=1800",
        source_url="https://www.pexels.com/photo/4811133/",
        photographer="Rainer Eck",
        source_name="Pexels",
        preferred_trip_types=("wellness",),
        keywords=("wellness", "yoga", "retreat", "meditation", "beach", "goa"),
        alt_text="Yoga pose on a beach at sunrise.",
    ),
)


def normalize_trip_type(value: object) -> str:
    return str(value or "").strip().lower()


def curated_demo_trip_cover_paths() -> set[str]:
    return {entry.storage_path for entry in DEMO_TRIP_COVER_IMAGES}


def is_curated_demo_trip_cover_path(file_name: str) -> bool:
    return str(file_name or "").strip() in curated_demo_trip_cover_paths()


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
    if len(curated_demo_trip_cover_paths()) != len(DEMO_TRIP_COVER_IMAGES):
        raise ValueError("Demo trip cover storage paths must be unique.")

    mapped_types = {
        normalize_trip_type(trip_type)
        for entry in DEMO_TRIP_COVER_IMAGES
        for trip_type in entry.preferred_trip_types
    }
    missing_types = sorted(set(REQUIRED_DEMO_COVER_SLOTS) - mapped_types)
    if missing_types:
        raise ValueError(f"Demo trip cover manifest is missing trip type mappings: {missing_types}")

    for entry in DEMO_TRIP_COVER_IMAGES:
        if not entry.download_url.startswith("https://images.pexels.com/"):
            raise ValueError(f"Demo trip cover {entry.slot} must download from images.pexels.com.")
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


def _load_font(size: int, *, bold: bool = False) -> DemoFont:
    font_candidates = [
        "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
        "arialbd.ttf" if bold else "arial.ttf",
    ]
    for candidate in font_candidates:
        try:
            return ImageFont.truetype(candidate, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def _text_width(draw: ImageDraw.ImageDraw, text: str, font: DemoFont) -> int:
    left, _top, right, _bottom = draw.textbbox((0, 0), text, font=font)
    return int(right - left)


def _wrap_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    *,
    font: DemoFont,
    max_width: int,
    max_lines: int,
) -> list[str]:
    words = [part for part in str(text or "").split() if part]
    if not words:
        return [""]

    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if _text_width(draw, candidate, font) <= max_width:
            current = candidate
            continue
        lines.append(current)
        current = word
        if len(lines) == max_lines - 1:
            break

    remaining_words = words[len(" ".join(lines + [current]).split()):]
    if remaining_words and len(lines) == max_lines - 1:
        tail = " ".join([current] + remaining_words)
        while tail and _text_width(draw, f"{tail}...", font) > max_width:
            tail = tail.rsplit(" ", 1)[0]
        current = f"{tail}..." if tail else current
    lines.append(current)
    return lines[:max_lines]


def _draw_pill(
    draw: ImageDraw.ImageDraw,
    *,
    x: int,
    y: int,
    text: str,
    font: DemoFont,
) -> None:
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    width = int(right - left)
    height = int(bottom - top)
    padding_x = 22
    padding_y = 12
    draw.rounded_rectangle(
        (x, y, x + width + (padding_x * 2), y + height + (padding_y * 2)),
        radius=24,
        fill=(255, 255, 255, 42),
        outline=(255, 255, 255, 76),
        width=2,
    )
    draw.text((x + padding_x, y + padding_y - 2), text, font=font, fill=(255, 255, 255, 235))


def render_generated_demo_cover(
    *,
    title: str,
    subtitle: str,
    eyebrow: str,
    primary: tuple[int, int, int],
    secondary: tuple[int, int, int],
) -> bytes:
    base = Image.new("RGBA", (DEMO_COVER_WIDTH, DEMO_COVER_HEIGHT), primary + (255,))
    draw = ImageDraw.Draw(base, "RGBA")

    for y in range(DEMO_COVER_HEIGHT):
        blend = y / max(1, DEMO_COVER_HEIGHT - 1)
        color = tuple(
            int(primary[idx] + ((secondary[idx] - primary[idx]) * blend))
            for idx in range(3)
        )
        draw.line((0, y, DEMO_COVER_WIDTH, y), fill=color + (255,))

    accent = tuple(min(255, channel + 28) for channel in secondary)
    draw.ellipse((-180, -140, 720, 760), fill=accent + (70,))
    draw.ellipse((980, 90, 1740, 920), fill=(255, 255, 255, 28))
    draw.rectangle((0, 0, DEMO_COVER_WIDTH, DEMO_COVER_HEIGHT), fill=(6, 10, 24, 58))
    draw.rounded_rectangle((84, 84, 1516, 816), radius=46, outline=(255, 255, 255, 48), width=3)

    eyebrow_font = _load_font(30, bold=True)
    title_font = _load_font(76, bold=True)
    subtitle_font = _load_font(34)

    _draw_pill(draw, x=124, y=120, text=eyebrow, font=eyebrow_font)

    title_lines = _wrap_text(draw, title, font=title_font, max_width=1180, max_lines=3)
    title_y = 270
    for line in title_lines:
        draw.text((124, title_y), line, font=title_font, fill=(255, 255, 255, 246))
        title_y += 92

    subtitle_lines = _wrap_text(draw, subtitle, font=subtitle_font, max_width=1060, max_lines=2)
    subtitle_y = 680
    for line in subtitle_lines:
        draw.text((124, subtitle_y), line, font=subtitle_font, fill=(235, 241, 255, 228))
        subtitle_y += 46

    output = BytesIO()
    base.convert("RGB").save(output, format="PNG", optimize=True)
    return output.getvalue()


def normalize_source_image_bytes(raw_image: bytes) -> bytes:
    try:
        with Image.open(BytesIO(raw_image)) as source:
            image = ImageOps.exif_transpose(source).convert("RGB")
            fitted = ImageOps.fit(
                image,
                (DEMO_COVER_WIDTH, DEMO_COVER_HEIGHT),
                method=Image.Resampling.LANCZOS,
                centering=(0.5, 0.5),
            )
            output = BytesIO()
            fitted.save(output, format="JPEG", quality=86, optimize=True, progressive=True)
            return output.getvalue()
    except (OSError, UnidentifiedImageError) as exc:
        raise ValueError("Downloaded demo cover is not a readable image.") from exc


def download_demo_trip_cover_image(entry: DemoTripCoverImage) -> bytes:
    request = Request(
        entry.download_url,
        headers={
            "User-Agent": "Tapne demo image sync/1.0",
            "Accept": "image/avif,image/webp,image/apng,image/jpeg,image/*,*/*;q=0.8",
        },
    )
    try:
        with urlopen(request, timeout=20) as response:
            raw = response.read(MAX_SOURCE_IMAGE_BYTES + 1)
    except (OSError, URLError) as exc:
        raise RuntimeError(f"Could not download {entry.slot} demo cover.") from exc

    if len(raw) > MAX_SOURCE_IMAGE_BYTES:
        raise ValueError(f"Downloaded {entry.slot} demo cover exceeded the size limit.")
    return normalize_source_image_bytes(raw)


def sync_demo_trip_cover_image(
    entry: DemoTripCoverImage,
    *,
    storage: Storage | None = None,
    force: bool = False,
) -> DemoTripCoverSyncResult:
    active_storage = storage or default_storage
    if not force and active_storage.exists(entry.storage_path):
        return DemoTripCoverSyncResult(slot=entry.slot, file_name=entry.storage_path, status="skipped")

    try:
        content = download_demo_trip_cover_image(entry)
        if force and active_storage.exists(entry.storage_path):
            active_storage.delete(entry.storage_path)
        saved_name = active_storage.save(entry.storage_path, ContentFile(content, name=Path(entry.storage_path).name))
    except Exception as exc:
        return DemoTripCoverSyncResult(
            slot=entry.slot,
            file_name=entry.storage_path,
            status="failed",
            error=str(exc),
        )

    return DemoTripCoverSyncResult(
        slot=entry.slot,
        file_name=saved_name,
        status="synced",
        bytes_written=len(content),
    )


def sync_demo_trip_cover_images(*, force: bool = False, storage: Storage | None = None) -> list[DemoTripCoverSyncResult]:
    validate_demo_trip_cover_manifest()
    return [
        sync_demo_trip_cover_image(entry, force=force, storage=storage)
        for entry in DEMO_TRIP_COVER_IMAGES
    ]


def _generated_demo_banner_path(*, trip_id: int, title: str) -> str:
    slug = slugify(title)[:72] or f"trip-{trip_id}"
    return f"trip_banners/demo/generated/{slug}-{trip_id}.png"


def _save_generated_demo_banner(*, trip: Trip, title: str, destination: str, trip_type: str) -> str:
    trip_id = int(trip.pk or 0)
    file_name = _generated_demo_banner_path(trip_id=trip_id, title=title)
    storage = trip.banner_image.storage
    if not storage.exists(file_name):
        primary, secondary = TRIP_IMAGE_PALETTES.get(trip_type, ((37, 99, 235), (30, 64, 175)))
        content = render_generated_demo_cover(
            title=title,
            subtitle=destination or "Handpicked Tapne demo itinerary",
            eyebrow=f"Demo trip • {trip_type.replace('-', ' ') or 'travel'}",
            primary=primary,
            secondary=secondary,
        )
        storage.save(file_name, ContentFile(content, name=Path(file_name).name))
    return file_name


def assign_demo_trip_banner(trip: Trip) -> DemoTripCoverAssignment:
    trip_id = int(trip.pk or 0)
    title = str(getattr(trip, "title", "") or "").strip() or f"Tapne Trip {trip_id}"
    destination = str(getattr(trip, "destination", "") or "").strip()
    trip_type = normalize_trip_type(getattr(trip, "trip_type", ""))
    cover = demo_trip_cover_for_trip(title=title, destination=destination, trip_type=trip_type)
    storage = trip.banner_image.storage

    source = "generated"
    file_name = ""
    if storage.exists(cover.storage_path):
        file_name = cover.storage_path
        source = f"curated:{cover.slot}"
    else:
        file_name = _save_generated_demo_banner(
            trip=trip,
            title=title,
            destination=destination,
            trip_type=trip_type,
        )

    current_name = str(getattr(trip.banner_image, "name", "") or "").strip()
    changed = current_name != file_name
    if changed:
        trip.banner_image.name = file_name
        trip.save(update_fields=["banner_image"])

    return DemoTripCoverAssignment(file_name=file_name, source=source, changed=changed)
