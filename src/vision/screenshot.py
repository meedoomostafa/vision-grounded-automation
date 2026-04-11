from PIL import Image
import mss

from src.core.logger import get_logger

logger = get_logger(__name__)


def capture_screen(monitor_index: int = 1) -> Image.Image:
    with mss.mss() as sct:
        monitors = sct.monitors
        if monitor_index >= len(monitors):
            logger.warning(
                "Monitor %d not found (%d available), falling back to primary",
                monitor_index,
                len(monitors) - 1,
            )
            monitor_index = 1

        monitor = monitors[monitor_index]
        raw = sct.grab(monitor)
        image = Image.frombytes("RGB", (raw.width, raw.height), raw.rgb)

    logger.debug("Captured screen: %dx%d from monitor %d", image.width, image.height, monitor_index)
    return image


def crop_region(image: Image.Image, bbox: tuple[int, int, int, int]) -> Image.Image:
    x1, y1, x2, y2 = bbox
    w, h = image.size

    x1 = max(0, min(x1, w))
    y1 = max(0, min(y1, h))
    x2 = max(x1 + 1, min(x2, w))
    y2 = max(y1 + 1, min(y2, h))

    cropped = image.crop((x1, y1, x2, y2))
    logger.debug("Cropped region (%d,%d,%d,%d) → %dx%d", x1, y1, x2, y2, cropped.width, cropped.height)
    return cropped
