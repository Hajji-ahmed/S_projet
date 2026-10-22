# Sources des documents PDF

Les PDF de `docs/` sont générés à partir des fichiers HTML de ce dossier :

| Source | PDF |
|---|---|
| `cahier-des-charges.html` | `docs/Cahier_des_charges_SIMTIS_V4.pdf` |
| `architecture-fonctionnelle.html` | `docs/Architecture_fonctionnelle_SIMTIS_V2.pdf` |
| `architecture-technique.html` | `docs/Architecture_technique_SIMTIS_V2.pdf` |

Le style commun est dans `simtis-doc.css` (palette du design system). Pour régénérer après une
modification, depuis la racine du dépôt :

```powershell
powershell -ExecutionPolicy Bypass -File docs\sources\generer-pdf.ps1
```

Le script utilise Microsoft Edge en mode sans fenêtre : rien à installer. Les versions d'origine
(V3 du cahier des charges, V1 des architectures) restent dans `docs/specs/`.
