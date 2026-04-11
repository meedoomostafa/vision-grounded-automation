class DesktopAutomationError(Exception):
    pass


class GroundingError(DesktopAutomationError):
    pass


class IconNotFoundError(GroundingError):
    pass


class WindowNotFoundError(DesktopAutomationError):
    pass


class APIError(DesktopAutomationError):
    pass
