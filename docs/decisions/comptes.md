# Comptes bancaires : affichage, désactivation, suppression

> Texte déplacé tel quel depuis `CLAUDE.md` le 04/11/2026, dans l'ordre d'origine (en anglais, comme ce fichier).
> Un paragraphe plus récent peut en remplacer un plus ancien : chercher « replaces » / « since ».

`/banques` cards show only the Solde (the bank detail page keeps crédit and position disponibles).

**Accounts**: deactivated accounts are no longer shown (the Comptes screen lists `actif=true` only, no status filter); an account **without history** (no statement, transaction, entry, import or balance check; `AccountOut.a_historique`) is deleted with its hand-entered balances (`DELETE /api/accounts/{id}`, `banks.manage`, audit `suppression_compte`, 409 otherwise); one with history can only be deactivated.

**Since 29/10/2026** the Comptes screen has « Afficher les comptes désactivés » (`actif` left out of the query): such an account is greyed with a « Désactivé » badge and a « Réactiver » button (existing `PATCH /api/accounts/{id}/status`, confirmation); a deactivated account keeps its number, and creating another account with it gives 409 naming the deactivated account and how to reactivate it (`account_service._check_numero_free`). Migration 0016 (data only) deleted the deactivated accounts without history (2 in the dev database), audited. (6)
