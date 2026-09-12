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

## Download results

`QobuzDL.download_from_id(item_id, album=True, alt_path=None)` returns an immutable `DownloadResult` with three fields:

| Field | Meaning |
|---|---|
| `state` | `finalized` when the top-level request completed, `ignored` when it was deliberately skipped or contained an ignored item, or `failed` when it could not complete |
| `reason` | Representative outcome: `downloaded`, `existing_file`, `database_duplicate`, `type_filter`, `quality_filter`, `demo`, `missing_url`, `not_streamable`, `request_error`, `tagging_error`, or `empty_release` |
| `finalized_paths` | Ordered tuple of final audio path strings confirmed during this attempt; partial albums may return paths even when their overall state is `ignored` or `failed` |

Only a `finalized` result is added to duplicate history. A database duplicate returns `ignored` with reason `database_duplicate` and an empty `finalized_paths` tuple because the database check does not inspect the filesystem.

```python
result = qobuz.download_from_id("va4j3hdlwaubc", album=True)

if result.state == "finalized":
    print(*result.finalized_paths, sep="\n")
else:
    print(f"{result.state}: {result.reason}")
```

Attributes, methods, and parameters are named to describe their purpose.
