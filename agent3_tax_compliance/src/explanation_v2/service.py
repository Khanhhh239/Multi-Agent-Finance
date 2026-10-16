"""Revision-bound optional RAG. V1 evaluation artifacts are never modified."""
import hashlib
import json
import os
import sqlite3
import time
from pathlib import Path
from uuid import uuid4
from .contracts import Policy, Corpus, ExplanationArtifact
from .context_builder import build_context
from .retrieval import retrieve
from .validator import validate, fallback
from .llm import provider_for, ProviderFailure, PROMPT_VERSION
from ..canonicalization.derive import sha
from ..domain.cfr import CanonicalFinancialRecord
from ..legal_registry.registry import LegalRegistry
from ..review.contracts import ReviewError
from ..orchestration.workflow import Workflow

CONFIG = Path(__file__).resolve().parents[2] / 'configs/explanation'


def load_config():
    policy = Policy.model_validate_json(Path(os.environ.get('AGENT3_EXPLANATION_POLICY', CONFIG/'policy_v1.json')).read_text(encoding='utf-8'))
    corpus = Corpus.model_validate_json(Path(os.environ.get('AGENT3_EXPLANATION_CORPUS', CONFIG/'corpus_20261016_v1.json')).read_text(encoding='utf-8'))
    return policy, corpus


def implementation_sha():
    return sha({p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted(Path(__file__).parent.glob('*.py'))})


def explain(artifact, inputs, policy, corpus, provider=None):
    started = time.perf_counter()
    report = artifact.report
    registry = LegalRegistry.model_validate(inputs['legal'])
    record = CanonicalFinancialRecord.model_validate(inputs['record'])
    citations = tuple(c for row in artifact.rule_results for c in row.citations)
    field = record.invoice.issue_date if record.invoice else None
    reason = None
    excerpts = ()
    if field is None or field.status != 'PRESENT' or field.value is None:
        reason = 'MISSING_LEGAL_DATE'
    elif corpus.registry_version != registry.version:
        reason = 'CORPUS_VERSION_MISMATCH'
    elif not citations:
        reason = 'NO_SELECTED_LEGAL_BASIS'
    elif any(not c.locator_reviewed for c in citations):
        reason = 'LEGAL_BASIS_NOT_REVIEWED'
    else:
        query = ' '.join(row.explanation+' '+row.rule_id for row in artifact.rule_results)
        # Top-k applies per selected locator, so a different rule cannot lose its basis.
        unique = {(c.document_id, c.locator, c.sha256): c for c in citations}
        selected = {}
        for cite in unique.values():
            found = retrieve(corpus, registry, (cite,), query, field.value, policy.top_k)
            if not found:
                reason = 'LEGAL_EXCERPT_UNAVAILABLE'
                selected = {}
                break
            selected.update((c.chunk_id, c) for c in found)
        excerpts = tuple(selected[k] for k in sorted(selected))
    context = build_context(artifact, excerpts)
    claims = fallback(context)
    mode = 'TEMPLATE'
    if not policy.enabled:
        reason = reason or 'LLM_DISABLED'
    elif len(context.facts) > policy.max_facts or len(context.model_dump_json().encode()) > policy.max_context_bytes:
        reason = 'CONTEXT_BUDGET'
    elif policy.model_revision == 'UNVERIFIED':
        reason = reason or 'MODEL_REVISION_UNPINNED'
    elif reason is None:
        try:
            claims = validate((provider or provider_for(policy)).generate(context, policy), context)
            mode = 'LLM_VALIDATED'
        except ProviderFailure as exc:
            reason = str(exc)
        except (ValueError, TypeError) as exc:
            reason = 'CLAIM_VALIDATION_FAILED'
        except Exception:
            # Optional provider crashes must not take the deterministic report down.
            reason = 'PROVIDER_FAILURE'
    return ExplanationArtifact(config_version=policy.version, creator='explanation-sidecar', stage='explanation',
        explanation_id='explanation-'+uuid4().hex, tenant_id=report.tenant_id, taxpayer_id=report.taxpayer_id,
        evaluation_id=report.evaluation_id, record_revision=report.record_revision,
        evaluation_sha256=sha(artifact.model_dump(mode='json')), context_sha256=sha(context.model_dump(mode='json')),
        config_sha256=sha(policy.model_dump(mode='json')), corpus_sha256=sha(corpus.model_dump(mode='json')),
        implementation_sha256=implementation_sha(), prompt_version=PROMPT_VERSION,
        provider=policy.provider, model=policy.model, model_revision=policy.model_revision,
        mode=mode, fallback_reason=reason, claims=claims, excerpts=excerpts,
        elapsed_seconds=time.perf_counter()-started)


class ExplanationService:
    def __init__(self, settings):
        self.workflow = Workflow(settings)
        # Independent sidecar DB preserves existing foundation migrations and replay hashes.
        self.path = settings.database_path.with_suffix('.explanations.sqlite3')

    def db(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            db.execute('CREATE TABLE IF NOT EXISTS explanations ('
                       'tenant TEXT NOT NULL,payer TEXT NOT NULL,evaluation TEXT NOT NULL,'
                       'request_key TEXT NOT NULL,binding TEXT NOT NULL,payload TEXT NOT NULL,'
                       'sha256 TEXT NOT NULL,PRIMARY KEY(tenant,payer,request_key))')
            db.commit()
        except BaseException:
            db.close()
            raise
        return db

    def latest(self, ctx, payer, evaluation):
        original = self.workflow.artifact(ctx, payer, evaluation)
        db = self.db()
        try:
            row = db.execute('SELECT * FROM explanations WHERE tenant=? AND payer=? AND evaluation=? ORDER BY rowid DESC LIMIT 1',
                             (ctx.tenant_id, payer, evaluation)).fetchone()
            return self._read(row, original) if row else None
        finally:
            db.close()

    @staticmethod
    def _read(row, original):
        if hashlib.sha256(row['payload'].encode()).hexdigest() != row['sha256']:
            raise ValueError('Explanation integrity failure')
        item = ExplanationArtifact.model_validate_json(row['payload'])
        report = original.report
        if ((item.tenant_id, item.taxpayer_id, item.evaluation_id, item.record_revision) !=
            (report.tenant_id, report.taxpayer_id, report.evaluation_id, report.record_revision) or
            item.evaluation_sha256 != sha(original.model_dump(mode='json'))):
            raise ValueError('Explanation scope or snapshot mismatch')
        return item

    def create(self, ctx, payer, evaluation, revision, request_key, *, policy=None, corpus=None, provider=None):
        ctx.require(ctx.tenant_id, payer, 'WRITE')
        original = self.workflow.artifact(ctx, payer, evaluation)
        if original.report.record_revision != revision:
            raise ReviewError('REVISION_CONFLICT', 'Explanation belongs to a different revision.', 409)
        if policy is None or corpus is None:
            policy, corpus = load_config()
        binding = sha([evaluation, revision, policy.model_dump(mode='json'), corpus.model_dump(mode='json'), implementation_sha()])
        db = self.db()
        try:
            row = db.execute('SELECT * FROM explanations WHERE tenant=? AND payer=? AND request_key=?',
                             (ctx.tenant_id, payer, request_key)).fetchone()
            if row:
                if row['binding'] != binding:
                    raise ReviewError('IDEMPOTENCY_CONFLICT', 'Explanation request key was used with another snapshot/config.', 409)
                return self._read(row, original)
            inputs = self.workflow.planning.snapshot(ctx, payer, original.report.planning_evaluation_id)
            result = explain(original, inputs, policy, corpus, provider)
            payload = result.model_dump_json()
            with db:
                # Concurrent equal requests can share the first committed artifact.
                db.execute('INSERT OR IGNORE INTO explanations VALUES(?,?,?,?,?,?,?)',
                           (ctx.tenant_id, payer, evaluation, request_key, binding, payload, hashlib.sha256(payload.encode()).hexdigest()))
                row = db.execute('SELECT * FROM explanations WHERE tenant=? AND payer=? AND request_key=?',
                                 (ctx.tenant_id, payer, request_key)).fetchone()
                if row['binding'] != binding:
                    raise ReviewError('IDEMPOTENCY_CONFLICT', 'Concurrent explanation key belongs to another snapshot.', 409)
                return self._read(row, original)
        finally:
            db.close()
