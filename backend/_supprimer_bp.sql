-- Suppression du releve et des ecritures comptables du compte BP (Simtis), en une transaction.
-- Le journal d'audit n'est jamais touche (il est en ajout seul).
\set ON_ERROR_STOP on
BEGIN;

CREATE TEMP TABLE c AS
SELECT a.id FROM bank_accounts a
JOIN banks b ON b.id = a.bank_id
JOIN companies co ON co.id = a.company_id
WHERE b.code = 'BP' AND co.code = 'SIMTIS';

CREATE TEMP TABLE tx AS SELECT id FROM bank_transactions WHERE bank_account_id IN (SELECT id FROM c);
CREATE TEMP TABLE ec AS SELECT id FROM accounting_entries WHERE bank_account_id IN (SELECT id FROM c);
CREATE TEMP TABLE lots AS
SELECT import_batch_id AS id FROM bank_statements WHERE bank_account_id IN (SELECT id FROM c)
UNION SELECT import_batch_id FROM accounting_entries WHERE id IN (SELECT id FROM ec);

-- Rapprochements (et leurs elements) qui touchent une operation ou une ecriture BP
DELETE FROM reconciliation_matches WHERE id IN (
  SELECT match_id FROM reconciliation_match_items
  WHERE bank_transaction_id IN (SELECT id FROM tx) OR accounting_entry_id IN (SELECT id FROM ec));
DELETE FROM discrepancies
WHERE bank_transaction_id IN (SELECT id FROM tx) OR accounting_entry_id IN (SELECT id FROM ec);
UPDATE cash_forecasts SET bank_transaction_id = NULL WHERE bank_transaction_id IN (SELECT id FROM tx);

DELETE FROM balance_checks WHERE bank_account_id IN (SELECT id FROM c);
DELETE FROM bank_transactions WHERE id IN (SELECT id FROM tx);
DELETE FROM bank_statements WHERE bank_account_id IN (SELECT id FROM c);
DELETE FROM accounting_entries WHERE id IN (SELECT id FROM ec);
-- Solde du jour cree par l'import du releve (les soldes saisis a la main restent)
DELETE FROM bank_account_balances
WHERE bank_account_id IN (SELECT id FROM c) AND source = U&'Relev\00E9';
DELETE FROM reconciliation_code_counters WHERE bank_account_id IN (SELECT id FROM c);
-- Lots d'import qui ne servent plus a rien (un export Sage peut aussi contenir d'autres banques)
DELETE FROM import_batches i WHERE i.id IN (SELECT id FROM lots)
  AND NOT EXISTS (SELECT 1 FROM bank_statements s WHERE s.import_batch_id = i.id)
  AND NOT EXISTS (SELECT 1 FROM accounting_entries e WHERE e.import_batch_id = i.id);

SELECT
  (SELECT count(*) FROM bank_transactions WHERE bank_account_id IN (SELECT id FROM c)) AS operations_bp,
  (SELECT count(*) FROM accounting_entries WHERE bank_account_id IN (SELECT id FROM c)) AS ecritures_bp;
COMMIT;
