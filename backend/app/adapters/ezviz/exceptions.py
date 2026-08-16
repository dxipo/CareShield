class EzvizError(Exception):
    """Base exception for safe translation at the API boundary."""


class EzvizNotConfiguredError(EzvizError):
    pass


class EzvizNetworkError(EzvizError):
    pass


class EzvizResponseError(EzvizError):
    pass


class EzvizApiError(EzvizError):
    def __init__(self, code: str | None) -> None:
        self.code = code
        suffix = f" (code {code})" if code else ""
        super().__init__(f"EZVIZ API request failed{suffix}")


class EzvizDeviceNotFoundError(EzvizError):
    pass


class EzvizDeviceOfflineError(EzvizError):
    pass


class EzvizStreamUnavailableError(EzvizError):
    def __init__(self, code: str | None = None) -> None:
        self.code = code
        super().__init__("EZVIZ live stream is unavailable")
