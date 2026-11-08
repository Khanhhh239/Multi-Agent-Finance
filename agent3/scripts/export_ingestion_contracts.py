import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'agent3_tax_compliance'))
from src.ingestion.models import DocumentArtifact,Geometry,IngestionIssue,IngestionView,PageArtifact,RoutePolicy,TextBlock


def main():
    output=ROOT/'agent3_tax_compliance/contracts/ingestion-v1'; output.mkdir(parents=True,exist_ok=True)
    registry={}
    for name,model in dict(document_artifact=DocumentArtifact,page_artifact=PageArtifact,geometry=Geometry,
        ingestion_issue=IngestionIssue,ingestion_view=IngestionView,route_policy=RoutePolicy,text_block=TextBlock).items():
        schema=model.model_json_schema(mode='serialization'); schema['$schema']='https://json-schema.org/draft/2020-12/schema'
        schema['$id']='urn:financial:ingestion:1.0.0:'+name
        path=output/(name+'.schema.json'); path.write_text(json.dumps(schema,indent=2)+'\n',encoding='utf-8')
        registry[path.name]=hashlib.sha256(path.read_bytes()).hexdigest()
    (output/'registry.json').write_text(json.dumps(dict(schema_version='1.0.0',profile='ingestion-v1',schemas=registry),indent=2)+'\n',encoding='utf-8')
    print(f'Exported {len(registry)} ingestion contracts')


if __name__=='__main__': main()
