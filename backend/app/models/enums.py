"""Valeurs autorisées des colonnes à liste fermée.

Les libellés sont ceux de l'interface (en français, avec accents) : ils sont enregistrés tels quels
et vérifiés par des CHECK en base. Pour en ajouter un, modifier la liste ici puis créer une migration.
"""

# Rapprochement d'une transaction bancaire ou d'une écriture comptable
STATUTS_RAPPROCHEMENT = ("Non rapprochée", "À vérifier", "Rapprochée", "Écart")

# Écarts : À traiter → En cours → Traité → Clôturé (la clôture exige un commentaire)
STATUTS_ECART = ("À traiter", "En cours", "Traité", "Clôturé")
TYPES_ECART = (
    "Banque sans écriture",
    "Écriture sans banque",
    "Montant différent",
    "Date différente",
    "Libellé ambigu",
    "Doublon potentiel",
)

# Prévisions
STATUTS_PREVISION = ("Prévu", "En attente", "Réalisé", "Reporté", "Annulé")

# Contrôle du solde du relevé par rapport au solde enregistré
STATUTS_CONTROLE_SOLDE = ("Conforme", "Écart", "À vérifier")

# Rapprochement : cardinalité et origine de la proposition
TYPES_CORRESPONDANCE = ("1-1", "1-N", "N-1", "N-N")
# « Frais » : écriture de frais bancaires comptabilisée par SIMTIS (13/10/2026)
# « Reprise » : état de rapprochement repris d'Excel, tout le reste rapproché d'un coup (27/10/2026)
ORIGINES_CORRESPONDANCE = ("Automatique", "Manuelle", "Frais", "Reprise")
# Origine d'une écriture comptable : importée de Sage, ou préparée par SIMTIS (13/10/2026)
ORIGINES_ECRITURE = ("Sage", "SIMTIS", "Manuelle")  # Manuelle : saisie à la main (24/10/2026)
STATUTS_CORRESPONDANCE = ("Proposée", "Validée", "Rejetée", "Annulée")

# Imports (relevés bancaires et écritures comptables partagent le même circuit)
TYPES_IMPORT = ("Banque", "Comptabilité")
STATUTS_IMPORT = ("Analysé", "Confirmé", "Annulé", "Échec")

# Comptes bancaires : « DH convertible » correspond à « Exp DH convertible » du classeur
TYPES_COMPTE = ("Courant", "DH convertible")

# Sens d'un flux de trésorerie
SENS = ("Entrée", "Sortie")

# Origine d'un solde journalier
SOURCES_SOLDE = ("Relevé", "Saisie")

# Origine d'une opération bancaire : telle que le fichier, ou corrigée avant l'enregistrement
ORIGINES_OPERATION = ("Fichier", "Corrigée", "Manuelle")  # Manuelle : 24/10/2026

# Tableau Devises saisi à la main (page Position bancaire) : ses lignes, et ses colonnes hors banques
LIGNES_DEVISES = ("EUR", "USD", "Exp DH convertible")
COLONNES_DEVISES = ("Banque", "TOTAL", "DEPASSEMENT")

# Tableau Prévisions saisi à la main : chaque ligne a sa date (30/10/2026), au plus 99 lignes par date
LIGNES_PREVISIONS_PAR_DATE = 99
# Lignes envoyées en une fois (toutes celles à partir de la date de la page)
LIGNES_PREVISIONS_MAX = 1000
