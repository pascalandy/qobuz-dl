# TOP: Project

État au 2026-11-19 : plan proposé, arrêté au point de contrôle de la Procédure A (étape 8). Aucune vague n'est `active`, aucune issue n'est créée, rien n'est synchronisé avec GitHub.

## Summary

- Objective: `qobuz top "<artiste>"`, tapé sur om1, fait jouer sur le Aurender N100 les titres « Popular » de l'artiste sur Spotify, retrouvés sur Qobuz. Voir [BC §1](00-business-case.md#1-but) et [BC §4](00-business-case.md#4-parcours-cible)
- Stakeholders: Pascal, PM et seul utilisateur. Il est aussi la seule personne qui peut entendre le N100
- Success criteria:
  - SC1: une seule commande sur om1 lance la lecture sur le N100, sans téléphone ni app du fabricant, et le N100 enchaîne seul les pistes de la sélection ([BC §3](00-business-case.md#3-critères-dacceptation-dorigine), [BC §8](00-business-case.md#8-lecture-sur-le-n100))
  - SC2: la file reçoit la meilleure version studio de chaque chanson, dans l'ordre de Spotify ([BC §7](00-business-case.md#7-correspondance-vers-qobuz))
  - SC3: une chanson sans correspondance est sautée et signalée ; un artiste ambigu ou une sélection vide n'écrit rien et sort en erreur ([BC §6](00-business-case.md#6-liste-popular-de-spotify), [BC §10](00-business-case.md#10-cadre-du-cli))
  - SC4: ce qui jouait sur le N100 s'arrête et la sélection prend sa place, selon la règle de file que la question 3 fixera ([BC §3](00-business-case.md#3-critères-dacceptation-dorigine))
  - SC5, sous réserve de la question 4 : la liste privée `Top · <Artiste>` existe dans le compte Qobuz, et une relance la remplace sans doublon ([BC §9](00-business-case.md#9-liste-qobuz))
  - SC6: un install ordinaire de la fourche ne reçoit rien de `top`, les tests par défaut restent hors ligne et `just ci` passe ([BC §12](00-business-case.md#12-contraintes-du-projet))
- Constraints: connexion par `app_id` et `user_auth_token` seulement, jamais `user/login` ([BC §5](00-business-case.md#5-connexion-qobuz)). om1 seulement ([BC §11](00-business-case.md#11-machine-et-installation)). Aucun essai n'imprime un secret. Un essai qui change ce qui joue dans la maison, ou qui écrit dans le compte Qobuz, attend l'accord du PM ([BC §12](00-business-case.md#12-contraintes-du-projet))
- Out of scope: Qobuz Connect et le crate Rust, macOS, le téléchargement de médias, Mixtape ([BC §16](00-business-case.md#16-hors-du-projet))
- Source: [Business case](00-business-case.md) · Agent file: [AGENTS.md](../AGENTS.md)
- QA machine: à confirmer par le PM (question 5). Recommandation : om1. Le défaut du skill est le Mac Mini

## Open questions

Dans l'ordre de l'effet de la réponse sur le plan, le plus grand d'abord.

1. **Le N100 joue-t-il seul des pistes ajoutées par un script ?** ([BC §8](00-business-case.md#8-lecture-sur-le-n100)) → spike dans W01, avec l'accord et la présence du PM
   - Si oui : le plan tient tel quel
   - Si non : le PM choisit la suite à la revue de W01, parmi les pistes de [BC §13](00-business-case.md#13-pistes-de-lecture-non-retenues). La piste A (liste seulement) est le repli le plus proche, mais elle n'est pas acquise : l'écriture dans le compte n'est pas prouvée (ancienne porte G7). Les vagues gardent leurs IDs. La revue replanifie W02 à W05 selon ce choix et renégocie SC1, SC2 et SC4 avec le PM ; pour la piste A, les critères de sortie n'ont plus de lecture
2. **Le jeton connecte-t-il depuis om1, et Spotify et Qobuz rendent-ils ce que la correspondance lit ?** ([BC §5](00-business-case.md#5-connexion-qobuz), [BC §6](00-business-case.md#6-liste-popular-de-spotify), [BC §7](00-business-case.md#7-correspondance-vers-qobuz)) → spikes dans W01, sans le PM
   - Ils reprennent les anciennes portes G2, G3 et G8 : la liste Popular par SpotAPI, et les champs de `track/search`, et de `album/get` au besoin
   - Ces réponses servent toutes les pistes, avec ou sans lecture. Si le jeton échoue, tout le projet est bloqué. Le risque est jugé faible : la même config marche sur le MacBook Pro
3. **`top` remplace-t-il la file du N100 ou y ajoute-t-il ?** → demandée au PM, à trancher à la revue de W01
   - Recommandation : ajouter à la fin et démarrer la première piste ajoutée. Ce qui jouait s'arrête, la sélection joue, et les 331 entrées du PM restent. Un `clear` ne se défait pas depuis `top`
   - Le spike de W01 observe la forme « ajouter » seulement, sans vider la file : la prise de relais sur une piste en cours, l'enchaînement, où la lecture va après la dernière piste ajoutée, et ce que Conductor affiche. La forme « remplacer » n'est pas essayée dans W01
   - Effet : la règle de file est le contrat de l'étape de lecture de W02, et fixe SC4
4. **La liste Qobuz privée reste-t-elle obligatoire ?** ([BC §9](00-business-case.md#9-liste-qobuz)) → demandée au PM, à trancher à la revue de W04
   - Recommandation : non. La lecture n'en dépend plus. La liste reste la dernière vague (W05), décidée d'après l'usage réel
   - Effet : W05 construite ou `dropped`, SC5 gardé ou retiré. Si la question 1 échoue, la revue de W01 reprend cette question plus tôt
5. **Quelle est la machine de QA ?** → demandée au PM
   - Recommandation : om1, dans une session neuve et un checkout séparé de celui de l'implémenteur
   - Pourquoi : le projet ne vise qu'om1 et Linux. Le Mac Mini est sur le même réseau local d'après `fleet.toml` (relevé du 2026-09-27), mais macOS est hors du projet : une QA sur le Mini testerait une plateforme qu'on ne livre pas, et pas l'installation réelle
   - Coût : l'indépendance repose sur la session, pas sur la machine. Le rapport de QA la consigne, comme le skill le demande
   - Effet : chaque brief de QA nomme cette machine
6. **Que devient la page de design ?** ([BC §2](00-business-case.md#2-historique-des-sources)) → demandée au PM
   - Recommandation : la marquer comme remplacée, sans la réécrire. Un bandeau en tête dit que la porte G1 a échoué, que la section C et les portes G1, G4, G5, G5b et G6 ne s'appliquent plus, et que `plan/` porte la suite. Une tâche `chore` de W01 le fait, met `docs/INDEX.md` à jour et répond aux critères de fermeture de l'issue #101
   - Effet : une tâche de W01, aucune vague
7. **L'entier de `qobuz://<entier>` est-il l'identifiant Qobuz de la piste ?** → spike dans W01, dans la même séance que la question 1
   - Si non : W02 gagne une tâche pour trouver la conversion, ou le PM choisit une autre piste comme à la question 1
8. **Le client MPD : bibliothèque standard ou `python-mpd2` ?** ([BC §12](00-business-case.md#12-contraintes-du-projet)) → décision technique à consigner à la revue de W01
   - Recommandation : la bibliothèque standard. Le besoin tient en quelques lignes de texte, et la fourche garde une seule dépendance d'exécution
9. **Conductor affiche-t-il une file modifiée par un autre client, et le N100 joue-t-il en haute résolution une entrée sans suffixe ?** → observations du spike de la question 1
   - Effet : une note dans le brief de l'étape de lecture. Le suffixe `%%<1-4>` n'entre dans W02 que si l'observation le demande
10. **Le changement des dotfiles vit dans un autre dépôt** ([BC §11](00-business-case.md#11-machine-et-installation)) → demandée au PM, avant que W03 devienne `planned`
    - Recommandation : une tâche de W03 dont l'issue est dans `pascalandy/qobuz-dl` et dont la PR est dans `pascalandy/dotfiles`

Le modèle exact du N100 n'est plus une question du plan : sa réponse n'y change rien depuis que Qobuz Connect est sorti. Il reste au dossier ([BC §14](00-business-case.md#14-questions-ouvertes)).

## Présence du PM

Seule une personne dans la maison peut entendre le N100. Le plan n'écrit aucun scénario d'UAT ; il sépare trois choses.

- **Une séance d'écoute, dans W01.** Les spikes des questions 1, 7 et 9 se font en une seule séance, sur l'accord du PM, avec le PM devant le N100. Le PM y est le témoin d'une tâche `spike`, pas un testeur : il dit ce qu'il entend, et le résultat va sur l'issue du spike
- **Un témoin lisible par machine, pour la suite.** La même séance compare ce que le PM entend avec ce que MPD rapporte (`status`, `currentsong`). Si les deux concordent, les critères d'acceptation et les scénarios de QA des vagues suivantes lisent MPD et n'ont plus besoin d'une oreille
- **L'accord avant de toucher au N100.** Toute tâche et toute tâche de QA qui change ce qui joue porte cette condition dans son brief : elle ne démarre que sur l'accord du PM. Les tests par défaut n'approchent jamais le N100
- Ce que le PM veut encore entendre après une vague relève de son UAT. Il le choisit en lisant les rapports de QA

## Limits

- Task: one module or ≤ 8 files, ≤ ~400 changed lines, ≤ 5 acceptance items, no open decision.
- QA: intermediate QA when an epic has > 5 tasks or spans > 2 batches; ≤ 8 QA scenarios per QA task.
- Recalibrated: never (initial limits)
- Taille : le projet est petit. Chaque vague aura moins que la cible de 10 à 30 tâches du skill

Next IDs: E01, D003

## Waves

| ID | Name | Goal | Status | File |
|---|---|---|---|---|
| W01 | n100-playback-proof | Prouver qu'un script sur om1 fait jouer des pistes Qobuz sur le N100, et lever les autres inconnues avant de construire | proposed | [W01](waves/W01-n100-playback-proof.md) |
| W02 | top-plays | `qobuz-dl top "<artiste>"`, lancé du checkout sur om1, fait jouer les titres Popular sur le N100, avec une correspondance simple | proposed | [W02](waves/W02-top-plays.md) |
| W03 | om1-daily-use | Le PM tape `qobuz top "<artiste>"` sur om1, avec le compte lu dans la voûte | proposed | [W03](waves/W03-om1-daily-use.md) |
| W04 | studio-selection | La sélection suit toutes les règles : version studio, album avant single, meilleure résolution | proposed | [W04](waves/W04-studio-selection.md) |
| W05 | qobuz-playlist | La sélection est aussi une liste privée du compte Qobuz, remplacée à chaque relance | proposed | [W05](waves/W05-qobuz-playlist.md) |

Raisons de l'ordre :

- W01 est le test de l'hypothèse la plus risquée, pas un squelette ambulant. Un squelette demanderait la connexion, Spotify et la correspondance avant de toucher à la seule inconnue qui peut renverser le projet
- W02 est le squelette ambulant : une tranche mince, de la commande au son. Elle porte aussi les refus sans écriture (artiste ambigu, sélection vide), pour qu'ils existent avant l'usage quotidien
- W03 vient avant W04 pour que le PM se serve de la commande tôt. Son usage réel nourrit les règles de W04
- W05 est dernière parce qu'elle est conditionnelle (question 4)
