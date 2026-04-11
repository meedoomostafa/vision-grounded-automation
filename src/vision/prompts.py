REGION_IDENTIFICATION = """You are analyzing a {width}x{height} pixel Windows desktop screenshot.

TASK: Locate the desktop shortcut for the Windows application "{target}" on this screen.

VISUAL CONTEXT — You must handle these variations:
- The desktop may use Windows Light OR Dark theme
- Desktop icons may be set to Small, Medium, or Large size
- The background could be any solid color, gradient, or busy wallpaper
- Some icons may be partially covered by open windows
- The icon grid may be auto-arranged or manually placed anywhere
- The visible label may be localized into the OS language and may NOT be the English word "{target}"

DISAMBIGUATION — Multiple similar icons may exist. You must:
- Look for the genuine Windows "{target}" shortcut for the built-in app
- REJECT distractors: "Notepad++" (green chameleon icon), "WordPad",
  "TextEdit", copies like "Notepad - Copy"
- Prefer the genuine built-in Windows "{target}" shortcut even if the
  visible text label is localized
- If the label text is unreadable or non-English, use the icon
  appearance and surrounding desktop context

Return a JSON object with candidate regions that likely contain the "{target}" icon.
Each region should be a bounding box in the original screenshot pixel space.

Format:
{{"regions": [
  {{"x1": int, "y1": int, "x2": int, "y2": int,
    "confidence": float, "reasoning": "why this region"}}
]}}

Rules:
- Coordinates must be within 0-{width} (x) and 0-{height} (y)
- Confidence is 0.0 to 1.0
- Return at most 5 candidate regions, sorted by confidence descending
- If no plausible regions found, return {{"regions": []}}
- Make regions large enough to fully contain the icon and its label (at least 150x150 pixels)
"""

PRECISE_LOCATION = """You are viewing a cropped region of a Windows desktop screenshot.
This crop is {crop_w}x{crop_h} pixels.

TASK: Find the EXACT center (x, y) pixel coordinates of the Windows "{target}" shortcut icon
WITHIN THIS CROPPED IMAGE.

VISUAL IDENTIFICATION:
- The target is the Windows shortcut for the application "{target}"
- It may include a shortcut arrow overlay and a localized label
- The visible label may be localized into the OS language instead of "{target}"
- Ignore ANY similar but different icons (Notepad++, WordPad, copies, etc.)

DISAMBIGUATION:
- If multiple similar icons exist, choose the one for the built-in Windows "{target}" app
- If a "Notepad++" icon exists, it has a green chameleon — that is NOT the target
- If the text label is non-English or unreadable, still return the best
  match based on icon appearance

Return JSON with coordinates relative to THIS cropped image (not the full screen):
{{"x": int, "y": int, "confidence": float, "label": "detected text label"}}

If the "{target}" icon is NOT in this crop, return:
{{"x": -1, "y": -1, "confidence": 0.0, "label": "not_found"}}
"""

VERIFICATION = """Look at this desktop screenshot. A UI element has been detected at
position ({det_x}, {det_y}) — marked in the general area of the screen.

QUESTION: Is the element at or very near that position the standard Windows
"{target}" desktop shortcut icon?

Consider:
- The icon shape and appearance should match the Windows application "{target}"
- The text label beneath it may be localized into the OS language instead of "{target}"
- It should be a desktop shortcut, not a taskbar item or window button

Return JSON:
{{"is_match": true/false, "reasoning": "brief explanation"}}
"""
