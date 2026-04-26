import logging
import tempfile
import os
import requests
from nudenet import NudeDetector

logger = logging.getLogger(__name__)

UNSAFE_LABELS = {
    "FEMALE_GENITALIA_EXPOSED",
    "MALE_GENITALIA_EXPOSED",
    "FEMALE_BREAST_EXPOSED",
    "ANUS_EXPOSED",
    "BUTTOCKS_EXPOSED",
}
UNSAFE_THRESHOLD = 0.6

_detector = None


def _get_detector():
    global _detector
    if _detector is None:
        _detector = NudeDetector()
    return _detector


def _analyze_image_file(path: str) -> bool:
    """Returns True if the image is safe."""
    try:
        results = _get_detector().detect(path)
        for detection in results:
            if (
                detection.get("class") in UNSAFE_LABELS
                and detection.get("score", 0) >= UNSAFE_THRESHOLD
            ):
                return False
        return True
    except Exception as e:
        logger.error("NudeNet analyze error for %s: %s", path, e)
        return True  # fail open on individual image error


def _download_to_temp(image_field) -> str | None:
    """Downloads an S3 ImageField to a temp file. Returns path or None."""
    try:
        url = image_field.url
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        suffix = os.path.splitext(image_field.name)[-1] or ".webp"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as f:
            f.write(response.content)
            return f.name
    except Exception as e:
        logger.error("Failed to download image %s: %s", image_field.name, e)
        return None


def moderate_images(offer) -> tuple[bool, str]:
    """
    Analyzes cover_image + all OfferPhoto images.
    Returns (passed: bool, reasons: str).
    passed=True if all images are safe.
    reasons lists flagged image names separated by commas.
    """
    flagged = []
    temp_files = []

    images_to_check = []

    if offer.cover_image:
        images_to_check.append(("cover_image", offer.cover_image))

    for photo in offer.photos.all():
        images_to_check.append((f"photo_{photo.pk}", photo.image))

    if not images_to_check:
        return True, ""

    try:
        for label, image_field in images_to_check:
            temp_path = _download_to_temp(image_field)
            if temp_path:
                temp_files.append(temp_path)
                if not _analyze_image_file(temp_path):
                    flagged.append(label)
    finally:
        for path in temp_files:
            try:
                os.unlink(path)
            except OSError:
                pass

    passed = len(flagged) == 0
    reasons = ",".join(flagged)
    return passed, reasons
