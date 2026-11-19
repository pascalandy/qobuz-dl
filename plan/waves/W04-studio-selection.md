---
id: W04
project: TOP
status: proposed
label: wave:W04
---

# W04: studio-selection

## Goal
La sélection que `top` fait jouer suit toutes les règles du dossier d'affaires : version studio, meilleure résolution, artiste sans ambiguïté.

## Exit criteria
- [ ] Sur un jeu de fixtures tiré de vraies réponses, `top` retient pour chaque chanson la version studio attendue et écarte les live, démos, remix, réenregistrements et compilations
- [ ] Entre deux versions studio du même type de parution, `top` retient celle de plus haute résolution que le compte peut écouter
- [ ] Un nom d'artiste qui désigne zéro ou plusieurs candidats exacts liste les candidats, sort en erreur et ne touche ni au N100 ni au compte
- [ ] Sur om1, `qobuz top` pour trois artistes choisis par le PM sort en `0`, et la sortie nomme chaque chanson sautée

## Scope
- Les règles 1 à 5 de la correspondance, au complet : normalisation des titres, `release_type` lu par `album/get` au besoin, studio seulement, pistes écoutables, ordre album puis single puis inconnu, puis résolution ([BC §7](../00-business-case.md#7-correspondance-vers-qobuz))
- Le choix de l'artiste : un seul candidat au nom exact, sans casse ni accents ([BC §6](../00-business-case.md#6-liste-popular-de-spotify))
- Les sorties en erreur : rien ne correspond, artiste ambigu, lecture non confirmée ([BC §10](../00-business-case.md#10-cadre-du-cli))
- La qualité demandée au N100, seulement si la séance de W01 a montré qu'une entrée sans suffixe ne joue pas en haute résolution ([BC §8](../00-business-case.md#8-lecture-sur-le-n100))
- Les écarts que le PM a relevés en se servant de la commande depuis W03
