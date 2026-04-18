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

FULLSCREEN_LOCATION = """You are analyzing a {width}x{height} pixel Windows desktop screenshot.
A cyan coordinate grid has been overlaid on the image to help you pinpoint exact pixels. Each grid cell is labeled with its top-left coordinate (e.g. 0,0 or 150,300).

TASK: Find the EXACT center (x, y) pixel coordinates of the desktop shortcut for
the Windows application "{target}" in this full screenshot.

VISUAL IDENTIFICATION:
- The target is the desktop shortcut for the built-in Windows "{target}" app
- On Windows 11, the icon typically looks like a small white/blue notepad page
  or notebook with a blue accent, and may include a shortcut arrow overlay
- The text label below may be localized, truncated, or non-English
- Ignore other desktop files, folders (yellow icons), URLs, and distractors like Notepad++ or WordPad. ABSOLUTELY DO NOT select a folder named "{target}". Only select the actual application icon.

Locate the target icon. Find the grid cell it lives in based on the cyan numbers.
Provide the final (x, y) coordinates of the exact center of the icon *within that cell*.

Return JSON:
{{"x": int, "y": int, "confidence": float, "label": "detected text label"}}

Rules:
- Coordinates must be in the original screenshot pixel space
- Confidence is 0.0 to 1.0
- If the icon is not visible, return {{"x": -1, "y": -1, "confidence": 0.0, "label": "not_found"}}
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
position ({det_x}, {det_y}) - marked in the general area of the screen.

QUESTION: Is the element AT EXACTLY that position the genuine, standard Windows
"{target}" desktop shortcut icon?

STRICT VERIFICATION RULES:
- The icon shape and appearance MUST EXACTLY MATCH the Windows application "{target}".
- The element MUST NOT be "Arc Raiders" or any other game, application, folder, or distractor.
- The element MUST NOT be "Notepad++", "WordPad", or a document file.
- It MUST be a desktop shortcut for the target application.
- If the element at this position is a DIFFERENT icon or application, you MUST return is_match: false.
- Do NOT return true if the element is only "near" the position but the position itself is empty or on a different icon.

Return JSON:
{{"is_match": true/false, "detected_label": "exact text visible under the icon", "confidence": float, "distractor_type": "none or name of distractor if not a match", "reasoning": "strict explanation of why this exact pixel coordinate is/isn't the target"}}
"""

POPUP_RESOLUTION = """You are analyzing a Windows desktop screenshot after automation lost focus.

Foreground window title: "{window_title}"
Foreground process: "{process_name}"

TASK: Decide the safest single dismissal action for a blocking popup or unexpected dialog.

Allowed actions only:
- "ignore"
- "press_escape"
- "press_enter"
- "hotkey_alt_f4"
- "hotkey_alt_n"

Return JSON:
{{"action": "one_of_the_allowed_actions", "reasoning": "brief reason"}}

Rules:
- Choose "ignore" if the foreground window does not look like a popup/dialog.
- Prefer the least destructive action.
- Use "hotkey_alt_n" only when the dialog is clearly asking to discard or don't save.
- Never invent other actions.
"""
