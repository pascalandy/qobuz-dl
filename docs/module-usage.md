# Module usage

`qobuz-dl` can be imported as a library by using `QobuzDL` from `qobuz_dl.core`.

For local development, run scripts through `uv run` so the project environment supplies the dependencies.

```python
import getpass
import hashlib
import logging
from qobuz_dl.core import QobuzDL

logging.basicConfig(level=logging.INFO)

email = input("Qobuz email: ")
password_plaintext = getpass.getpass("Qobuz password: ")
password_md5 = hashlib.md5(password_plaintext.encode("utf-8")).hexdigest()

qobuz = QobuzDL()
qobuz.get_tokens()  # get 'app_id' and 'secrets' attrs
qobuz.initialize_client(email, password_md5, qobuz.app_id, qobuz.secrets)

qobuz.handle_url("https://play.qobuz.com/album/va4j3hdlwaubc")
```

`initialize_client` forwards its password argument unchanged. Pass one lowercase MD5 hexadecimal digest computed from the UTF-8 plaintext password, as shown above. If you load an existing digest from `config.ini`, pass it unchanged. Do not hash the digest again.

The digest is not encryption. Treat it as credential-equivalent because the current login flow can use it without the plaintext password. See [Authentication credential and transport evidence](research/authentication-transport.md) for the current request placement and its verification limits.

## API rate-limit errors

`QobuzDL` propagates `qobuz_dl.exceptions.ApiRateLimitError` when a replay-safe Qobuz API read exhausts its bounded `429` retries. A collection stops before the next queued item.

The retry helper lets `KeyboardInterrupt` propagate. An interactive caller can handle the interruption.

See [API rate-limit retries](cli.md#api-rate-limit-retries) for the attempt, wait, and endpoint limits.

## Audio rate-limit results

Audio acquisition exhaustion follows the normal download result contract. It returns a `failed` result with reason `request_error`. A partial album preserves paths finalized before the failed track, and cancellation propagates `KeyboardInterrupt`.

See [audio rate-limit retries](cli.md#audio-rate-limit-retries) for the shared limits and media integrity rules.

## Download results

`QobuzDL.download_from_id(item_id, album=True, alt_path=None)` returns an immutable `DownloadResult` with three fields:

| Field | Meaning |
|---|---|
| `state` | `finalized` when the top-level request completed, `ignored` when it was deliberately skipped or contained an ignored item, or `failed` when it could not complete |
| `reason` | Representative outcome: `downloaded`, `verified_artifact`, `existing_file`, `type_filter`, `quality_filter`, `demo`, `missing_url`, `not_streamable`, `request_error`, `tagging_error`, `path_conflict`, `media_error`, `publish_error`, or `empty_release` |
| `finalized_paths` | Ordered tuple of final audio path strings confirmed during this attempt; partial albums may return paths even when their overall state is `ignored` or `failed` |

Direct track, album, Qobuz playlist, and matched Last.fm playlist requests return `verified_artifact` only after the exact destination artifact passes track identity, digest, media, and effective-quality checks. A missing or nonmatching album child is downloaded while verified children remain in place. Unknown occupied paths return `path_conflict`. Invalid or mismatched media evidence returns `media_error`, and a safe-publication failure returns `publish_error`. Legacy ID-only rows do not satisfy a request.

With no persistent database path, `QobuzDL` keeps verified evidence in memory for the process lifetime. A later occurrence in that process can return `verified_artifact`. An unexplained pre-existing path still returns `path_conflict`.

```python
result = qobuz.download_from_id("va4j3hdlwaubc", album=True)

if result.state == "finalized":
    print(*result.finalized_paths, sep="\n")
else:
    print(f"{result.state}: {result.reason}")
```

Attributes, methods, and parameters are named to describe their purpose.
