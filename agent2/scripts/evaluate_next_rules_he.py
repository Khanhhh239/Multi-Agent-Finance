"""Empirical evaluation of next HE rule candidate: A6 vs C2.

Evaluates:
1. Rule weights, hard-trigger status, and source table dependencies.
2. Source completeness rate, HE domain-fit rate, hit rate, and incremental catches
   beyond the existing `{P1, C3, B1, B5, E4}` HE group across:
   - Cohort 1: existing repo `agent2-rule-snapshot/1.0.0` examples
   - Cohort 2: `sme_fraud.rule35_ml_eval_demo` (`C001`/`C002`)
   - Cohort 3: multi-company `sme_fraud.generate.Generator` synthetic SME cohorts
     (including partial coverage, missing `invoice_gross_vnd`, and `>4` authority rules)
3. Optional (`--with-wsl-compile`) real Concrete circuit compilation / keygen / eval
   cost measurement in WSL comparing `C2` (combined with existing `c3` authority matrix)
   vs `A6` (modulo-1000 integer arithmetic). Must only run when no heavy FHE job
   is competing for WSL RAM.
"""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
SHARED_SRC = ROOT.parent / 'shared' / 'finance_input' / 'src'
for path in (str(ROOT), str(SHARED_SRC), str(ROOT / 'tests')):
    if path not in sys.path:
        sys.path.insert(0, path)

from finance_input import AccessScope
from sme_fraud.import_files import canonical, digest
from experiments.he4.rule_snapshot_c3_adapter import _metadata_authority_candidates
import experiments.he4.c3_circuit as c3m
from sme_fraud.accounting import enrich_accounting
from sme_fraud.generate import Generator, TZ, stamp
from sme_fraud.native_rule_demo import authorities, base
from sme_fraud.native_rule_node import REQUIRED, TABLES, VERSION as NATIVE_VERSION, _gaps, evaluate_bundle, validate_bundle
from sme_fraud.rule35_ml_eval_demo import build_eval_source
from sme_fraud.rule_snapshot import CONTRACT, MAX_CANDIDATES, source_guards, validate as validate_rule_snapshot
from sme_fraud.rules import DEFAULT_CONFIG, HARD_TRIGGERS, RULE_NAMES, WEIGHTS, ApprovalAuthority, score_rules

HE_COVERED_NOW = ('P1', 'C3', 'B1', 'B5', 'E4')
WSL_PYTHON = '/home/sang/.local/share/agent2/he4/bin/python'
TZ7 = timezone(timedelta(hours=7))


def _make_scope(company_id: str, tenant_id: str = 'demo') -> AccessScope:
    return AccessScope(
        tenant_id=tenant_id,
        company_ids=frozenset({company_id}),
        actor_id='eval-director',
        permissions=frozenset({'data.import'}),
    )


def _wrap_source(tables_by_name: dict, company_id: str, as_of: str, *, candidate_ids: list[str], source_id: str, coverage_overrides: dict | None = None) -> dict:
    norm_tables = {}
    for t in TABLES:
        rows = [deepcopy(r) for r in tables_by_name.get(t, [])]
        for r in rows:
            if t != 'companies' or 'company_id' in r:
                r.setdefault('company_id', company_id)
            if t == 'companies':
                r.setdefault('recorded_at', '2023-01-01T00:00:00+07:00')
            if t == 'transactions':
                r['observed_at'] = r.get('posted_at') or r.get('observed_at') or '2023-01-01T00:00:00+07:00'
                r.pop('recorded_at', None)
            elif 'recorded_at' in r:
                r['observed_at'] = r['recorded_at']
            elif 'observed_at' not in r:
                r['observed_at'] = r.get('posted_at') or r.get('effective_from') or '2023-01-01T00:00:00+07:00'
        norm_tables[t] = rows
    coverage = {}
    for t, rows in norm_tables.items():
        cov = dict(
            status='complete',
            observed_at=as_of,
            covered_from='2023-01-01T00:00:00+07:00',
            covered_through=as_of,
            history_basis='since_inception',
            record_count=len(rows),
            records_sha256=digest(canonical(rows)),
        )
        if coverage_overrides and t in coverage_overrides:
            cov.update(coverage_overrides[t])
        coverage[t] = cov
    source = dict(
        version=NATIVE_VERSION,
        tenant_id='demo',
        company_id=company_id,
        as_of=as_of,
        source_id=source_id,
        is_simulated=True,
        tables=norm_tables,
        coverage=coverage,
    )
    return dict(
        contract_version=CONTRACT,
        tenant_id='demo',
        company_id=company_id,
        source=source,
        candidate_transaction_ids=list(candidate_ids),
    )


def _evaluate_bundle_for_next_rules(label: str, doc: dict, *, candidate_ids_override: list[str] | None = None) -> dict:
    src = deepcopy(doc['source'])
    comp = src['company_id']
    scope = _make_scope(comp, doc.get('tenant_id', src.get('tenant_id', 'demo')))
    checked = validate_bundle(src, scope)
    if checked['status'] != 'accepted':
        return dict(label=label, valid=False, errors=checked['errors'][:5])

    as_of = src['as_of']
    tables = src['tables']
    visible_tables = {
        name: [
            deepcopy(r)
            for r in tables.get(name, [])
            if r.get('observed_at', '') <= as_of and (name != 'transactions' or r.get('posted_at', '') <= as_of)
        ]
        for name in TABLES
    }
    tx_rows = visible_tables['transactions']
    if candidate_ids_override is not None:
        eval_ids = list(candidate_ids_override)
    else:
        eval_ids = list(doc.get('candidate_transaction_ids') or [r['transaction_id'] for r in tx_rows])

    nat_all = evaluate_bundle(src, scope)
    # Apply source_guards over chunks of MAX_CANDIDATES to preserve contract semantics faithfully
    guarded_rules = {r['rule_id']: deepcopy(r) for r in nat_all['rules']}
    for start in range(0, max(1, len(eval_ids)), MAX_CANDIDATES):
        chunk_doc = deepcopy(doc)
        chunk_doc['candidate_transaction_ids'] = eval_ids[start : start + MAX_CANDIDATES] or [r['transaction_id'] for r in tx_rows[:1]]
        guarded_chunk = source_guards(chunk_doc, deepcopy(nat_all))
        for gr in guarded_chunk['rules']:
            rid = gr['rule_id']
            if gr['status'] == 'unavailable':
                guarded_rules[rid] = gr
            elif guarded_rules[rid]['status'] != 'unavailable' and gr['status'] == 'not_applicable':
                guarded_rules[rid] = gr

    # Raw engine score_rules over visible tables gives exact per-tx rule hits even when a sibling tx has missing source
    raw_ref = score_rules(visible_tables, config=deepcopy(DEFAULT_CONFIG))
    raw_hits_by_rule: dict[str, set[str]] = {r: set() for r in (*HE_COVERED_NOW, 'A6', 'C2')}
    for h in raw_ref['hits']:
        if h.get('suppressed_reason'):
            continue
        rid = h.get('rule_id')
        tid = h.get('transaction_id')
        if rid in raw_hits_by_rule and tid:
            raw_hits_by_rule[rid].add(tid)
        for alias in h.get('aliases', []):
            if alias in raw_hits_by_rule and tid:
                raw_hits_by_rule[alias].add(tid)

    tx_by_id = {r['transaction_id']: r for r in tx_rows}
    auth_helper = ApprovalAuthority(visible_tables)

    # Dataset-level table coverage checks (unrelated to per-tx invoice_gross_vnd)
    def _table_cov_ok(rule_code: str, table_subset: tuple[str, ...]) -> bool:
        for tname in table_subset:
            cov = src['coverage'].get(tname)
            if tname not in tables or not cov or cov.get('status') != 'complete':
                return False
        if rule_code == 'C2' and (not visible_tables.get('approval_authorities') or not visible_tables.get('approval_authority_coverage')):
            return False
        return True

    a6_tables_ok = _table_cov_ok('A6', REQUIRED['A6'])
    c2_tables_ok = _table_cov_ok('C2', REQUIRED['C2'])

    counts = Counter()
    a6_hit_ids = set()
    c2_hit_ids = set()
    covered_hit_ids = set()

    for cid in eval_ids:
        counts['total_rows'] += 1
        tx = tx_by_id.get(cid)
        if tx is None:
            continue

        if any(cid in raw_hits_by_rule[rg] for rg in HE_COVERED_NOW):
            covered_hit_ids.add(cid)

        # A6 row evaluation
        is_vendor_pay = tx.get('txn_type') == 'vendor_payment'
        if is_vendor_pay:
            counts['a6_applicable'] += 1
            has_inv = bool(tx.get('invoice_gross_vnd')) and isinstance(tx.get('invoice_number'), str) and bool(tx.get('invoice_number').strip())
            if a6_tables_ok and has_inv:
                counts['a6_source_complete'] += 1
                amt = int(tx.get('amount_vnd') or 0)
                gross = int(tx.get('invoice_gross_vnd') or 0)
                if 0 <= amt < (1 << 63) and 0 < gross < (1 << 63):
                    counts['a6_domain_fit'] += 1
                if cid in raw_hits_by_rule['A6']:
                    a6_hit_ids.add(cid)
            elif a6_tables_ok:
                counts['a6_missing_invoice_fields'] += 1

        # C2 row evaluation
        approver = str(tx.get('approver_id') or '')
        creator = str(tx.get('creator_id') or '')
        at = str(tx.get('approved_at') or '')
        if approver:
            counts['c2_applicable'] += 1
            if c2_tables_ok:
                action = 'self_approve' if creator == approver else 'approve'
                cov = auth_helper.covered(tx, action, at)
                actor_id = creator if creator == approver else approver
                emp = auth_helper.employee_at(comp, actor_id, at)
                role_ok = bool(emp and emp.get('company_id') == comp and str(emp.get('role') or '').strip())
                if cov is not None and not cov.get('_ambiguous') and role_ok:
                    allowed_actions = {'self_approve', 'all'} if creator == approver else {'approve', 'all'}
                    cands = [
                        rec for rec in auth_helper.authorities.records_at(comp, at)
                        if auth_helper._approved(rec, comp, at, actor_id)
                        and rec['action'] in allowed_actions
                        and rec['txn_type'] in {tx['txn_type'], '*'}
                        and (rec['subject_employee_id'] == actor_id if rec['subject_employee_id'] else rec['subject_role'] == emp.get('role'))
                        and (not rec['department'] or rec['department'] == tx.get('department'))
                        and (not rec['project_id'] or rec['project_id'] == tx.get('project_id'))
                        and rec['effective_from'][:10] <= at[:10] <= rec['effective_to'][:10]
                    ]
                    dec = auth_helper.self_approval(tx) if creator == approver else dict(status='ok', mode='authority_matrix')
                    if dec.get('mode') == 'authority_matrix' and dec.get('status') not in ('ambiguous_coverage', 'ambiguous_authority', 'unknown_actor'):
                        counts['c2_source_complete'] += 1
                        if len(cands) <= c3m.MAX_AUTHORITIES:
                            counts['c2_domain_fit'] += 1
                        else:
                            counts['c2_exceeds_max_authorities'] += 1
                        if cid in raw_hits_by_rule['C2']:
                            c2_hit_ids.add(cid)
                else:
                    counts['c2_missing_coverage_or_ambiguous'] += 1

    a6_inc = a6_hit_ids - covered_hit_ids
    c2_inc = c2_hit_ids - covered_hit_ids

    return dict(
        label=label,
        company_id=comp,
        valid=True,
        total_rows=counts['total_rows'],
        covered_he_hits=len(covered_hit_ids),
        A6=dict(
            applicable=counts['a6_applicable'],
            source_complete=counts['a6_source_complete'],
            domain_fit=counts['a6_domain_fit'],
            missing_invoice_fields=counts['a6_missing_invoice_fields'],
            hits=len(a6_hit_ids),
            incremental_beyond_he5=len(a6_inc),
            guarded_dataset_status=guarded_rules['A6']['status'],
        ),
        C2=dict(
            applicable=counts['c2_applicable'],
            source_complete=counts['c2_source_complete'],
            domain_fit=counts['c2_domain_fit'],
            missing_coverage_or_ambiguous=counts['c2_missing_coverage_or_ambiguous'],
            exceeds_max_authorities=counts['c2_exceeds_max_authorities'],
            hits=len(c2_hit_ids),
            incremental_beyond_he5=len(c2_inc),
            guarded_dataset_status=guarded_rules['C2']['status'],
        ),
    )


def _cohort_repo_examples() -> list[dict]:
    out = []
    paths = [
        ROOT / 'examples' / 'rule_bridge_models' / 'C001_5_giao_dich.json',
        ROOT / 'examples' / 'rule_bridge_models' / 'C002_5_giao_dich.json',
        ROOT / 'examples' / 'full_rules' / 'C001_B1_signal.json',
        ROOT / 'examples' / 'full_rules' / 'C001_C2_signal.json',
        ROOT / 'examples' / 'full_rules' / 'C001_coverage_unknown.json',
        ROOT / 'examples' / 'full_rules' / 'C001_E2_signal.json',
        ROOT / 'examples' / 'full_rules' / 'C001_F4_signal.json',
        ROOT / 'examples' / 'full_rules' / 'C002_B1_signal.json',
    ]
    for p in paths:
        doc = json.loads(p.read_text(encoding='utf-8'))
        all_ids = [r['transaction_id'] for r in doc['source']['tables']['transactions']]
        out.append(_evaluate_bundle_for_next_rules(p.name, doc, candidate_ids_override=all_ids))
    return out


def _cohort_rule35_eval_demo() -> list[dict]:
    out = []
    for comp in ('C001', 'C002'):
        ev_doc = build_eval_source(comp, tenant_id='demo')
        out.append(_evaluate_bundle_for_next_rules(f'rule35_eval_{comp}_all_tx', ev_doc, candidate_ids_override=[r['transaction_id'] for r in ev_doc['source']['tables']['transactions']]))
    return out


def _cohort_sme_generator() -> list[dict]:
    gen = Generator(n=420, rate=0.08, seed=20261115, companies=4)
    raw = gen.finalize()
    out = []
    as_of = '2026-01-02T00:00:00+07:00'

    by_comp_tables = {c: {t: [] for t in TABLES} for c in ('C001', 'C002', 'C003', 'C004')}
    for t in TABLES:
        for row in raw.get(t, []):
            cid = row.get('company_id')
            if cid in by_comp_tables:
                by_comp_tables[cid][t].append(deepcopy(row))
            elif t == 'companies' and row.get('company_id') in by_comp_tables:
                by_comp_tables[row['company_id']][t].append(deepcopy(row))

    # Inject deterministic realistic SME operational characteristics per company:
    # C001: Complete sources, small/medium SME (<=4 authorities), mixed A6 & C2 cases
    # C002: Partial approval_authority_coverage (tests C2 source gap) + uninvoiced payments
    # C003: Complex company with 6 overlapping authority rules on big payments (> MAX_AUTHORITIES=4)
    # C004: Clean + self-approval + A6 round-over-fractional invoices
    for comp in ('C001', 'C002', 'C003', 'C004'):
        tmap = by_comp_tables[comp]
        emps = tmap['employees']
        if not tmap['companies'] or not emps or not tmap['transactions']:
            continue
        maker = next((e for e in emps if e.get('role') == 'accountant'), emps[0])
        director = next((e for e in emps if e.get('role') == 'director'), emps[-1])
        vendor = tmap['vendors'][0]
        auth_tmpl = json.loads((ROOT / 'examples' / 'full_rules' / 'C001_C2_signal.json').read_text(encoding='utf-8'))['source']['tables']
        tmpl_cash = deepcopy(next((r for r in tmap['transactions'] if r.get('txn_type') == 'cash_expense'), tmap['transactions'][0]))
        tmpl_vp = deepcopy(next((r for r in tmap['transactions'] if r.get('txn_type') == 'vendor_payment'), tmap['transactions'][0]))

        # Populate complete valid authority matrix & coverage per generated company
        tmap['approval_authorities'] = []
        roles_present = sorted({str(e.get('role') or 'staff') for e in emps})
        for role_name in roles_present:
            is_dir = role_name == 'director'
            rec = deepcopy(auth_tmpl['approval_authorities'][0])
            rec.update(
                authority_id=f'AUTH_{comp}_{role_name}',
                company_id=comp,
                subject_role=role_name,
                subject_employee_id='',
                action='all',
                txn_type='*',
                min_amount_vnd=0,
                max_amount_vnd=500_000_000 if is_dir else 5_000_000,
                self_approval_allowed=1,
                authority_level='high' if is_dir else 'standard',
                approver_id=director['employee_id'],
                effective_from='2023-01-01',
                effective_to='2027-01-01',
                observed_at='2023-01-01T00:00:00+07:00',
                approved_at='2023-01-01T00:00:00+07:00',
            )
            tmap['approval_authorities'].append(rec)

        cov_rec = deepcopy(auth_tmpl['approval_authority_coverage'][0])
        cov_rec.update(
            coverage_id=f'AUTH_COV_{comp}',
            company_id=comp,
            approver_id=director['employee_id'],
            covered_actions='self_approve,approve',
            covered_from='2023-01-01',
            covered_through=as_of[:10],
            observed_at='2023-01-01T00:00:00+07:00',
            approved_at='2023-01-01T00:00:00+07:00',
            status='approved',
        )
        tmap['approval_authority_coverage'] = [cov_rec]

        # Inject 1 legitimate self-approval (within limit), 2 unauthorized self-approvals (C2), & 2 A6 round-over-fractional invoices
        base_dt = datetime(2025, 11, 15, 10, 0, tzinfo=TZ7)
        legit_c2 = deepcopy(tmpl_cash)
        legit_c2.update(
            transaction_id=f'SYN_{comp}_C2_LEGIT',
            company_id=comp,
            txn_type='cash_expense',
            amount_vnd=2_500_000,
            creator_id=maker['employee_id'],
            approver_id=maker['employee_id'],
            employee_id=maker['employee_id'],
            created_at=stamp(base_dt - timedelta(hours=1)),
            approved_at=stamp(base_dt - timedelta(minutes=45)),
            posted_at=stamp(base_dt - timedelta(minutes=40)),
            observed_at=stamp(base_dt - timedelta(minutes=40)),
        )
        tmap['transactions'].append(legit_c2)
        for idx in range(2):
            row_c2 = deepcopy(tmpl_cash)
            row_c2.update(
                transaction_id=f'SYN_{comp}_C2_{idx}',
                company_id=comp,
                txn_type='cash_expense',
                amount_vnd=8_500_000 + idx * 1_000_000,
                creator_id=maker['employee_id'],
                approver_id=maker['employee_id'],
                employee_id=maker['employee_id'],
                created_at=stamp(base_dt + timedelta(hours=idx)),
                approved_at=stamp(base_dt + timedelta(hours=idx, minutes=15)),
                posted_at=stamp(base_dt + timedelta(hours=idx, minutes=20)),
                observed_at=stamp(base_dt + timedelta(hours=idx, minutes=20)),
            )
            tmap['transactions'].append(row_c2)

        for idx in range(2):
            row_a6 = deepcopy(tmpl_vp)
            row_a6.update(
                transaction_id=f'SYN_{comp}_A6_{idx}',
                company_id=comp,
                txn_type='vendor_payment',
                amount_vnd=4_500_000,
                creator_id=maker['employee_id'],
                approver_id=director['employee_id'],
                employee_id=maker['employee_id'],
                vendor_id=vendor['vendor_id'],
                created_at=stamp(base_dt + timedelta(days=1, hours=idx)),
                approved_at=stamp(base_dt + timedelta(days=1, hours=idx, minutes=10)),
                posted_at=stamp(base_dt + timedelta(days=1, hours=idx, minutes=15)),
                observed_at=stamp(base_dt + timedelta(days=1, hours=idx, minutes=15)),
                invoice_number=f'INV_A6_{comp}_{idx}',
                invoice_gross_vnd=4_487_350,
                invoice_issued_at=stamp(base_dt - timedelta(days=2)),
                recipient_account=vendor['bank_account'],
                recipient_bank_code='VCB',
            )
            tmap['transactions'].append(row_a6)

        cov_override = None
        if comp == 'C002':
            cov_override = {'approval_authority_coverage': {'status': 'partial'}}
            vp_seen = 0
            for row in tmap['transactions']:
                if row.get('txn_type') == 'vendor_payment':
                    vp_seen += 1
                    if vp_seen % 5 == 0:
                        row['invoice_gross_vnd'] = 0
        elif comp == 'C003':
            # Add 5 overlapping amount-slab authority tiers for every role (> MAX_AUTHORITIES=4)
            slabs = ((0, 1_000_000), (1_000_001, 2_000_000), (2_000_001, 5_000_000), (5_000_001, 25_000_000), (25_000_001, 500_000_000))
            tmap['approval_authorities'] = []
            for role_name in roles_present:
                is_dir = role_name == 'director'
                for k, (lo, hi) in enumerate(slabs):
                    rec = deepcopy(auth_tmpl['approval_authorities'][0])
                    rec.update(
                        authority_id=f'SLAB_{comp}_{role_name}_{k}',
                        company_id=comp,
                        subject_role=role_name,
                        subject_employee_id='',
                        action='all',
                        txn_type='*',
                        min_amount_vnd=lo,
                        max_amount_vnd=hi,
                        self_approval_allowed=1 if (is_dir or hi <= 5_000_000) else 0,
                        authority_level='high' if (is_dir or k >= 3) else 'standard',
                        approver_id=director['employee_id'],
                        effective_from='2023-01-01',
                        effective_to='2027-01-01',
                        observed_at='2023-01-01T00:00:00+07:00',
                        approved_at='2023-01-01T00:00:00+07:00',
                    )
                    tmap['approval_authorities'].append(rec)

        # Ensure validate_bundle temporal invariants on generated historical rows
        for row in tmap['transactions']:
            if row.get('recipient_account') and not row.get('recipient_bank_code'):
                row['recipient_bank_code'] = 'VCB'
            if row.get('posted_at'):
                row['observed_at'] = row['posted_at']
        doc = _wrap_source(
            tmap,
            comp,
            as_of,
            candidate_ids=[r['transaction_id'] for r in tmap['transactions']],
            source_id=f'gen-{comp.lower()}',
            coverage_overrides=cov_override,
        )
        out.append(_evaluate_bundle_for_next_rules(f'gen_{comp}', doc))
    return out


def _aggregate(rows: list[dict]) -> dict:
    valid = [r for r in rows if r.get('valid')]
    summary = {}
    for rule in ('A6', 'C2'):
        app = sum(r[rule]['applicable'] for r in valid)
        sc = sum(r[rule]['source_complete'] for r in valid)
        df = sum(r[rule]['domain_fit'] for r in valid)
        hits = sum(r[rule]['hits'] for r in valid)
        inc = sum(r[rule]['incremental_beyond_he5'] for r in valid)
        summary[rule] = dict(
            weight=WEIGHTS[rule],
            hard_trigger=(rule in HARD_TRIGGERS),
            required_tables=list(REQUIRED[rule]),
            applicable_rows=app,
            source_complete_rows=sc,
            source_complete_rate=round(sc / app, 4) if app else 0.0,
            domain_fit_rows=df,
            domain_fit_rate_of_complete=round(df / sc, 4) if sc else 0.0,
            domain_fit_rate_of_applicable=round(df / app, 4) if app else 0.0,
            hits=hits,
            incremental_hits_beyond_he5=inc,
        )
    return dict(
        evaluated_bundles=len(valid),
        rejected_bundles=len(rows) - len(valid),
        total_rows=sum(r['total_rows'] for r in valid),
        covered_he5_hits=sum(r['covered_he_hits'] for r in valid),
        rules=summary,
    )


def _wsl_compile_microbenchmark() -> dict:
    """Measure Concrete compile + keygen + eval cost of A6 mod-1000 vs C3+C2 extension in WSL."""
    script = r"""
import json, resource, time
import numpy as np
from concrete import fhe

def rss_mb():
    return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0, 1)

results = {}

# Variant 1: A6 exact modulo-1000 in Concrete on single uint24 (scaled mod 1000? Even uint32 exceeds tiny bitwidth! Measure uint20 scaled / uint32 bit-cost)
try:
    t0 = time.monotonic()
    @fhe.compiler({"amount": "encrypted", "gross": "encrypted"})
    def a6_mod(amount, gross):
        g_pos = gross > 0
        g_mod = (gross % 1000) > 0
        a_mod = (amount % 1000) == 0
        over = amount > (gross + 1)
        return g_pos & g_mod & a_mod & over

    inputset_a6 = [(2_001_000, 1_990_007), (1_000_000, 1_990_007), (500_000, 500_000), (10_000_000, 9_999_001)]
    c_a6 = a6_mod.compile(inputset_a6, p_error=1e-5)
    compile_s = round(time.monotonic() - t0, 3)
    t1 = time.monotonic()
    c_a6.keygen()
    keygen_s = round(time.monotonic() - t1, 3)
    t2 = time.monotonic()
    out = c_a6.encrypt_run_decrypt(2_001_000, 1_990_007)
    eval_s = round(time.monotonic() - t2, 3)
    results['a6_direct_mod1000'] = dict(
        ok=True,
        bit_width=c_a6.graph.maximum_integer_bit_width(),
        compile_s=compile_s,
        keygen_s=keygen_s,
        encrypt_run_decrypt_s=eval_s,
        sample_out=int(out),
        peak_rss_mb=rss_mb(),
    )
except Exception as exc:
    results['a6_direct_mod1000'] = dict(ok=False, error=str(exc), peak_rss_mb=rss_mb())

# Variant 2: C2 combined into existing C3 nibble-word64 authority evaluator (add 2 scalar inputs: self_match, self_ok per slot)
try:
    t0 = time.monotonic()
    @fhe.compiler({"maker_eq_approver": "encrypted", "rule_ok": "encrypted", "rule_self_ok": "encrypted"})
    def c2_ext(maker_eq_approver, rule_ok, rule_self_ok):
        allowed_self = np.sum(rule_ok * rule_self_ok)
        return (maker_eq_approver * (allowed_self == 0)) > 0

    in_c2 = [(np.int64(i % 2), np.array([1, 0, 0, 0], dtype=np.int64), np.array([j % 2, 0, 0, 0], dtype=np.int64)) for i in range(4) for j in range(4)]
    c_c2 = c2_ext.compile(in_c2, p_error=1e-5)
    compile_s = round(time.monotonic() - t0, 3)
    t1 = time.monotonic()
    c_c2.keygen()
    keygen_s = round(time.monotonic() - t1, 3)
    t2 = time.monotonic()
    out = c_c2.encrypt_run_decrypt(1, np.array([1, 0, 0, 0], dtype=np.int64), np.array([0, 0, 0, 0], dtype=np.int64))
    eval_s = round(time.monotonic() - t2, 3)
    results['c2_authority_gate_extension'] = dict(
        ok=True,
        bit_width=c_c2.graph.maximum_integer_bit_width(),
        compile_s=compile_s,
        keygen_s=keygen_s,
        encrypt_run_decrypt_s=eval_s,
        sample_out=int(out),
        peak_rss_mb=rss_mb(),
    )
except Exception as exc:
    results['c2_authority_gate_extension'] = dict(ok=False, error=str(exc), peak_rss_mb=rss_mb())

print(json.dumps(results), flush=True)
"""
    proc = subprocess.run(
        ['wsl.exe', '-d', 'Debian', '--exec', WSL_PYTHON, '-'],
        input=script,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding='utf-8',
        errors='replace',
        timeout=300,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]
    if proc.returncode != 0 or not lines:
        return dict(ok=False, returncode=proc.returncode, stdout=proc.stdout.strip()[-1000:], stderr=proc.stderr.strip()[-1000:])
    return json.loads(lines[-1])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--with-wsl-compile', action='store_true', help='Also run real Concrete compilation benchmark in WSL.')
    parser.add_argument('--output', type=Path, default=None, help='Optional JSON output path.')
    args = parser.parse_args()

    t0 = time.monotonic()
    c1 = _cohort_repo_examples()
    c2 = _cohort_rule35_eval_demo()
    c3 = _cohort_sme_generator()

    report = dict(
        timestamp=datetime.now(TZ7).isoformat(),
        rule_comparison=dict(
            A6=dict(
                name=RULE_NAMES['A6'],
                weight=WEIGHTS['A6'],
                hard_trigger=('A6' in HARD_TRIGGERS),
                required_tables=list(REQUIRED['A6']),
                fhe_complexity='64-bit VND modulo-1000 LUT + strictly-greater comparison + invoice_gross_vnd > 0 + transaction_documents',
                shares_tables_with_existing_he='partial (transactions + employees shared with P1, needs additional transaction_documents)',
            ),
            C2=dict(
                name=RULE_NAMES['C2'],
                weight=WEIGHTS['C2'],
                hard_trigger=('C2' in HARD_TRIGGERS),
                required_tables=list(REQUIRED['C2']),
                fhe_complexity='Reuses exact c3 authority matrix (MAX_AUTHORITIES=4, nibble word64 range checks) + maker==approver & self_approval_allowed bit',
                shares_tables_with_existing_he='100% identical to C3 (transactions, employees, approval_authorities, approval_authority_coverage)',
            ),
        ),
        cohorts=dict(
            repo_examples=dict(summary=_aggregate(c1), details=c1),
            rule35_ml_eval_demo=dict(summary=_aggregate(c2), details=c2),
            sme_generator_stress=dict(summary=_aggregate(c3), details=c3),
            combined_summary=_aggregate(c1 + c2 + c3),
        ),
        wsl_compile_benchmark=_wsl_compile_microbenchmark() if args.with_wsl_compile else dict(skipped=True, reason='Run with --with-wsl-compile after active HE worker benchmark finishes.'),
        elapsed_seconds=round(time.monotonic() - t0, 3),
    )

    txt = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(txt, encoding='utf-8')
        print(f'Wrote {args.output}', flush=True)
    else:
        print(txt, flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
