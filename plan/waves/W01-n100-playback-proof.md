---
id: W01
project: TOP
status: proposed
label: wave:W01
---

# W01: n100-playback-proof

## Goal
Prouver qu'un script sur om1 fait jouer des pistes Qobuz sur le N100, et lever les autres inconnues avant de construire quoi que ce soit.

## Exit criteria
- [ ] Pendant qu'une autre piste joue, un script sur om1 ajoute deux pistes Qobuz et démarre la première : le PM l'entend prendre la place de ce qui jouait, et MPD rapporte `state: play` sur cette entrée
- [ ] Une fois le script terminé, sans téléphone ni Conductor, le N100 passe seul à la deuxième piste ajoutée
- [ ] Les pistes entendues sont celles dont les identifiants Qobuz ont été envoyés, et ce que MPD rapporte concorde avec ce que le PM entend pendant toute la séance
- [ ] Depuis om1, une lecture authentifiée par `app_id` et `user_auth_token` réussit avec la config de la voûte ; SpotAPI rend une liste Popular ordonnée, et les réponses de Qobuz portent chaque champ que la correspondance lit. Le résultat consigne la version de SpotAPI et le secret épinglé qui ont servi
- [ ] Les décisions sur la règle de file et le client MPD sont dans `decisions.md`, et la page de design consigne le résultat de G1, la voie de lecture révisée et les portes retirées, avec un lien vers `plan/`

## Scope
- Une séance d'écoute, sur l'accord du PM et en sa présence : deux pistes ajoutées et la première démarrée par script pendant qu'une autre piste joue, l'identité de l'entier de `qobuz://<entier>`, le passage seul à la piste suivante après la fin du script, où va la lecture après la dernière piste ajoutée, ce que Conductor affiche, la qualité affichée sans suffixe. La file du PM n'est jamais vidée pendant la séance ([BC §8](../00-business-case.md#8-lecture-sur-le-n100))
- Les spikes sans le PM : om1 lit le compte dans la voûte, le jeton connecte sans courriel ni mot de passe, Spotify répond sans identifiants, `track/search`, et `album/get` au besoin, portent les champs que la correspondance lit ([BC §5](../00-business-case.md#5-connexion-qobuz), [BC §6](../00-business-case.md#6-liste-popular-de-spotify), [BC §7](../00-business-case.md#7-correspondance-vers-qobuz))
- Chaque spike est un script jetable, sans PR. Son résultat est une recommandation sur son issue. Aucun n'imprime un secret
- La première tâche met `AGENTS.md` à jour : le plan, la commande de vérification `just ci`, et comment joindre le N100 pour un essai
- Une tâche `chore` marque la page de design comme remplacée et met `docs/INDEX.md` à jour ([BC §2](../00-business-case.md#2-historique-des-sources))
- Hors de la vague : tout code de `top`, toute écriture dans le compte Qobuz, toute commande `clear`
