class DesktopAutomationError(Exception):
    """Base exception for all desktop automation errors."""


class GroundingError(DesktopAutomationError):
    """MLLM visual grounding failures."""


class IconNotFoundError(GroundingError):
    """Target icon could not be located on screen."""


class WindowNotFoundError(DesktopAutomationError):
    """Expected window did not appear within timeout."""


class APIError(DesktopAutomationError):
    """JSONPlaceholder API communication failures."""
