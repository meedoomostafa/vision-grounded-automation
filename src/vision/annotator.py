from PIL import Image, ImageDraw, ImageFont

from src import config
from src.core.logger import get_logger

logger = get_logger(__name__)

                                         
COLOR_REGION = (255, 255, 0)                                   
COLOR_CROSSHAIR = (255, 0, 0)                            
COLOR_TEXT_BG = (0, 0, 0, 180)                            
COLOR_TEXT = (255, 255, 255)                   


def annotate_detection(
    image: Image.Image,
    coords: tuple[int, int],
    regions: list | None = None,
    label: str = "Detected",
) -> Image.Image:
    annotated = image.copy().convert("RGBA")
    overlay = Image.new("RGBA", annotated.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

                                 
    if regions:
        for i, region in enumerate(regions):
            x1 = region.get("x1", 0)
            y1 = region.get("y1", 0)
            x2 = region.get("x2", 0)
            y2 = region.get("y2", 0)
            conf = region.get("confidence", 0)

            draw.rectangle([x1, y1, x2, y2], outline=COLOR_REGION, width=2)

            region_label = f"R{i+1} ({conf:.0%})"
            draw.text((x1 + 4, y1 + 4), region_label, fill=COLOR_REGION)

                                       
    x, y = coords
    arm = 25
    draw.line([(x - arm, y), (x + arm, y)], fill=COLOR_CROSSHAIR, width=3)
    draw.line([(x, y - arm), (x, y + arm)], fill=COLOR_CROSSHAIR, width=3)
    draw.ellipse([(x - 6, y - 6), (x + 6, y + 6)], fill=COLOR_CROSSHAIR)

                     
    text = f"{label} ({x}, {y})"
    draw.text((x + 12, y - 24), text, fill=COLOR_CROSSHAIR)

    annotated = Image.alpha_composite(annotated, overlay)
    return annotated.convert("RGB")


def save_annotated(image: Image.Image, name: str) -> None:
    config.SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    path = config.SCREENSHOTS_DIR / f"{name}.png"
    image.save(path)
    logger.info("Saved annotated screenshot: %s", path)


def save_debug_crop(image: Image.Image, phase: str, step: int, label: str = "") -> None:
    if not config.VISUAL_DEBUG:
        return

    config.DEBUG_SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    suffix = f"_{label}" if label else ""
    filename = f"phase{phase}_step{step}{suffix}.png"
    path = config.DEBUG_SCREENSHOTS_DIR / filename
    image.save(path)
    logger.debug("Saved debug crop: %s", path)
