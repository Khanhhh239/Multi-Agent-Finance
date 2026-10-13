"""Export review contracts and OpenAPI without database or model initialization."""
import json,re,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'agent3_tax_compliance'))
from src.review import contracts
from src.review.api import EvidenceToken,Recovery
from src.app import create_app
from src.persistence.repository import digest

def main():
    target=ROOT/'agent3_tax_compliance/contracts/review-v1';target.mkdir(parents=True,exist_ok=True);schemas={}
    models=[getattr(contracts,name) for name in ('Change','FieldCorrection','CorrectionCommand','CorrectionEvent','CorrectionResult','ReviewTask','TaskPage','TaskAction')]+[EvidenceToken,Recovery]
    for model in models:
        name=re.sub(r'(?<!^)(?=[A-Z][a-z])','_',model.__name__).lower()+'.schema.json'
        raw=(json.dumps(model.model_json_schema(mode='serialization'),indent=2)+'\n').encode()
        (target/name).write_bytes(raw);schemas[name]=digest(raw)
    (target/'registry.json').write_text(json.dumps({'version':'review-v1','schemas':schemas},indent=2)+'\n',encoding='utf-8')
    public=ROOT/'docs/agent3/plans/evidence/plan06';public.mkdir(parents=True,exist_ok=True)
    (public/'openapi.json').write_text(json.dumps(create_app().openapi(),indent=2)+'\n',encoding='utf-8')
    print('Exported '+str(len(models))+' review schemas and OpenAPI')
if __name__=='__main__':main()
