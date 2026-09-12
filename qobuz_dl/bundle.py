import base64
import binascii
import logging
import re
from collections import OrderedDict

from qobuz_dl.exceptions import BundleError
from qobuz_dl.http import HttpClient

# Modified code based on DashLt's spoofbuz

logger = logging.getLogger(__name__)

_SEED_TIMEZONE_REGEX = re.compile(
    r'[a-z]\.initialSeed\("(?P<seed>[^"]*)",window\.utimezone\.(?P<timezone>[a-z]+)\)'
)
_INFO_EXTRAS_REGEX = r'name:"\w+/(?P<timezone>{timezones})",info:"(?P<info>[^"]*)",extras:"(?P<extras>[^"]*)"'
_APP_ID_REGEX = re.compile(
    r'production:{api:{appId:"(?P<app_id>\d{9})",appSecret:"\w{32}"'
)

_BUNDLE_URL_REGEX = re.compile(
    r'<script src="(/resources/\d+\.\d+\.\d+-[a-z]\d{3}/bundle\.js)"></script>'
)

_BASE_URL = "https://play.qobuz.com"

_SECRETS_NOT_FOUND = "Could not find the secrets in the Qobuz web bundle"
_CONFLICTING_SECRET_FRAGMENTS = (
    "Found conflicting secret fragments in the Qobuz web bundle"
)
_INCOMPLETE_SECRET_FRAGMENTS = (
    "Found incomplete secret fragments in the Qobuz web bundle"
)
_INVALID_SECRET_ENCODING = "Found invalid secret encoding in the Qobuz web bundle"
_EMPTY_DECODED_SECRET = "Found an empty decoded secret in the Qobuz web bundle"


class Bundle:
    def __init__(self):
        self._session = HttpClient()

        logger.debug("Getting logging page")
        response = self._session.get(f"{_BASE_URL}/login")
        response.raise_for_status()

        bundle_url_match = _BUNDLE_URL_REGEX.search(response.text)
        if not bundle_url_match:
            raise BundleError("Could not find the bundle URL on the Qobuz login page")

        bundle_url = bundle_url_match.group(1)

        logger.debug("Getting bundle")
        response = self._session.get(_BASE_URL + bundle_url)
        response.raise_for_status()

        self._bundle = response.text

    def get_app_id(self):
        match = _APP_ID_REGEX.search(self._bundle)
        if not match:
            raise BundleError("Could not find the app ID in the Qobuz web bundle")

        return match.group("app_id")

    def get_secrets(self):
        logger.debug("Getting secrets")
        seeds = OrderedDict()
        for match in _SEED_TIMEZONE_REGEX.finditer(self._bundle):
            seed, timezone = match.group("seed", "timezone")
            if timezone in seeds:
                if seeds[timezone] != seed:
                    raise BundleError(_CONFLICTING_SECRET_FRAGMENTS)
                continue
            seeds[timezone] = seed

        if len(seeds) < 2:
            raise BundleError(_SECRETS_NOT_FOUND)

        info_extras_regex = _INFO_EXTRAS_REGEX.format(
            timezones="|".join(timezone.capitalize() for timezone in seeds)
        )
        fragments = OrderedDict()
        for match in re.finditer(info_extras_regex, self._bundle):
            timezone, info, extras = match.group("timezone", "info", "extras")
            timezone = timezone.lower()
            fragment_pair = (info, extras)
            if timezone in fragments:
                if fragments[timezone] != fragment_pair:
                    raise BundleError(_CONFLICTING_SECRET_FRAGMENTS)
                continue
            fragments[timezone] = fragment_pair

        if any(
            not seed or timezone not in fragments or not all(fragments[timezone])
            for timezone, seed in seeds.items()
        ):
            raise BundleError(_INCOMPLETE_SECRET_FRAGMENTS)

        timezones = list(seeds)
        ordered_timezones = [timezones[1], timezones[0], *timezones[2:]]
        secrets = OrderedDict()
        for timezone in ordered_timezones:
            encoded_secret = seeds[timezone] + "".join(fragments[timezone])
            if len(encoded_secret) <= 44:
                raise BundleError(_INVALID_SECRET_ENCODING)

            try:
                secret = base64.b64decode(
                    encoded_secret[:-44].encode("ascii"), validate=True
                ).decode("utf-8")
            except (binascii.Error, UnicodeError):
                raise BundleError(_INVALID_SECRET_ENCODING) from None

            if not secret:
                raise BundleError(_EMPTY_DECODED_SECRET)
            secrets[timezone] = secret

        return secrets
