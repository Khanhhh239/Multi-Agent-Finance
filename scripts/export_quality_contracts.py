import json,re,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'agent3_tax_compliance'))
from src.quality import contracts
from src.persistence.repository import digest

def main():
    target=ROOT/'agent3_tax_compliance/contracts/quality-v1';target.mkdir(parents=True,exist_ok=True);schemas={}
    for name in ('QualityPolicy','QualityProfile','CalibrationScope','ScoreSample','CalibrationArtifact','SourceCheck',
                 'FieldQuality','QualityIssue','Coverage','ConfidenceSummary','ReviewRecommendation','QualityAssessment'):
        filename=re.sub(r'(?<!^)(?=[A-Z][a-z])','_',name).lower()+'.schema.json'
        raw=(json.dumps(getattr(contracts,name).model_json_schema(mode='serialization'),indent=2)+'\n').encode()
        (target/filename).write_bytes(raw);schemas[filename]=digest(raw)
    (target/'registry.json').write_text(json.dumps({'version':'quality-v1','schemas':schemas},indent=2)+'\n',encoding='utf-8')
    print('Exported '+str(len(schemas))+' quality schemas')

if __name__=='__main__': main()
