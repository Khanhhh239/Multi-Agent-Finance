"""Offline corpus integrity inspection; local model probe never sends invoices."""
import argparse
import http.client
import json
from urllib.parse import urlparse
from .service import load_config, implementation_sha
from ..legal_registry.registry import load_registry
from ..canonicalization.derive import sha


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
        config_sha256=sha(policy.model_dump(mode='json')),corpus_sha256=sha(corpus.model_dump(mode='json')),
        implementation_sha256=implementation_sha(),valid=not errors,errors=errors,
        corpus_acceptance='PENDING_NO_EXCERPTS' if not corpus.chunks else 'REQUIRES_LABELED_RETRIEVAL_EVALUATION',
        model=policy.model,model_revision=policy.model_revision,llm_enabled=policy.enabled)


def probe(policy):
    url=urlparse(policy.endpoint)
    if url.scheme!='http' or url.hostname not in ('127.0.0.1','::1') or url.username or url.password:
        return dict(status='LOCAL_ENDPOINT_REQUIRED')
    connection=http.client.HTTPConnection(url.hostname,url.port or 80,timeout=2)
    try:
        connection.request('GET','/api/tags')
        response=connection.getresponse();raw=response.read(64001)
        if response.status!=200 or len(raw)>64000:return dict(status='MODEL_MANIFEST_UNAVAILABLE')
        models=json.loads(raw).get('models',[])
        model=next((m for m in models if m.get('name')==policy.model),None)
        if not model:return dict(status='MODEL_NOT_INSTALLED')
        return dict(status='MODEL_INSTALLED',model=policy.model,digest=model.get('digest'),
                    pin_matches=model.get('digest')==policy.model_revision)
    except (OSError,ValueError,TypeError):return dict(status='PROVIDER_UNAVAILABLE')
    finally:connection.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--probe',action='store_true',help='Inspect loopback Ollama manifest, no document sent')
    args=parser.parse_args()
    policy,corpus=load_config();result=inspect(policy,corpus,load_registry())
    if args.probe:result['runtime']=probe(policy)
    print(json.dumps(result,ensure_ascii=True,indent=2))
    return 0 if result['valid'] else 1


if __name__=='__main__':raise SystemExit(main())
