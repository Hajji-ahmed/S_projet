---
name: simtis-plan
description: Use when the user asks to implement, create, add, build, modify, fix, refactor or configure anything in the SIMTIS application (backend, frontend, database, migrations, Docker, CI, tests, dependencies), in French or English (« implémente », « ajoute », « crée », « corrige », « modifie », « mets en place », « lance la phase »), or types /simtis-plan.
---

# SIMTIS — Plan d'abord, code après confirmation

## Principe

Pour chaque tâche d'implémentation, présente d'abord un plan détaillé, puis **arrête-toi**. Tu n'écris rien tant que l'utilisateur n'a pas confirmé explicitement.

Une tâche est une tâche d'implémentation quand elle crée ou modifie un fichier de l'application : code, configuration, migrations, tests, dépendances, Docker, CI. Mettre à jour la documentation (`*.md` du projet, skills) n'en fait pas partie.

**Respecter la lettre de la règle, c'est respecter son esprit.** Une petite tâche suit la même règle, avec le format court.

## Avant la confirmation

| Permis | Interdit |
|---|---|
| Lire et chercher (Read, Grep, Glob) | Créer, modifier, supprimer ou déplacer un fichier de l'application |
| Commandes en lecture seule : `git status`, `git diff`, lancer les tests existants | `npm install`, `pip install`, `create-next-app`, `alembic upgrade`, `docker compose up`, `git commit` |
| Poser une question bloquante | Écrire du code « en brouillon » ou « pour voir » |

## Déroulé

1. **Comprendre.** Relis `CLAUDE.md`. Dans `docs/specs/Plan_Phases_Realisation_SIMTIS.md`, lis la phase concernée (tâches, tables, endpoints, critères de fin) et les sections 3.3 (décisions prises) et 3.4 (points en attente). Inspecte le code existant que la tâche touchera.
2. **Repérer les blocages.** Si la tâche dépend d'un point de la section 3.4, n'invente pas sa définition. Mets-le dans « Questions et risques » avec une proposition. Si la tâche ne peut pas avancer sans réponse, dis-le dès l'objectif.
3. **Choisir le format.** Format court si la tâche touche un seul fichier sans base de données, calcul, permission ni dépendance. Format complet dans tous les autres cas.
4. **Présenter le plan**, terminer par la question de confirmation, puis **terminer le tour**. Si la session est en mode plan, présente-le avec ExitPlanMode.
5. **Lire la réponse.**
   - « ok », « oui », « confirme », « vas-y », « valide » : implémente.
   - Changements demandés : mets le plan à jour et représente-le. Implémente directement seulement si l'utilisateur dit de le faire avec ces changements.
   - Confirmation partielle (« seulement les étapes 1 à 3 ») : fais uniquement ces étapes.
6. **Implémenter** le plan confirmé, étape par étape, dans l'ordre. Si une découverte oblige à changer de fichier, d'approche ou de périmètre, arrête-toi, explique l'écart et redemande confirmation.
7. **Rendre compte.** Pour chaque étape : faite ou non. Pour chaque vérification : la commande lancée et son résultat réel. Puis les écarts par rapport au plan.

Pour une tâche d'interface, charge aussi le skill `simtis-design` avant de rédiger le plan.

## Format complet

```markdown
## Plan — <titre court>

**Phase** : P<n> <nom> · **Taille** : petite / moyenne / grande

### 1. Objectif
<1 à 2 phrases : ce qui fonctionnera à la fin, du point de vue de l'utilisateur.>

### 2. Contexte
- Sources : <documents et sections, ex. CDC §5.2, Plan §3.3>
- Décisions appliquées : <décisions de la section 3.3 qui s'appliquent>
- Hypothèses : <chacune à confirmer, ou « Aucune »>

### 3. Fichiers
| Action | Fichier | Rôle |
|---|---|---|
| Créer | `backend/app/services/position_service.py` | Calcul du crédit et de la position disponibles |

### 4. Étapes
1. <Action> — fichiers : <…> — vérification : <commande ou contrôle>
2. …

### 5. Données et règles
- Tables et colonnes : <nom, type> ou « Aucune »
- Formules et statuts : <…> ou « Aucun »
- Permission requise et entrée `audit_logs` : <…> ou « Aucune »
- Société et devises : <filtrage par `company_id`, pas de somme entre devises> ou « Non concerné »

### 6. Tests et vérification
- Tests à écrire : <unitaires, intégration, cas 401 / 403>
- Commandes : <…>
- Contrôle manuel : <page, URL, exemple chiffré>

### 7. Hors périmètre
- <ce qui ne sera pas fait dans cette tâche>

### 8. Questions et risques
- <question bloquante + proposition> ou « Aucune »

---
**Confirmes-tu ce plan ?** Réponds « ok » pour lancer l'implémentation, ou dis-moi ce qu'il faut changer.
```

Ordre habituel des étapes. Backend : modèle, migration, repository, service, schéma, endpoint, tests. Frontend : types, service API, composants, page.

## Format court

```markdown
## Plan — <titre court>

**Objectif** : <1 phrase>
**Fichier** : `<chemin>` (créer / modifier)
**Étapes** : 1. <…> 2. <…>
**Vérification** : <commande ou contrôle>

**Confirmes-tu ce plan ?** Réponds « ok » pour lancer l'implémentation, ou dis-moi ce qu'il faut changer.
```

## Signaux d'alerte : arrête-toi

| Pensée | Réalité |
|---|---|
| « C'est trop simple pour un plan » | Utilise le format court. Il faut quand même un plan. |
| « L'utilisateur est pressé » | Un plan court se lit en 30 secondes. |
| « Je crée juste le dossier » ou « j'installe juste les dépendances » | C'est une modification. Elle vient après la confirmation. |
| « Il a confirmé le plan précédent » | Une confirmation vaut pour un seul plan. Nouvelle tâche, nouveau plan. |
| « L'écart est petit, inutile de redemander » | Un autre fichier, une autre approche ou un autre périmètre : redemande. |
| « Je présente le plan et je commence en attendant » | Le tour se termine sur la question de confirmation. |
| « Ce terme est sûrement… » | S'il est dans la section 3.4, c'est une question, pas une hypothèse. |
