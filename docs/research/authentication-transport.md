# Authentication credential and transport evidence

This note separates the credential representations used by `qobuz-dl` from observations about the public Qobuz web client. It records evidence, not a server contract.

## Evidence snapshot

The public files were retrieved without credentials on 2026-09-12 at `2026-09-12T03:47:26Z`. The requests sent no account identifiers, request bodies, cookies, or authentication headers.

| Artifact | URL | SHA-256 |
|---|---|---|
| Login page | `https://play.qobuz.com/login` | `5a785cc320bffa5b7f683a4303d73a7756c1b02d1a886c6781ff7bc2c9d72877` |
| Web client bundle `8.2.0-b034` | `https://play.qobuz.com/resources/8.2.0-b034/bundle.js` | `bfa7fde65714cdac274313e370d1e6ee33af99ca548345e71dad3384ae8ae011` |

The login page selects `/resources/8.2.0-b034/bundle.js`. The bundle offsets below are zero-based byte offsets in the file identified by the full SHA-256 digest.

| Offset | Safe excerpt | Observation |
|---|---|---|
| `3230607` | `postForm("user/login",{query:t})` | The bundle has a form POST wrapper for `user/login`. |
| `5314375` | `extra:"partner"` | The only traced caller of that wrapper supplies `extra=partner`. Its requester already carries a user authentication token through the shared request transformer. |
| `7176854` | `"X-User-Auth-Token":n,"X-App-Id":e` | The request transformer adds the existing token and the app ID to request headers. |
| `7177922` | `encodeURIComponent(r),encodeURIComponent(p(n))` | The form serializer URL-encodes each field name and value before joining the fields into a string. |
| `7179511` | `headers:e.params.header,body:r,method:"POST"` | This POST path forwards the transformed headers and string body. It does not set an explicit `Content-Type`. |
| `7988538` | `favorite/getUserFavorites` | The public Favorites wrapper uses the requester's GET method. Its shared request transformer adds authentication headers. |

The excerpts omit runtime values. No account identifier, password digest, token, application secret, signed URL, query string, request body, cookie, or session capture is part of this record.

## Current local credential flow

The CLI and the importable library use three distinct credential representations:

1. `_reset_config` reads the plaintext password with `getpass`, so terminal input is hidden.
2. `_reset_config` encodes that plaintext as UTF-8 and computes one lowercase MD5 hexadecimal digest. It stores the digest under the historical `password` config key.
3. CLI startup passes the stored digest to `QobuzDL.initialize_client` unchanged.
4. `QobuzDL.initialize_client(email, pwd, app_id, secrets)` passes `pwd` to `qopy.Client` unchanged. A library caller must supply the digest used by this flow. It must not hash an existing digest again.
5. `qopy.Client` currently sends `GET user/login` with `email`, the digest in `password`, and `app_id` as query fields.
6. A successful login keeps the returned user token in memory and installs it as the `X-User-Auth-Token` session header.
7. `favorite/getUserFavorites` currently uses GET. The request includes the user token in both the query and the session header.

The MD5 digest is not encryption. Treat the stored digest as credential-equivalent because the current login flow can use it without the plaintext password.

The offline characterization in `tests/test_auth_contract.py` proves one UTF-8 MD5 operation during CLI setup, unchanged forwarding through `initialize_client`, and the current request placement with synthetic values. It also blocks sockets. It does not prove what the Qobuz server accepts or requires.

## What the public client proves

The bundle proves that this version of the public client contains these paths:

- One traced `postForm("user/login", ...)` caller passes `extra=partner` with an existing token
- That form path uses a URL-encoded string body without an explicit `Content-Type`
- The Favorites wrapper uses GET and shared authentication headers

The first path does not prove that Qobuz accepts an email and MD5 password in a POST body. It is a token-authenticated partner refresh path, not evidence for password login transport.

The Favorites code does not prove that Qobuz accepts the user token only in a header. Client code shows what it sends. It does not establish which fields the server requires.

## Unsupported server inferences

This evidence does not establish any of these claims:

- `user/login` accepts an email and MD5 password through POST
- A POST body has a server-supported `Content-Type` when the client omits that header
- `favorite/getUserFavorites` accepts header-only authentication
- The current `qobuz-dl` GET query fields are required by Qobuz
- The current `qobuz-dl` transport was live-verified against the server during this investigation

`qobuz-dl` therefore keeps its current GET, query, and token placement behavior. [Issue #63](https://github.com/pascalandy/qobuz-dl/issues/63) owns separate verification through an accessible primary contract or an explicitly authorized server check. Missing evidence remains a blocker for a transport change.
