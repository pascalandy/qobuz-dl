# TOP: Decisions

La décision sur les vagues initiales et leur raison sera consignée quand le PM approuvera le point de contrôle (Procédure A, étape 12). Elle prendra le prochain ID libre.

## D001: Qobuz Connect sort du plan, le port MPD du N100 est la voie à prouver
- Date: 2026-11-19
- Trigger: décision du PM (issue #101)
- Decision: Qobuz Connect ne peut pas piloter ce N100. Le crate Rust `connect/`, les JWT Connect et les portes G1, G4, G5, G5b et G6 de la page de design ne sont plus la voie de lecture. La voie étudiée est la piste B : des commandes MPD envoyées en Python au port TCP 12019 du N100, sur le réseau local
- Why: la porte G1 a échoué. Conductor n'offre pas Qobuz Connect sur cet appareil, alors que le logiciel est à jour. Deux enquêtes indépendantes jugent la piste B probablement faisable. Elle n'est pas prouvée : W01 la teste
- Affects: tout le plan. W01 (test de l'hypothèse), W02 (étape de lecture)

## D002: Langue des fichiers de `plan/`
- Date: 2026-11-19
- Trigger: structure du plan
- Decision: dans `plan/`, la prose est en français. Les entrées d'epic et les briefs sont en anglais, écrits avec le skill `asd-ste100`, parce que les issues GitHub reçoivent ce texte. Les IDs, les noms de fichier, les étiquettes, les commandes et les titres de section des gabarits restent en anglais
- Why: c'est la règle du skill `rolling-wave-planning`. Le dépôt n'a pas de règle écrite sur la langue, mais tous ses documents sous `docs/` sont en anglais. `plan/` s'en écarte, et le skill l'emporte dans `plan/`
- Affects: tous les fichiers de `plan/`
