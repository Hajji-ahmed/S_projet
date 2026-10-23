#!/bin/bash
# Déploiement automatique de SIMTIS (23/10/2026), lancé par cron toutes les 5 minutes sur le serveur :
#   */5 * * * * $HOME/simtis/deploy/auto-deploy.sh >> $HOME/backups/deploiement.log 2>&1
# Quand la branche suivie a un nouveau commit ET que la CI GitHub de ce commit est verte : sauvegarde
# de la base, code mis à jour, application reconstruite et redémarrée, contrôle de santé. Le serveur va
# chercher (clé de déploiement en lecture seule) : rien n'entre depuis l'extérieur, une pull request n'est
# jamais exécutée. Un commit dont la CI ou le déploiement a échoué n'est pas retenté (fichier .deploiement-echoue).
set -euo pipefail

DOSSIER="${SIMTIS_DOSSIER:-$HOME/simtis}"
BRANCHE="${SIMTIS_BRANCHE:-hajji}"
DEPOT="${SIMTIS_DEPOT:-Hajji-ahmed/S_projet}"
COMPOSE=(docker compose -f docker-compose.prod.yml)

journal() { echo "$(date '+%F %T') $*"; }

# Un seul déploiement à la fois
exec 9>/tmp/simtis-auto-deploy.lock
flock -n 9 || exit 0

cd "$DOSSIER"
git fetch -q origin "$BRANCHE"
DISTANT=$(git rev-parse "origin/$BRANCHE")
DEPLOYE=$(cat .deploiement-ok 2>/dev/null || git rev-parse HEAD)
[ "$DISTANT" = "$DEPLOYE" ] && exit 0
[ "$DISTANT" = "$(cat .deploiement-echoue 2>/dev/null)" ] && exit 0
COURT=${DISTANT:0:7}

# État de la CI du commit (API GitHub) : attente, verte ou rouge. Dépôt privé : jeton en lecture seule
# (« Checks : Read-only ») dans ~/.simtis-github-token (chmod 600) ; sans ce fichier, appel anonyme
JETON_FICHIER="${SIMTIS_JETON:-$HOME/.simtis-github-token}"
AUTH=()
if [ -r "$JETON_FICHIER" ]; then
  AUTH=(-H "Authorization: Bearer $(tr -d '[:space:]' < "$JETON_FICHIER")")
fi
ETAT=$(curl -fsS -m 20 -H "Accept: application/vnd.github+json" "${AUTH[@]}" \
  "https://api.github.com/repos/$DEPOT/commits/$DISTANT/check-runs?per_page=100" |
  python3 -c '
import json, sys
runs = json.load(sys.stdin).get("check_runs", [])
if not runs or any(r["status"] != "completed" for r in runs):
    print("attente")
elif all(r["conclusion"] in ("success", "skipped", "neutral") for r in runs):
    print("verte")
else:
    print("rouge")
' 2>/dev/null) || { journal "$COURT : CI illisible (GitHub injoignable ?), nouvel essai dans 5 min"; exit 0; }

case "$ETAT" in
  attente) exit 0 ;;
  rouge)
    journal "$COURT : CI en échec, commit NON déployé"
    echo "$DISTANT" > .deploiement-echoue
    exit 0 ;;
esac

journal "$COURT : CI verte, déploiement…"
"$HOME/sauvegarde-simtis.sh" || { journal "$COURT : sauvegarde impossible, déploiement annulé"; exit 1; }
git reset -q --hard "$DISTANT"

if "${COMPOSE[@]}" up -d --build --wait >/tmp/simtis-auto-deploy-build.log 2>&1 \
  && curl -fsS -m 20 http://localhost/api/health | grep -q '"status":"ok"'; then
  echo "$DISTANT" > .deploiement-ok
  rm -f .deploiement-echoue
  docker image prune -f >/dev/null 2>&1 || true
  docker builder prune -f --filter until=168h >/dev/null 2>&1 || true
  journal "$COURT : déployé ($(git log -1 --format=%s))"
else
  echo "$DISTANT" > .deploiement-echoue
  journal "$COURT : ÉCHEC du déploiement, voir /tmp/simtis-auto-deploy-build.log"
  tail -20 /tmp/simtis-auto-deploy-build.log
  exit 1
fi
