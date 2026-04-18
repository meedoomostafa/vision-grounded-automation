from PIL import Image, ImageDraw

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


def save_debug_image(image: Image.Image, name: str) -> None:
    if not config.VISUAL_DEBUG:
        return

    config.DEBUG_SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    path = config.DEBUG_SCREENSHOTS_DIR / f"{name}.png"
    image.save(path)
    logger.debug("Saved debug image: %s", path)


def save_debug_crop(image: Image.Image, phase: str, step: int, label: str = "") -> None:
    if not config.VISUAL_DEBUG:
        return

    config.DEBUG_SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    suffix = f"_{label}" if label else ""
    filename = f"phase{phase}_step{step}{suffix}.png"
    path = config.DEBUG_SCREENSHOTS_DIR / filename
    image.save(path)
    logger.debug("Saved debug crop: %s", path)


def draw_coordinate_grid(image: Image.Image, cell_size: int = 150) -> Image.Image:
    annotated = image.copy().convert("RGBA")
    overlay = Image.new("RGBA", annotated.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    width, height = annotated.size

                         
    for x in range(0, width, cell_size):
        draw.line([(x, 0), (x, height)], fill=(0, 255, 255, 120), width=2)
        for y in range(0, height, cell_size):
                                                    
            draw.text((x + 4, y + 4), f"{x},{y}", fill=(0, 255, 255, 255))

                           
    for y in range(0, height, cell_size):
        draw.line([(0, y), (width, y)], fill=(0, 255, 255, 120), width=2)

    annotated = Image.alpha_composite(annotated, overlay)
    return annotated.convert("RGB")
import cv2
import numpy as np
from PIL import Image

def generate_som_overlay(image: Image.Image) -> tuple[Image.Image, dict[int, tuple[int, int]]]:
                                                               
    open_cv_image = cv2.cvtColor(np.array(image.convert('RGB')), cv2.COLOR_RGB2BGR)
    gray = cv2.cvtColor(open_cv_image, cv2.COLOR_BGR2GRAY)
    
                         
    edges = cv2.Canny(gray, 50, 150)
    
                                                                           
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 5))
    closed = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel)
    
                     
    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    boxes = []
    width, height = image.size
    for cnt in contours:
        x, y, w, h = cv2.boundingRect(cnt)
        if w < 12 or h < 12:                           
            continue
        if w > width * 0.9 or h > height * 0.9:                              
            continue
        boxes.append([x, y, w, h])
        
    elements_map = {}
    
                   
    for idx, (x, y, w, h) in enumerate(boxes):
        element_id = idx + 1
        elements_map[element_id] = (x + w//2, y + h//2)
        
        cv2.rectangle(open_cv_image, (x, y), (x+w, y+h), (0, 0, 255), 2)
        label = str(element_id)
        (text_w, text_h), baseline = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        text_y = max(y, text_h + baseline) 
        cv2.rectangle(open_cv_image, (x, text_y - text_h - baseline), (x + text_w, text_y), (0, 0, 255), -1)
        cv2.putText(open_cv_image, label, (x, text_y - baseline), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

    rgb_image = cv2.cvtColor(open_cv_image, cv2.COLOR_BGR2RGB)
    return Image.fromarray(rgb_image), elements_map

