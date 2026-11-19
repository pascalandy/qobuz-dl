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
- [ ] Sur om1, `top "Dire Straits"` lancé du checkout sort en `0`, MPD rapporte en lecture la première piste de la sélection, puis la deuxième sans autre commande
- [ ] La file du N100 contient les pistes retenues, dans l'ordre de Spotify, placées selon la règle de file décidée à la revue de W01
- [ ] Une chanson sans correspondance est nommée dans la sortie, et les autres jouent
- [ ] Un nom d'artiste qui désigne zéro ou plusieurs candidats exacts, ou une sélection vide, sort en erreur, et la file du N100 est la même avant et après
- [ ] `just ci` passe sans réseau, sans compte Qobuz et sans N100, et `just verify-install` passe encore : `mutagen` reste la seule dépendance d'un install ordinaire

## Scope
- Les entrées de l'essai lancé du checkout : l'extra `top`, la config de la voûte passée par `--config`, et l'adresse du N100. Cette vague fixe d'où `top` lit l'adresse ; W03 n'ajoute que la commande installée
- Le choix de l'artiste : un seul candidat au nom exact, sans casse ni accents ([BC §6](../00-business-case.md#6-liste-popular-de-spotify))
- La connexion par jeton pour `top` : `app_id` et `user_auth_token`, jamais `user/login` ([BC §5](../00-business-case.md#5-connexion-qobuz))
- La liste Popular par SpotAPI, en dépendance optionnelle, avec le secret TOTP épinglé. Le vérificateur d'installation (`scripts/verify_install.py`) compte aujourd'hui toute déclaration de dépendance, extras compris : il doit continuer de passer ([BC §6](../00-business-case.md#6-liste-popular-de-spotify))
- Une correspondance simple : titre, artiste, durée à 3 secondes près, piste que le compte peut écouter. Les règles complètes sont dans W04 ([BC §7](../00-business-case.md#7-correspondance-vers-qobuz))
- L'étape de lecture : le client MPD, l'ajout des pistes une par une, le démarrage, et la confirmation par `status` ([BC §8](../00-business-case.md#8-lecture-sur-le-n100))
- Le cadre du CLI : `top` lancé avant l'état de téléchargement, `--dry-run` refusé, codes de sortie ([BC §10](../00-business-case.md#10-cadre-du-cli))
- Des fixtures hors ligne pour Spotify, Qobuz et MPD, tirées des réponses que les spikes de W01 ont observées
