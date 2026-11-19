---
id: W04
project: TOP
status: proposed
label: wave:W04
---

# W04: studio-selection

## Goal
La sélection que `top` fait jouer suit toutes les règles du dossier d'affaires : version studio, album avant single, meilleure résolution.

## Exit criteria
- [ ] Sur un jeu de fixtures tiré de vraies réponses, la sélection de `top` égale la suite attendue d'identifiants Qobuz, dans l'ordre de Spotify, et écarte les live, démos, remix, réenregistrements et compilations
- [ ] Ce jeu contient une chanson dont l'album l'emporte sur un single de plus haute résolution, et une chanson parue seulement en single, qui est retenue
- [ ] Entre deux versions studio du même type de parution, `top` retient celle de plus haute résolution que le compte peut écouter
- [ ] Sur om1, `qobuz top` pour trois artistes choisis par le PM sort en `0`, et la sortie nomme chaque chanson sautée

## Scope
- Les règles 1 à 5 de la correspondance, au complet : normalisation des titres, `release_type` lu par `album/get` au besoin, studio seulement, pistes écoutables, ordre album puis single puis inconnu, puis résolution ([BC §7](../00-business-case.md#7-correspondance-vers-qobuz))
- Les sorties en erreur qui restent après W02 : lecture non confirmée ([BC §10](../00-business-case.md#10-cadre-du-cli))
- La qualité demandée au N100, seulement si la séance de W01 a montré qu'une entrée sans suffixe ne joue pas en haute résolution ([BC §8](../00-business-case.md#8-lecture-sur-le-n100))
- Les écarts que le PM a relevés en se servant de la commande depuis W03
