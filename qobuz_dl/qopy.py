# Wrapper for Qo-DL Reborn. This is a slightly modified version
# of qopy, originally written by Sorrow446. All credits to the
# original author.

import hashlib
import logging
import time
from dataclasses import dataclass

from qobuz_dl.color import GREEN, YELLOW
from qobuz_dl.exceptions import (
    AuthenticationError,
    IneligibleError,
    InvalidAppIdError,
    InvalidAppSecretError,
    InvalidQuality,
)
from qobuz_dl.http import HttpClient

RESET = "Reset your credentials with 'uvx qobuz-dl -r' (or 'qobuz-dl -r' if installed)"

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _ApiRequest:
    endpoint: str
    params: dict


class Client:
    def __init__(self, email, pwd, app_id, secrets):
        logger.info(f"{YELLOW}Logging in...")
        self.secrets = secrets
        self.id = str(app_id)
        self.session = HttpClient()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:83.0) "
                    "Gecko/20100101 Firefox/83.0"
                ),
                "X-App-Id": self.id,
                "Content-Type": "application/json;charset=UTF-8",
            }
        )
        self.base = "https://www.qobuz.com/api.json/0.2/"
        self.sec = None
        self.auth(email, pwd)
        self.cfg_setup()

    def api_call(self, epoint, **kwargs):
        request = self._build_api_request(epoint, kwargs)
        r = self.session.get(self.base + request.endpoint, params=request.params)
        self._raise_mapped_api_error(request.endpoint, r)
        r.raise_for_status()
        return r.json()

    def _build_api_request(self, epoint, kwargs):
        if epoint == "user/login":
            params = self._login_params(kwargs)
        elif epoint == "track/get":
            params = self._track_meta_params(kwargs)
        elif epoint == "album/get":
            params = self._album_meta_params(kwargs)
        elif epoint == "playlist/get":
            params = self._playlist_meta_params(kwargs)
        elif epoint == "artist/get":
            params = self._artist_meta_params(kwargs)
        elif epoint == "label/get":
            params = self._label_meta_params(kwargs)
        elif epoint == "favorite/getUserFavorites":
            params = self._favorite_params(kwargs)
        elif epoint == "track/getFileUrl":
            params = self._track_file_url_params(kwargs)
        else:
            params = kwargs
        return _ApiRequest(endpoint=epoint, params=params)

    def _login_params(self, kwargs):
        return {
            "email": kwargs["email"],
            "password": kwargs["pwd"],
            "app_id": self.id,
        }

    def _track_meta_params(self, kwargs):
        return {"track_id": kwargs["id"]}

    def _album_meta_params(self, kwargs):
        return {"album_id": kwargs["id"]}

    def _playlist_meta_params(self, kwargs):
        return {
            "extra": "tracks",
            "playlist_id": kwargs["id"],
            "limit": 500,
            "offset": kwargs["offset"],
        }

    def _artist_meta_params(self, kwargs):
        return {
            "app_id": self.id,
            "artist_id": kwargs["id"],
            "limit": 500,
            "offset": kwargs["offset"],
            "extra": "albums",
        }

    def _label_meta_params(self, kwargs):
        return {
            "label_id": kwargs["id"],
            "limit": 500,
            "offset": kwargs["offset"],
            "extra": "albums",
        }

    def _favorite_params(self, kwargs):
        unix = time.time()
        r_sig = "favoritegetUserFavorites" + str(unix) + kwargs.get("sec", self.sec)
        r_sig_hashed = hashlib.md5(r_sig.encode("utf-8")).hexdigest()
        return {
            "app_id": self.id,
            "user_auth_token": self.uat,
            "type": kwargs["type"],
            "offset": kwargs["offset"],
            "limit": kwargs["limit"],
            "request_ts": unix,
            "request_sig": r_sig_hashed,
        }

    def _track_file_url_params(self, kwargs):
        unix = time.time()
        track_id = kwargs["id"]
        fmt_id = kwargs["fmt_id"]
        if int(fmt_id) not in (5, 6, 7, 27):
            raise InvalidQuality("Invalid quality id: choose between 5, 6, 7 or 27")
        r_sig = "trackgetFileUrlformat_id{}intentstreamtrack_id{}{}{}".format(
            fmt_id, track_id, unix, kwargs.get("sec", self.sec)
        )
        r_sig_hashed = hashlib.md5(r_sig.encode("utf-8")).hexdigest()
        return {
            "request_ts": unix,
            "request_sig": r_sig_hashed,
            "track_id": track_id,
            "format_id": fmt_id,
            "intent": "stream",
        }

    def _raise_mapped_api_error(self, epoint, response):
        if epoint == "user/login":
            if response.status_code == 401:
                raise AuthenticationError("Invalid credentials.\n" + RESET)
            elif response.status_code == 400:
                raise InvalidAppIdError("Invalid app id.\n" + RESET)
            else:
                logger.info(f"{GREEN}Logged: OK")
        elif (
            epoint in ["track/getFileUrl", "favorite/getUserFavorites"]
            and response.status_code == 400
        ):
            raise InvalidAppSecretError(
                f"Invalid app secret: {response.json()}.\n" + RESET
            )

    def auth(self, email, pwd):
        usr_info = self.api_call("user/login", email=email, pwd=pwd)
        if not usr_info["user"]["credential"]["parameters"]:
            raise IneligibleError("Free accounts are not eligible to download tracks.")
        self.uat = usr_info["user_auth_token"]
        self.session.headers.update({"X-User-Auth-Token": self.uat})
        self.label = usr_info["user"]["credential"]["parameters"]["short_label"]
        logger.info(f"{GREEN}Membership: {self.label}")

    def multi_meta(self, epoint, key, item_id, content_type):
        total = 1
        offset = 0
        while total > 0:
            chunk = self.api_call(epoint, id=item_id, offset=offset, type=content_type)
            if content_type in ("tracks", "albums"):
                chunk = chunk[content_type]
            yield chunk
            if offset == 0:
                total = chunk[key] - 500
            else:
                total -= 500
            offset += 500

    def get_album_meta(self, id):
        return self.api_call("album/get", id=id)

    def get_track_meta(self, id):
        return self.api_call("track/get", id=id)

    def get_track_url(self, id, fmt_id):
        return self.api_call("track/getFileUrl", id=id, fmt_id=fmt_id)

    def get_artist_meta(self, id):
        return self.multi_meta("artist/get", "albums_count", id, None)

    def get_plist_meta(self, id):
        return self.multi_meta("playlist/get", "tracks_count", id, None)

    def get_label_meta(self, id):
        return self.multi_meta("label/get", "albums_count", id, None)

    def search_albums(self, query, limit):
        return self.api_call("album/search", query=query, limit=limit)

    def search_artists(self, query, limit):
        return self.api_call("artist/search", query=query, limit=limit)

    def search_playlists(self, query, limit):
        return self.api_call("playlist/search", query=query, limit=limit)

    def search_tracks(self, query, limit):
        return self.api_call("track/search", query=query, limit=limit)

    def get_favorite_albums(self, offset, limit):
        return self.api_call(
            "favorite/getUserFavorites", type="albums", offset=offset, limit=limit
        )

    def get_favorite_tracks(self, offset, limit):
        return self.api_call(
            "favorite/getUserFavorites", type="tracks", offset=offset, limit=limit
        )

    def get_favorite_artists(self, offset, limit):
        return self.api_call(
            "favorite/getUserFavorites", type="artists", offset=offset, limit=limit
        )

    def get_user_playlists(self, limit):
        return self.api_call("playlist/getUserPlaylists", limit=limit)

    def test_secret(self, sec):
        try:
            self.api_call("track/getFileUrl", id=5966783, fmt_id=5, sec=sec)
            return True
        except InvalidAppSecretError:
            return False

    def cfg_setup(self):
        for secret in self.secrets:
            # Falsy secrets
            if not secret:
                continue

            if self.test_secret(secret):
                self.sec = secret
                break

        if self.sec is None:
            raise InvalidAppSecretError("Can't find any valid app secret.\n" + RESET)
