# Qobuz access and project status

## Decision

As of 12 September 2026, `qobuz-dl` remains an unofficial Beta project. It is not affiliated with or certified by Qobuz.

The project keeps its current access mode. During setup, it derives app parameters from Qobuz's public web bundle. It does not ship project-owned credentials or claim access through a Qobuz partner agreement. This behavior may break when Qobuz changes the bundle, the service, or the accepted request behavior.

Users need an eligible Qobuz account and subscription. The tool does not grant content rights or bypass account, subscription, territory, or catalog restrictions.

## Evidence boundaries

Public documents help explain the surrounding access model, but they do not establish current Qobuz approval, a current contract, or legal compliance for this project or a user's actions.

| Evidence | What it establishes | What it does not establish |
| --- | --- | --- |
| [Qobuz API Terms of Use](https://static.qobuz.com/apps/api/QobuzAPI-TermsofUse.pdf), effective 1 September 2011 | This dated API document describes Qobuz-issued application identifiers, access restrictions, and a non-certified application notice | It does not show that Qobuz issued credentials to this project, approved this project, or still offers the same agreement on the same terms |
| [Qobuz Apps & UX Guidelines V1.0](https://static.qobuz.com/apps/api/Qobuz-AppsGuidelines-V1.0.pdf), revised 15 January 2014 | This dated integration guide describes third-party app capabilities and refers to separate API integration documentation | It does not provide a current endpoint contract or prove that the referenced developer access remains available |
| [Qobuz General Conditions of Use and Sale](https://www.qobuz.com/gb-en/legal/terms), accessed 12 September 2026 | This public page states general account, subscription, service, and content conditions | The page exposes no revision date. Its availability does not approve this client or resolve how the older API documents apply today |
| `developer.qobuz.com`, checked during the 2026 research passes | The project could not access a current official developer portal or endpoint reference | An unavailable portal proves neither that public developer access exists nor that it has ended |
| Current source and offline tests | The client fetches the public login page and bundle, derives app parameters, and uses Qobuz-style endpoints | Observed code behavior and mocked tests do not prove server acceptance, authorization, contractual permission, or legal compliance |

The detailed source review remains in [Qobuz official API and SDK research](research/qobuz-official-api.md). The dated bundle and request observations remain in [Authentication credential and transport evidence](research/authentication-transport.md).

## Public notices

The project uses these statements in maintained public documentation:

- This application uses the Qobuz API but is not certified by Qobuz
- `qobuz-dl` is unofficial and is not affiliated with Qobuz
- Users are responsible for checking the terms and laws that apply to their account, subscription, location, and use

These notices explain the project's position. They are not legal advice and do not convert the bundle-derived access mode into an approved integration.

## Consequences

The package Trove classifier is `Development Status :: 4 - Beta`. The classifier describes project maturity. It does not make a legal or contractual claim.

The current bundle-derived implementation remains unchanged. A future migration to issued credentials, a documented partner flow, or another access mode requires a separate decision with current primary evidence.
