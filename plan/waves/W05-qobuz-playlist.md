---
id: W05
project: TOP
status: proposed
label: wave:W05
---

# W05: qobuz-playlist

Vague conditionnelle : voir la question 3 de `01-project.md`. Si le PM juge la liste inutile, la vague passe à `dropped`. Si la séance de W01 échoue, elle devient obligatoire et remonte en deuxième place.

## Goal
La sélection de `top` est aussi une liste privée `Top · <Artiste>` du compte Qobuz, remplacée à chaque relance.

## Exit criteria
- [ ] Après `qobuz top "Dire Straits"`, le compte a une seule liste qui porte le marqueur de cet artiste : elle est privée, nommée `Top · Dire Straits`, et ses pistes égalent la sélection, dans l'ordre
- [ ] Après une deuxième exécution, le compte a encore une seule liste avec ce marqueur, et son identifiant a changé
- [ ] Si la vérification de la nouvelle liste échoue, `top` la supprime, laisse les anciennes et sort en erreur
- [ ] Une sélection vide n'écrit rien dans le compte

## Scope
- Un spike d'abord, sur l'accord du PM, parce qu'il écrit dans le compte : le remplacement lancé deux fois avec un marqueur d'essai et deux pistes, puis le nettoyage ([BC §9](../00-business-case.md#9-liste-qobuz))
- Le POST dans `qobuz_dl/http.py`, en `application/x-www-form-urlencoded`
- Le remplacement : créer, ajouter, relire, vérifier, puis supprimer les autres listes au même marqueur
- L'ordre entre la liste et la lecture, et ce que `top` dit quand l'une réussit et l'autre échoue ([BC §10](../00-business-case.md#10-cadre-du-cli))
- Hors de la vague : `playlist/deleteTracks`, et toute liste publique
