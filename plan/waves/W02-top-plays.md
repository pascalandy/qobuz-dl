---
id: W02
project: TOP
status: proposed
label: wave:W02
---

# W02: top-plays

## Goal
`qobuz-dl top "<artiste>"`, lancé du checkout sur om1, fait jouer sur le N100 les titres Popular de l'artiste, avec une correspondance simple.

## Exit criteria
- [ ] Sur om1, `uv run qobuz-dl top "Dire Straits"` avec la config de la voûte sort en `0`, et MPD rapporte en lecture la première piste de la sélection
- [ ] La file du N100 contient les pistes retenues, dans l'ordre de Spotify, placées selon la règle de file décidée à la revue de W01
- [ ] Une chanson sans correspondance est nommée dans la sortie, et les autres jouent
- [ ] `just ci` passe sans réseau, sans compte Qobuz et sans N100

## Scope
- La connexion par jeton pour `top` : `app_id` et `user_auth_token`, jamais `user/login` ([BC §5](../00-business-case.md#5-connexion-qobuz))
- La liste Popular par SpotAPI, en dépendance optionnelle, avec le secret TOTP épinglé ([BC §6](../00-business-case.md#6-liste-popular-de-spotify))
- Une correspondance simple : titre, artiste, durée à 3 secondes près, piste que le compte peut écouter. Les règles complètes sont dans W04 ([BC §7](../00-business-case.md#7-correspondance-vers-qobuz))
- L'étape de lecture : le client MPD, l'ajout des pistes une par une, le démarrage, et la confirmation par `status` ([BC §8](../00-business-case.md#8-lecture-sur-le-n100))
- Le cadre du CLI : `top` lancé avant l'état de téléchargement, `--dry-run` refusé, codes de sortie ([BC §10](../00-business-case.md#10-cadre-du-cli))
- Des fixtures hors ligne pour Spotify, Qobuz et MPD, tirées des réponses que les spikes de W01 ont observées
