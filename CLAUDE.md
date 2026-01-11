\# CLAUDE.md



\## Git Workflow — OBLIGATOIRE



\*\*Avant CHAQUE commit, TOUJOURS exécuter :\*\*

```bash

git fetch origin \&\& git pull origin main --ff-only

```



Ceci est CRITIQUE pour éviter les divergences de branches quand plusieurs sessions Claude Code travaillent en parallèle.



\## Pourquoi ?



Un outil externe (`git\_claude\_helper.py`) synchronise automatiquement les branches `claude/\*` avec `main`. Si tu ne fetch/pull pas avant de committer, tu risques de travailler sur une base obsolète et créer des conflits.



\## Workflow type



1\. `git fetch origin \&\& git pull origin main --ff-only`

2\. Faire les modifications

3\. `git add .`

4\. `git commit -m "..."`

5\. `git push`



\## En cas d'erreur "non-fast-forward"

```bash

git fetch origin

git pull origin main --ff-only

\# puis réessayer le push

```

