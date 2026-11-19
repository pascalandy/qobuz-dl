---
id: W03
project: TOP
status: proposed
label: wave:W03
---

# W03: om1-daily-use

## Goal
Le PM tape `qobuz top "<artiste>"` dans un terminal d'om1, et la commande installée lit le compte dans la voûte.

## Exit criteria
- [ ] Après `just install`, `qobuz-dl` se trouve dans `~/.local/bin` avec l'extra `top`, et la recette vérifie que la commande se résout sur le `PATH`
- [ ] Dans un nouveau terminal d'om1, `qobuz top "Dire Straits"` sort en `0` et MPD rapporte la sélection en lecture
- [ ] Après la commande, aucun fichier de config Qobuz ne reste sur om1
- [ ] Un install ordinaire de la fourche, sans l'extra, n'importe pas SpotAPI, et `qobuz-dl dl --help` y fonctionne

## Scope
- La recette `just install` : `uv tool install` depuis le checkout, avec l'extra `top` ([BC §11](../00-business-case.md#11-machine-et-installation))
- La branche Linux de la fonction zsh `qobuz` des dotfiles, qui passe le fichier temporaire de la voûte avec `--config`. Ce travail est dans le dépôt `pascalandy/dotfiles` : voir la question 10 de `01-project.md`
- L'adresse du N100, fournie à la commande installée de la façon que W02 a fixée
- Les documents que `top` rend périmés : `docs/dependencies.md`, `docs/packaging.md`, `docs/architecture.md`, `docs/cli.md` ([BC §12](../00-business-case.md#12-contraintes-du-projet))
- Hors de la vague : macOS, et tout fichier de config permanent sur om1
