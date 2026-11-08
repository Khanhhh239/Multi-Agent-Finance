import json,sys,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'agent3_tax_compliance'))
from src.extraction import contracts
from src.canonicalization.derive import sha
from src.persistence.repository import digest

def main():
    destination=ROOT/'agent3_tax_compliance/contracts/extraction-v1';destination.mkdir(parents=True,exist_ok=True)
    registry={}
    for name in ('ExtractionProfile','ExtractionCandidate','IdentityMap','DerivationManifest','VATGroup','Segmentation','ExtractionArtifact'):
        model=getattr(contracts,name)
        filename=re.sub(r'(?<!^)(?=[A-Z][a-z])','_',name).lower()+'.schema.json'
        raw=(json.dumps(model.model_json_schema(mode='serialization'),indent=2)+'\n').encode()
        (destination/filename).write_bytes(raw);registry[filename]=digest(raw)
    (destination/'registry.json').write_text(json.dumps({'version':'extraction-v1','schemas':registry},indent=2)+'\n',encoding='utf-8')
    print('Exported '+str(len(registry))+' extraction contracts')

if __name__=='__main__': main()
