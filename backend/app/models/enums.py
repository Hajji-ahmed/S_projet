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
ORIGINES_CORRESPONDANCE = ("Automatique", "Manuelle")
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
ORIGINES_OPERATION = ("Fichier", "Corrigée")

# Tableau Devises saisi à la main (page Position bancaire) : ses lignes, et ses colonnes hors banques
LIGNES_DEVISES = ("EUR", "USD", "Exp DH convertible")
COLONNES_DEVISES = ("Banque", "TOTAL", "DEPASSEMENT")

# Tableau Prévisions saisi à la main : nombre de lignes du bloc d'une journée
NB_LIGNES_PREVISIONS = 14
