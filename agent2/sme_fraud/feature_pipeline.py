"""Authorized local feature job; exports immutable, checksum-bound separate channels."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import os
import math
import tempfile

from finance_input.json_io import loads
from .auth import AuthError, FileAuthorizer
from .import_files import canonical, digest, fail, ImportFailure
from .rule_snapshot_features import SOURCE_CONTRACT as RULE_SOURCE_CONTRACT, build_from_rule_snapshot
from .snapshot_features import build_from_snapshot
from .snapshots import SnapshotStore

CHANNELS=("features","missing","rows","evidence","contract")


def read_artifact(directory):
    directory=Path(directory)
    try:
        manifest=loads((directory/"manifest.json").read_bytes())
        checksum=manifest.pop("checksum")
        if digest(canonical(manifest))!=checksum:
            raise ValueError("manifest checksum")
        contents={}
        if set(manifest["files"])!={name+".json" for name in CHANNELS}:
            raise ValueError("channel list")
        for name in CHANNELS:
            raw=(directory/(name+".json")).read_bytes()
            if digest(raw)!=manifest["files"][name+".json"]:
                raise ValueError("channel checksum")
            contents[name]=loads(raw)
        if digest(canonical(contents["contract"]))!=manifest["contract_checksum"]:
            raise ValueError("contract checksum")
        if contents["contract"]["fingerprint"]!=manifest["feature_contract_fingerprint"]:
            raise ValueError("contract binding")
        contract=dict(contents["contract"]);fingerprint=contract.pop("fingerprint")
        if digest(canonical(contract))!=fingerprint:
            raise ValueError("contract fingerprint")
        count=manifest["row_count"];columns=contents["contract"]["columns"]
        if any(len(contents[name])!=count for name in ("features","missing","rows","evidence")):
            raise ValueError("row alignment")
        if any(len(row)!=len(columns) for row in contents["features"]+contents["missing"]):
            raise ValueError("column alignment")
        for index,(values,missing,row,evidence) in enumerate(zip(contents["features"],contents["missing"],contents["rows"],contents["evidence"])):
            if row["row_index"]!=index or evidence["row_index"]!=index or any(row[k]!=manifest["snapshot"][k] for k in ("tenant_id","company_id")):
                raise ValueError("scope/alignment")
            for value,flag in zip(values,missing):
                if type(flag) is not bool or flag!=(value is None) or value is not None and (type(value) not in (float,int) or not math.isfinite(value)):
                    raise ValueError("predictor type/missing mask")
        manifest["checksum"]=checksum
        return dict(manifest=manifest,**contents)
    except (OSError,ValueError,KeyError,TypeError,AttributeError,RecursionError,OverflowError):
        fail(500,"FEATURE_ARTIFACT_INTEGRITY","Artifact feature thiếu tệp hoặc checksum/schema không khớp.","Tạo lại job từ snapshot và contract đúng phiên bản; không ghi đè bản lỗi.")


def export_artifact(result, output_base, *, recheck=None, scope=None):
    """Atomic directory publish on the local Windows filesystem; never overwrite."""
    if "snapshot" not in result:
        fail(400,"SNAPSHOT_BINDING_REQUIRED","Feature phải gắn snapshot đã khóa.","Dùng build_from_snapshot hoặc job CLI, không xuất ma trận không có nguồn.")
    def guard():
        if recheck is not None and recheck()!=scope:
            fail(409,"AUTH_CONTEXT_CHANGED","Quyền đã thay đổi trước khi xuất artifact.","Chạy lại job theo quyền hiện hành.")
    guard()
    payload={name+".json":canonical(result[name]) for name in CHANNELS}
    files={name:digest(raw) for name,raw in payload.items()}
    binding=dict(version="feature-artifact/1.0.0",snapshot=result["snapshot"],as_of=result["as_of"],
        feature_contract_fingerprint=result["contract"]["fingerprint"],files=files,
        contract_checksum=files["contract.json"],row_count=len(result["rows"]),columns=result["contract"]["columns"])
    identity="ftr_"+digest(canonical(binding))
    output_base=Path(output_base).resolve();output_base.mkdir(parents=True,exist_ok=True)
    destination=output_base/identity
    if destination.exists():
        prior=read_artifact(destination)["manifest"]
        if any(prior.get(k)!=v for k,v in binding.items()):
            fail(409,"FEATURE_ARTIFACT_CONFLICT","Thư mục artifact đã có nội dung khác.","Đối chiếu kho; không ghi đè.")
        guard()
        return dict(directory=str(destination),manifest=prior)
    manifest=dict(binding,artifact_id=identity,created_at=datetime.now(timezone.utc).isoformat())
    manifest["checksum"]=digest(canonical(manifest))
    temporary=Path(tempfile.mkdtemp(prefix=".feature-",dir=output_base))
    try:
        for name,raw in {**payload,"manifest.json":canonical(manifest)}.items():
            with (temporary/name).open("xb") as stream:
                stream.write(raw);stream.flush();os.fsync(stream.fileno())
        guard()
        try:
            temporary.rename(destination)
        except FileExistsError:
            prior=read_artifact(destination)["manifest"]
            if any(prior.get(k)!=v for k,v in binding.items()):
                fail(409,"FEATURE_ARTIFACT_CONFLICT","Artifact cùng mã có nội dung khác.","Đối chiếu kho, không ghi đè.")
            manifest=prior
        return dict(directory=str(destination),manifest=manifest)
    finally:
        if temporary.exists():
            # Only our flat, explicitly created staging files; no recursive delete.
            assert temporary.resolve().parent==output_base and temporary.name.startswith(".feature-")
            for name in (*payload,"manifest.json"):
                (temporary/name).unlink(missing_ok=True)
            temporary.rmdir()


def run_job(store, authorizer, authorization, company, snapshot_id, as_of, output_base):
    scope=authorizer.authorize(authorization,company)
    recheck=lambda:authorizer.authorize(authorization,company)
    manifest=store.get_snapshot(scope,snapshot_id,recheck)
    if manifest['contract_version']==RULE_SOURCE_CONTRACT:
        result=build_from_rule_snapshot(store,scope,snapshot_id,as_of,recheck,candidates_only=False)
    else:
        result=build_from_snapshot(store,scope,snapshot_id,as_of,recheck)
    if recheck()!=scope:
        fail(409,"AUTH_CONTEXT_CHANGED","Quyền đã thay đổi khi xuất feature.","Chạy lại job theo quyền hiện hành.")
    return export_artifact(result,output_base,recheck=recheck,scope=scope)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ("snapshot-db","auth-file","token-file","company","snapshot-id","as-of","output-dir"):
        parser.add_argument("--"+name,required=True)
    args=parser.parse_args()
    try:
        token=Path(args.token_file).read_text("utf-8").strip()
        authorizer=FileAuthorizer(args.auth_file)
        # Authenticate before opening/initializing any business snapshot DB.
        authorizer.authorize("Bearer "+token,args.company)
        store=SnapshotStore(args.snapshot_db)
        result=run_job(store,authorizer,"Bearer "+token,args.company,args.snapshot_id,args.as_of,args.output_dir)
        print("Feature artifact:",result["directory"])
        print("Rows:",result["manifest"]["row_count"],"· columns:",len(result["manifest"]["columns"]))
        print("Checksum:",result["manifest"]["checksum"])
        return 0
    except (AuthError,ImportFailure) as error:
        print(error.code+": "+error.message+" "+error.action)
        return 1
    except (OSError,ValueError) as error:
        print("FEATURE_JOB_FAILED: Kiểm tra đường dẫn, as_of và kho dữ liệu; chưa có artifact hoàn chỉnh mới.")
        return 1


if __name__=="__main__":raise SystemExit(main())
