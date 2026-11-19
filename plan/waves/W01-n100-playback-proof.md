---
id: W01
project: TOP
status: proposed
label: wave:W01
---

# W01: n100-playback-proof

## Goal
Prouver qu'un script sur om1 fait jouer une piste Qobuz sur le N100, et lever les autres inconnues avant de construire quoi que ce soit.

## Exit criteria
- [ ] Le PM entend sur le N100 une piste Qobuz qu'un script sur om1 a ajoutée et démarrée, et MPD rapporte `state: play` sur cette entrée
- [ ] La piste entendue est celle dont l'identifiant Qobuz a été envoyé, et ce que MPD rapporte concorde avec ce que le PM entend pendant toute la séance
- [ ] Depuis om1, une lecture authentifiée par `app_id` et `user_auth_token` réussit avec la config de la voûte, et SpotAPI rend une liste Popular ordonnée et non vide
- [ ] Les décisions sur la règle de file, la liste Qobuz et le client MPD sont consignées dans `decisions.md`
- [ ] La page de design dit que la voie Qobuz Connect est remplacée et pointe vers `plan/`

## Scope
- Une séance d'écoute, sur l'accord du PM et en sa présence : une piste ajoutée et démarrée par script, l'identité de l'entier de `qobuz://<entier>`, le passage seul à la piste suivante, où va la lecture après la dernière piste ajoutée, ce que Conductor affiche, la qualité affichée sans suffixe. La file du PM n'est jamais vidée pendant la séance ([BC §8](../00-business-case.md#8-lecture-sur-le-n100))
- Les spikes sans le PM : om1 lit le compte dans la voûte, le jeton connecte sans courriel ni mot de passe, Spotify répond sans identifiants, `track/search` porte les champs que la correspondance lit ([BC §5](../00-business-case.md#5-connexion-qobuz), [BC §6](../00-business-case.md#6-liste-popular-de-spotify), [BC §7](../00-business-case.md#7-correspondance-vers-qobuz))
- Chaque spike est un script jetable, sans PR. Son résultat est une recommandation sur son issue. Aucun n'imprime un secret
- La première tâche met `AGENTS.md` à jour : le plan, la commande de vérification `just ci`, et comment joindre le N100 pour un essai
- Une tâche `chore` marque la page de design comme remplacée et met `docs/INDEX.md` à jour ([BC §2](../00-business-case.md#2-historique-des-sources))
- Hors de la vague : tout code de `top`, toute écriture dans le compte Qobuz, toute commande `clear`
