class AuthenticationError(Exception):
    pass


class BundleError(Exception):
    """Raised when app credentials cannot be extracted from the Qobuz web bundle."""


class IneligibleError(Exception):
    pass


class InvalidAppIdError(Exception):
    pass


class InvalidAppSecretError(Exception):
    pass


class InvalidQuality(Exception):
    pass


class NonStreamable(Exception):
    pass
