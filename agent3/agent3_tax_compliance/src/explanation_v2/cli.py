"""Offline corpus integrity inspection and API configuration check."""
import argparse
import json
from .service import load_config, implementation_sha
from ..legal_registry.registry import load_registry
from ..canonicalization.derive import sha
from ..runtime_config import env


def inspect(policy, corpus, registry):
    errors=[]
    if corpus.registry_version != registry.version:
        errors.append('CORPUS_REGISTRY_VERSION_MISMATCH')
    docs={d.document_id:d for d in registry.documents}
    for chunk in corpus.chunks:
        doc=docs.get(chunk.document_id)
        if not doc or doc.source_status!='PDF_REVIEWED' or chunk.locator not in doc.verified_locators:
            errors.append(chunk.chunk_id+':UNREVIEWED_LOCATOR')
        elif (doc.sha256,doc.effective_from,doc.effective_to)!=(chunk.document_sha256,chunk.effective_from,chunk.effective_to):
            errors.append(chunk.chunk_id+':DOCUMENT_PIN_MISMATCH')
    return dict(config_version=policy.version, corpus_version=corpus.version, chunk_count=len(corpus.chunks),
        validated_through=corpus.validated_through.isoformat() if corpus.validated_through else None,
        required_context_chunks=sum(c.required_context for c in corpus.chunks),
        config_sha256=sha(policy.model_dump(mode='json')),corpus_sha256=sha(corpus.model_dump(mode='json')),
        implementation_sha256=implementation_sha(),valid=not errors,errors=errors,
        corpus_acceptance='PENDING_NO_EXCERPTS' if not corpus.chunks else 'REQUIRES_LABELED_RETRIEVAL_EVALUATION',
        model=policy.model,model_revision=policy.model_revision,llm_enabled=policy.enabled)


def probe(policy):
    key = env('AGENT3_LLM_API_KEY') or env('AGENT3_API_KEY') or env('OPENAI_API_KEY') or env('GROQ_API_KEY')
    return dict(status='API_CONFIGURED' if policy.provider == 'openai' and key else 'API_KEY_MISSING',
                provider=policy.provider, endpoint=policy.endpoint, model=policy.model)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--probe',action='store_true',help='Check API configuration without sending document data')
    args=parser.parse_args()
    policy,corpus=load_config();result=inspect(policy,corpus,load_registry())
    if args.probe:result['runtime']=probe(policy)
    print(json.dumps(result,ensure_ascii=True,indent=2))
    return 0 if result['valid'] else 1


if __name__=='__main__':raise SystemExit(main())
