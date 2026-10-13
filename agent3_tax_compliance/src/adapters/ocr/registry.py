"""Declarative runtime profiles; application/normalizer never import engine code."""
import json
from pathlib import Path
from typing import Any
from pydantic import Field
from ...domain.base import Contract, Identifier
from .protocol import OCRConfig, OCRError

CONFIG_ROOT=Path(__file__).resolve().parents[3]/'configs/ocr'


class EngineProfile(Contract):
    profile_version: Identifier
    model_id: Identifier
    adapter: Identifier
    interpreter: str
    distributions: tuple[str,...]
    source_files: tuple[str,...]
    assets: tuple[str,...]
    environment: dict[str,str] = {}
    adapter_config: dict[str,Any]
    path_parameters: tuple[str,...] = ()
    max_processes: int = Field(default=2,ge=2,le=8)


def confined(root,path):
    target=(root/path).resolve()
    if not target.is_relative_to(root.resolve()):
        raise OCRError('MODEL_UNAVAILABLE','Engine profile path escapes benchmark root')
    return target


class EngineRegistry:
    def __init__(self,directory=None):
        self.directory=Path(directory or CONFIG_ROOT/'engines')

    def get(self,model_id):
        try:
            path=confined(self.directory,model_id+'.json')
            profile=EngineProfile.model_validate_json(path.read_text(encoding='utf-8'))
            if profile.model_id!=model_id: raise ValueError('profile identity mismatch')
            return profile
        except (OSError,ValueError):
            raise OCRError('MODEL_UNAVAILABLE','OCR engine profile is missing or invalid') from None


def adapter_config(profile,root,config):
    # Deep copy; profile is immutable between requests. Runtime/model paths and
    # environment come only from trusted engine profiles, never request options.
    output=json.loads(json.dumps(profile.adapter_config))
    for dotted in profile.path_parameters:
        parts=dotted.split('.');current=output
        for part in parts[:-1]: current=current[part]
        current[parts[-1]]=str(confined(root,current[parts[-1]]))
    output.update(model_id=config.model_id,adapter=profile.adapter,output_mode='boxes_and_text')
    if profile.adapter=='tesseract': output.update(language=config.language,psm=config.psm)
    allowed=output.get('application_parameters',[])
    if set(config.parameters)-set(allowed):
        raise OCRError('BAD_INPUT','Unregistered OCR tuning parameter')
    output.pop('application_parameters',None)
    output.update(config.parameters)
    return output


def load_default_config():
    pointer=json.loads((CONFIG_ROOT/'default.json').read_text(encoding='utf-8'))
    path=confined(CONFIG_ROOT,pointer['config'])
    return OCRConfig.model_validate_json(path.read_text(encoding='utf-8'))
