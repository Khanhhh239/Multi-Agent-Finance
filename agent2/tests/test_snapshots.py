"""R1-03/04 and scoped immutable storage; all data and DBs are synthetic."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import copy
from datetime import datetime, timedelta, timezone
from email.message import Message
import http.client
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from finance_input import AccessScope
from sme_fraud.auth import FileAuthorizer
from sme_fraud.import_files import canonical, digest, ImportFailure
from sme_fraud.review_server import make_server
from sme_fraud.snapshot_api import handle_snapshots
from sme_fraud.snapshots import SnapshotStore
from test_validation_backend import bundle_for, policy_for


def commit_fields(report):
    value={k:report[k] for k in ("preview_id","source_hash","mapping_hash","report_hash","context_hash")}
    return dict(value,expected_revision=report["revision"],acknowledge=True)


@contextmanager
def connection(path):
    conn=sqlite3.connect(path)
    try:
        with conn:
            yield conn
    finally:
        conn.close()


class SnapshotStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/"snapshots.sqlite3"
        self.now=datetime(2026,11,10,10,tzinfo=timezone.utc)
        self.store=SnapshotStore(self.path,clock=lambda:self.now,preview_ttl=60)
        self.scope=AccessScope("demo",frozenset({"C001"}),"synthetic-reviewer",frozenset({"data.import"}))
        self.raw=canonical(bundle_for())

    def count(self,table):
        with connection(self.path) as conn:return conn.execute("SELECT count(*) FROM "+table).fetchone()[0]

    def ready(self,raw=None,key="upload-ready"):
        draft=self.store.upload(self.scope,raw if raw is not None else self.raw,"fixture.json",key)
        report=self.store.preview(self.scope,draft["import_id"],draft["revision"])
        return draft,report,commit_fields(report)

    def test_roundtrip_keeps_exact_signed_data_and_versioned_checksums(self):
        draft,report,request=self.ready()
        saved=self.store.commit(self.scope,draft["import_id"],request,"commit-roundtrip")
        snapshot=saved["snapshot"]
        raw=self.store.get_snapshot(self.scope,snapshot["snapshot_id"],data=True)
        self.assertEqual(raw,self.raw);self.assertEqual(digest(raw),snapshot["data_checksum"])
        self.assertEqual(json.loads(raw)["transactions"][2]["amount_vnd"],-2000000)
        self.assertEqual(snapshot["contract_version"],"1.0.0")
        self.assertEqual(len(snapshot["checksum"]),64)
        self.assertEqual(snapshot,self.store.get_snapshot(self.scope,snapshot["snapshot_id"]))

    def test_R1_04_ten_identical_commit_retries_create_one_snapshot_and_event(self):
        draft,_,request=self.ready()
        results=[self.store.commit(self.scope,draft["import_id"],request,"ten-retries-key") for _ in range(10)]
        self.assertTrue(all(r==results[0] for r in results))
        self.assertEqual(self.count("snapshots"),1)
        with connection(self.path) as conn:
            self.assertEqual(conn.execute("SELECT count(*) FROM import_audit WHERE action='committed'").fetchone()[0],1)

    def test_concurrent_ten_commit_retries_are_atomic(self):
        draft,_,request=self.ready()
        with ThreadPoolExecutor(max_workers=10) as workers:
            results=list(workers.map(lambda _:self.store.commit(self.scope,draft["import_id"],request,"concurrent-commit"),range(10)))
        self.assertEqual(len({r["snapshot"]["snapshot_id"] for r in results}),1)
        self.assertEqual(self.count("snapshots"),1)

    def test_different_retry_keys_same_confirmed_import_do_not_duplicate(self):
        draft,_,request=self.ready()
        first=self.store.commit(self.scope,draft["import_id"],request,"first-commit-key")
        again=self.store.commit(self.scope,draft["import_id"],request,"second-commit-key")
        self.assertEqual(first,again);self.assertEqual(self.count("snapshots"),1)

    def test_restarted_process_recovers_same_receipt_after_response_loss(self):
        draft,_,request=self.ready()
        first=self.store.commit(self.scope,draft["import_id"],request,"lost-response-key")
        restarted=SnapshotStore(self.path,clock=lambda:self.now+timedelta(days=1))
        self.assertEqual(first,restarted.commit(self.scope,draft["import_id"],request,"lost-response-key"))

    def test_identical_upload_retry_returns_same_draft(self):
        rows=[self.store.upload(self.scope,self.raw,"fixture.json","upload-repeat-key") for _ in range(10)]
        self.assertTrue(all(r==rows[0] for r in rows));self.assertEqual(self.count("imports"),1)
        self.assertEqual(self.count("source_blobs"),1)

    def test_same_data_in_a_new_import_reuses_immutable_snapshot(self):
        first,_,request=self.ready(key="upload-first-key")
        saved=self.store.commit(self.scope,first["import_id"],request,"commit-first-key")
        second,_,request=self.ready(key="upload-second-key")
        again=self.store.commit(self.scope,second["import_id"],request,"commit-second-key")
        self.assertNotEqual(first["import_id"],second["import_id"])
        self.assertEqual(saved["snapshot"],again["snapshot"]);self.assertEqual(self.count("snapshots"),1)

    def test_idempotency_key_reused_with_different_content_is_conflict(self):
        self.store.upload(self.scope,self.raw,"fixture.json","conflicting-key")
        changed=bundle_for();changed["transactions"][0]["description"]="different"
        with self.assertRaises(ImportFailure) as error:
            self.store.upload(self.scope,canonical(changed),"fixture.json","conflicting-key")
        self.assertEqual(error.exception.code,"IDEMPOTENCY_CONFLICT")
        self.assertEqual(self.count("imports"),1)

    def test_R1_03_new_source_invalidates_old_preview(self):
        draft,_,request=self.ready()
        changed=bundle_for();changed["transactions"][0]["description"]="revised source"
        info=self.store.revise(self.scope,draft["import_id"],1,"replace-source-key",raw=canonical(changed),filename="new.json")
        self.assertEqual(info["revision"],2);self.assertIsNone(info["active_preview_id"])
        with self.assertRaises(ImportFailure) as error:self.store.commit(self.scope,draft["import_id"],request,"stale-source-key")
        self.assertEqual(error.exception.code,"STALE_REVISION");self.assertEqual(self.count("snapshots"),0)
        report=self.store.preview(self.scope,draft["import_id"],2)
        saved=self.store.commit(self.scope,draft["import_id"],commit_fields(report),"fresh-source-key")
        self.assertIn(b"revised source",self.store.get_snapshot(self.scope,saved["snapshot"]["snapshot_id"],data=True))

    def test_R1_03_new_mapping_invalidates_old_preview(self):
        draft,_,request=self.ready()
        mapping={"tables":{"transactions":{"description":"adjustment_reason"}}}
        info=self.store.revise(self.scope,draft["import_id"],1,"change-mapping-key",mapping=mapping)
        self.assertEqual(info["revision"],2)
        with self.assertRaises(ImportFailure):self.store.commit(self.scope,draft["import_id"],request,"stale-mapping-key")
        report=self.store.preview(self.scope,draft["import_id"],2)
        self.assertEqual(report["status"],"rejected")
        with self.assertRaises(ImportFailure):self.store.commit(self.scope,draft["import_id"],commit_fields(report),"bad-mapping-key")
        self.assertEqual(self.count("snapshots"),0)

    def test_actual_column_mapping_applies_before_validation(self):
        data=bundle_for()
        for row in data["transactions"]:row["Số tiền"]=row.pop("amount_vnd")
        draft=self.store.upload(self.scope,canonical(data),"mapping.json","upload-mapping-key")
        report=self.store.preview(self.scope,draft["import_id"],1)
        self.assertEqual(report["status"],"rejected")
        mapping={"tables":{"transactions":{"Số tiền":"amount_vnd"}}}
        self.store.revise(self.scope,draft["import_id"],1,"mapping-fix-key",mapping=mapping)
        report=self.store.preview(self.scope,draft["import_id"],2)
        saved=self.store.commit(self.scope,draft["import_id"],commit_fields(report),"mapping-commit-key")
        self.assertEqual(self.store.get_snapshot(self.scope,saved["snapshot"]["snapshot_id"],data=True),self.raw)

    def test_mapping_collision_never_silently_overwrites_a_column(self):
        data=bundle_for();data["transactions"][0]["Số tiền"]=999
        draft=self.store.upload(self.scope,canonical(data),"collision.json","upload-collision-key")
        self.store.revise(self.scope,draft["import_id"],1,"mapping-collision-key",mapping={"tables":{"transactions":{"Số tiền":"amount_vnd"}}})
        report=self.store.preview(self.scope,draft["import_id"],2)
        self.assertEqual(report["errors"][0]["code"],"MAPPING_COLLISION")
        self.assertEqual(report["errors"][0]["row"],1)
        self.assertEqual(self.count("snapshots"),0)

    def test_mapping_does_not_allow_code_or_two_columns_to_one_target(self):
        draft,_,_=self.ready()
        for mapping in [{"code":"eval"},{"tables":{"transactions":{"x":"amount_vnd","y":"amount_vnd"}}},{"tables":{"transactions":{"x":"nonexistent"}}}]:
            with self.subTest(mapping=mapping),self.assertRaises(ImportFailure):
                self.store.revise(self.scope,draft["import_id"],1,"mapping-invalid-key",mapping=mapping)

    def test_preview_is_cached_until_expiry_then_rechecked(self):
        draft,report,_=self.ready()
        self.assertEqual(report,self.store.preview(self.scope,draft["import_id"],1))
        self.now+=timedelta(seconds=61)
        fresh=self.store.preview(self.scope,draft["import_id"],1)
        self.assertNotEqual(report["preview_id"],fresh["preview_id"])
        self.assertEqual(self.count("previews"),2)

    def test_expired_preview_cannot_commit(self):
        draft,_,request=self.ready();self.now+=timedelta(seconds=61)
        with self.assertRaises(ImportFailure) as error:self.store.commit(self.scope,draft["import_id"],request,"expired-preview-key")
        self.assertEqual(error.exception.code,"PREVIEW_EXPIRED");self.assertEqual(self.count("snapshots"),0)

    def test_each_hash_is_checked_not_trusted_from_client(self):
        draft,_,request=self.ready()
        for field in ("source_hash","mapping_hash","report_hash","context_hash"):
            changed=dict(request);changed[field]="0"*64
            with self.subTest(field=field),self.assertRaises(ImportFailure) as error:
                self.store.commit(self.scope,draft["import_id"],changed,"wrong-hash-key")
            self.assertEqual(error.exception.code,"STALE_PREVIEW")
        self.assertEqual(self.count("snapshots"),0)

    def test_explicit_confirmation_required(self):
        draft,_,request=self.ready()
        for value in (False,1,"true",None):
            with self.subTest(value=value),self.assertRaises(ImportFailure):
                self.store.commit(self.scope,draft["import_id"],dict(request,acknowledge=value),"confirm-needed-key")
        self.assertEqual(self.count("snapshots"),0)

    def test_validator_or_permission_context_change_forces_new_preview(self):
        draft,_,request=self.ready()
        with patch("sme_fraud.imports.VALIDATOR_VERSION","new-version"):
            with self.assertRaises(ImportFailure) as error:self.store.commit(self.scope,draft["import_id"],request,"changed-validator-key")
            self.assertEqual(error.exception.code,"STALE_PREVIEW")
        new_scope=AccessScope(self.scope.tenant_id,self.scope.company_ids,self.scope.actor_id,frozenset({"data.import","evidence.verify"}))
        with self.assertRaises(ImportFailure):self.store.commit(new_scope,draft["import_id"],request,"changed-permission-key")

    def test_snapshot_and_committed_import_cannot_be_modified(self):
        draft,_,request=self.ready();saved=self.store.commit(self.scope,draft["import_id"],request,"immutability-key")
        for table in ("snapshots","source_blobs","import_revisions","previews","request_receipts","import_audit"):
            for operation in ("UPDATE","DELETE"):
                with self.subTest(table=table,operation=operation),connection(self.path) as conn,self.assertRaises(sqlite3.IntegrityError):
                    conn.execute(f"UPDATE {table} SET rowid=rowid" if operation=="UPDATE" else f"DELETE FROM {table}")
        with self.assertRaises(ImportFailure):self.store.revise(self.scope,draft["import_id"],1,"edit-committed-key",mapping={})
        self.assertEqual(saved["snapshot"],self.store.get_snapshot(self.scope,saved["snapshot"]["snapshot_id"]))

    def test_atomic_failure_rolls_back_snapshot_audit_receipt_and_status(self):
        draft,_,request=self.ready()
        with connection(self.path) as conn:
            conn.execute("CREATE TRIGGER inject_failure BEFORE INSERT ON request_receipts WHEN NEW.operation='commit' BEGIN SELECT RAISE(ABORT,'synthetic failure'); END")
        with self.assertRaises(sqlite3.IntegrityError):self.store.commit(self.scope,draft["import_id"],request,"atomic-retry-key")
        self.assertEqual(self.count("snapshots"),0)
        self.assertEqual(self.store.get_import(self.scope,draft["import_id"])["status"],"validated")
        with connection(self.path) as conn:conn.execute("DROP TRIGGER inject_failure")
        self.store.commit(self.scope,draft["import_id"],request,"atomic-retry-key")
        self.assertEqual(self.count("snapshots"),1)

    def test_scope_isolation_for_draft_report_commit_and_snapshot(self):
        draft,_,request=self.ready();saved=self.store.commit(self.scope,draft["import_id"],request,"scope-commit-key")
        for scope in [AccessScope("demo",frozenset({"C002"}),self.scope.actor_id,self.scope.permissions),
                      AccessScope("other",frozenset({"C001"}),self.scope.actor_id,self.scope.permissions)]:
            for call in [lambda:self.store.get_import(scope,draft["import_id"]),lambda:self.store.get_report(scope,draft["import_id"]),
                         lambda:self.store.commit(scope,draft["import_id"],request,"scope-commit-key"),lambda:self.store.get_snapshot(scope,saved["snapshot"]["snapshot_id"],data=True)]:
                with self.subTest(scope=scope),self.assertRaises(ImportFailure) as error:call()
                self.assertEqual(error.exception.status,404)

    def test_policy_recheck_occurs_inside_transaction_before_any_write(self):
        changed=AccessScope("demo",self.scope.company_ids,self.scope.actor_id,frozenset())
        with self.assertRaises(ImportFailure):self.store.upload(self.scope,self.raw,"data.json","recheck-upload-key",lambda:changed)
        self.assertEqual(self.count("imports"),0);self.assertEqual(self.count("source_blobs"),0)

    def test_tampered_snapshot_data_is_not_returned_even_on_receipt_replay(self):
        draft,_,request=self.ready();saved=self.store.commit(self.scope,draft["import_id"],request,"tamper-snapshot-key")
        with connection(self.path) as conn:
            conn.execute("DROP TRIGGER snapshots_update");conn.execute("UPDATE snapshots SET data_json=?",(b'{}',))
        for call in [lambda:self.store.get_snapshot(self.scope,saved["snapshot"]["snapshot_id"],data=True),
                     lambda:self.store.commit(self.scope,draft["import_id"],request,"tamper-snapshot-key")]:
            with self.assertRaises(ImportFailure) as error:call()
            self.assertEqual(error.exception.code,"ARTIFACT_INTEGRITY")

    def test_tampered_original_source_cannot_commit(self):
        draft,_,request=self.ready()
        with connection(self.path) as conn:
            conn.execute("DROP TRIGGER source_blobs_update");conn.execute("UPDATE source_blobs SET content=?",(b'{}',))
        with self.assertRaises(ImportFailure) as error:self.store.commit(self.scope,draft["import_id"],request,"tampered-source-key")
        self.assertEqual(error.exception.code,"ARTIFACT_INTEGRITY");self.assertEqual(self.count("snapshots"),0)

    def test_old_snapshots_survive_new_import_of_changed_data(self):
        first,_,request=self.ready();saved=self.store.commit(self.scope,first["import_id"],request,"old-snapshot-key")
        changed=bundle_for();changed["transactions"][0]["description"]="new source version"
        second,_,request=self.ready(canonical(changed),"new-import-key")
        newer=self.store.commit(self.scope,second["import_id"],request,"new-snapshot-key")
        self.assertNotEqual(saved["snapshot"]["snapshot_id"],newer["snapshot"]["snapshot_id"])
        self.assertEqual(self.store.get_snapshot(self.scope,saved["snapshot"]["snapshot_id"],data=True),self.raw)

    def test_legacy_database_is_refused_without_migration(self):
        path=Path(self.temp.name)/"legacy.sqlite3"
        with connection(path) as conn:conn.execute("CREATE TABLE old_reviews(id TEXT)")
        with self.assertRaises(ImportFailure):SnapshotStore(path)
        with connection(path) as conn:
            self.assertEqual(conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall(),[("old_reviews",)])

    def test_commit_receipt_key_cannot_be_reused_for_altered_confirmation(self):
        draft,_,request=self.ready()
        self.store.commit(self.scope,draft["import_id"],request,"bound-receipt-key")
        changed=dict(request,source_hash="0"*64)
        with self.assertRaises(ImportFailure) as error:self.store.commit(self.scope,draft["import_id"],changed,"bound-receipt-key")
        self.assertEqual(error.exception.code,"IDEMPOTENCY_CONFLICT")
        self.assertEqual(self.count("snapshots"),1)

    def test_source_and_mapping_mutation_receipts_do_not_repeat_revisions(self):
        draft,_,_=self.ready()
        raw=self.raw+b'\n'
        first=self.store.revise(self.scope,draft["import_id"],1,"source-retry-key",raw=raw,filename="changed.json")
        again=self.store.revise(self.scope,draft["import_id"],1,"source-retry-key",raw=raw,filename="changed.json")
        self.assertEqual(first,again);self.assertEqual(first["revision"],2)
        mapping={"tables":{"transactions":{"unused_column":"description"}}}
        first=self.store.revise(self.scope,draft["import_id"],2,"mapping-retry-key",mapping=mapping)
        again=self.store.revise(self.scope,draft["import_id"],2,"mapping-retry-key",mapping=mapping)
        self.assertEqual(first,again);self.assertEqual(self.count("import_revisions"),3)

    def test_source_change_racing_commit_has_only_one_winner(self):
        draft,_,request=self.ready();barrier=threading.Barrier(2)
        def operation(commit):
            barrier.wait()
            try:
                if commit:self.store.commit(self.scope,draft["import_id"],request,"racing-commit-key")
                else:self.store.revise(self.scope,draft["import_id"],1,"racing-source-key",raw=self.raw+b'\n',filename="racing.json")
                return "success"
            except ImportFailure as error:return error.code
        with ThreadPoolExecutor(max_workers=2) as workers:
            results=list(workers.map(operation,[True,False]))
        self.assertEqual(results.count("success"),1)
        info=self.store.get_import(self.scope,draft["import_id"])
        self.assertEqual(self.count("snapshots"),1 if info["status"]=="committed" else 0)
        if info["status"]!="committed":self.assertEqual(info["revision"],2);self.assertIsNone(info["active_preview_id"])

    def test_expiry_during_commit_revalidation_does_not_create_snapshot(self):
        draft,_,request=self.ready()
        from sme_fraud.snapshots import parse_file
        def slow_parse(*args):
            result=parse_file(*args);self.now+=timedelta(seconds=61);return result
        with patch("sme_fraud.snapshots.parse_file",side_effect=slow_parse),self.assertRaises(ImportFailure) as error:
            self.store.commit(self.scope,draft["import_id"],request,"expiry-during-commit")
        self.assertEqual(error.exception.code,"PREVIEW_EXPIRED");self.assertEqual(self.count("snapshots"),0)

    def test_permission_change_at_transaction_exit_rolls_back_all_writes(self):
        calls=[]
        def recheck():
            calls.append(1)
            return self.scope if len(calls)==1 else AccessScope("demo",self.scope.company_ids,self.scope.actor_id,frozenset())
        with self.assertRaises(ImportFailure):self.store.upload(self.scope,self.raw,"data.json","last-recheck-key",recheck)
        self.assertEqual(self.count("imports"),0);self.assertEqual(self.count("request_receipts"),0)

    def test_invalid_stored_manifest_json_is_a_controlled_integrity_error(self):
        draft,_,request=self.ready();saved=self.store.commit(self.scope,draft["import_id"],request,"broken-manifest-key")
        with connection(self.path) as conn:
            conn.execute("DROP TRIGGER snapshots_update");conn.execute("UPDATE snapshots SET manifest_json=?",(b'{broken',))
        with self.assertRaises(ImportFailure) as error:self.store.get_snapshot(self.scope,saved["snapshot"]["snapshot_id"])
        self.assertEqual(error.exception.code,"ARTIFACT_INTEGRITY")


class SnapshotApiTests(unittest.TestCase):
    def setUp(self):
        import secrets
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.token=secrets.token_urlsafe(32)
        self.policy=policy_for(self.token);self.policy_file=self.root/"policy.json";self.save_policy()
        self.store=SnapshotStore(self.root/"snapshots.sqlite3")
        self.authorizer=FileAuthorizer(self.policy_file)
        self.server=make_server(0,self.authorizer,self.store)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start();self.addCleanup(self.close)

    def save_policy(self):self.policy_file.write_text(json.dumps(self.policy),encoding="utf-8")
    def close(self):self.server.shutdown();self.server.server_close();self.thread.join(5)
    def call(self,method,path,body=None,raw=None,headers=None,company="C001",data=False):
        base=f"/api/v1/companies/{company}/"
        h={"Authorization":"Bearer "+self.token,"Content-Type":"application/json"};h.update(headers or {})
        payload=raw if raw is not None else canonical(body) if body is not None else None
        conn=http.client.HTTPConnection("127.0.0.1",self.server.server_port,timeout=20);self.addCleanup(conn.close)
        conn.request(method,base+path,payload,h);response=conn.getresponse();content=response.read()
        return response.status,content if data else json.loads(content)

    def ready(self):
        code,draft=self.call("POST","imports/upload",raw=canonical(bundle_for()),headers={"Idempotency-Key":"http-upload-key","X-File-Name":"data.json","Content-Type":"application/octet-stream"})
        self.assertEqual(code,201)
        code,report=self.call("POST",f"imports/{draft['import_id']}/preview",dict(expected_revision=1));self.assertEqual(code,200)
        return draft,report

    def test_full_http_upload_preview_confirm_snapshot_and_download(self):
        draft,report=self.ready()
        path=f"imports/{draft['import_id']}/commit";body=commit_fields(report);headers={"Idempotency-Key":"http-commit-key"}
        code,saved=self.call("POST",path,body,headers=headers);self.assertEqual(code,200)
        for _ in range(10):self.assertEqual(self.call("POST",path,body,headers=headers),(code,saved))
        code,manifest=self.call("GET","snapshots/"+saved["snapshot"]["snapshot_id"])
        self.assertEqual(code,200);self.assertEqual(manifest,saved["snapshot"])
        code,content=self.call("GET","snapshots/"+manifest["snapshot_id"]+"/data",data=True)
        self.assertEqual(code,200);self.assertEqual(digest(content),manifest["data_checksum"])

    def test_mapping_and_source_revision_routes_require_new_preview(self):
        draft,report=self.ready();base=f"imports/{draft['import_id']}"
        code,info=self.call("PUT",base+"/mapping",dict(expected_revision=1,mapping={"tables":{"transactions":{"description":"adjustment_reason"}}}),headers={"Idempotency-Key":"http-mapping-key"})
        self.assertEqual(code,200);self.assertEqual(info["revision"],2)
        self.assertEqual(self.call("POST",base+"/commit",commit_fields(report),headers={"Idempotency-Key":"http-stale-key"})[0],409)
        code,info=self.call("PUT",base+"/source",raw=canonical(bundle_for()),headers={"Idempotency-Key":"http-source-key","X-File-Name":"changed.json","X-Expected-Revision":"2"})
        self.assertEqual(code,200);self.assertEqual(info["revision"],3)

    def test_all_routes_deny_company_b_before_body_or_storage_access(self):
        class Untouchable:
            def read(self,*args):raise AssertionError("unauthorized body read")
            def __getattr__(self,name):raise AssertionError("unauthorized storage access")
        paths=[("POST","imports/upload"),("POST","imports/imp_"+"a"*32+"/preview"),
               ("POST","imports/imp_"+"a"*32+"/commit"),("PUT","imports/imp_"+"a"*32+"/mapping"),
               ("PUT","imports/imp_"+"a"*32+"/source"),("GET","imports/imp_"+"a"*32+"/report"),
               ("GET","snapshots/snp_"+"a"*32),("GET","snapshots/snp_"+"a"*32+"/data")]
        for method,path in paths:
            headers=Message();headers["Host"]="127.0.0.1:12345";headers["Authorization"]="Bearer "+self.token
            results=[]
            handler=SimpleNamespace(path="/api/v1/companies/C002/"+path,headers=headers,server=SimpleNamespace(server_port=12345),rfile=Untouchable(),respond=lambda status,value:results.append((status,value)))
            self.assertTrue(handle_snapshots(handler,self.authorizer,Untouchable(),method))
            self.assertEqual(results[0][0],403);self.assertEqual(results[0][1]["counts"],{})

    def test_revoked_credentials_cannot_commit_or_read_saved_data(self):
        draft,report=self.ready()
        code,saved=self.call("POST",f"imports/{draft['import_id']}/commit",commit_fields(report),headers={"Idempotency-Key":"http-revoke-key"})
        self.assertEqual(code,200)
        self.policy["principals"][0]["memberships"][0]["status"]="revoked";self.save_policy()
        self.assertEqual(self.call("GET","snapshots/"+saved["snapshot"]["snapshot_id"])[0],403)
        self.assertEqual(self.call("POST",f"imports/{draft['import_id']}/commit",commit_fields(report),headers={"Idempotency-Key":"http-revoke-key"})[0],403)

    def test_tampered_or_unacknowledged_client_commit_never_saves(self):
        draft,report=self.ready();body=commit_fields(report)
        self.assertEqual(self.call("POST",f"imports/{draft['import_id']}/commit",dict(body,acknowledge=False),headers={"Idempotency-Key":"http-no-ack-key"})[0],400)
        body["source_hash"]="0"*64
        self.assertEqual(self.call("POST",f"imports/{draft['import_id']}/commit",body,headers={"Idempotency-Key":"http-bad-hash-key"})[0],409)
        with connection(self.store.path) as conn:self.assertEqual(conn.execute("SELECT count(*) FROM snapshots").fetchone()[0],0)

    def test_invalid_file_preview_persists_errors_and_no_snapshot(self):
        code,draft=self.call("POST","imports/upload",raw=b'{not-json',headers={"Idempotency-Key":"http-invalid-key","X-File-Name":"invalid.json"})
        self.assertEqual(code,201)
        code,report=self.call("POST",f"imports/{draft['import_id']}/preview",dict(expected_revision=1))
        self.assertEqual(code,422);self.assertEqual(report["errors"][0]["code"],"INVALID_JSON")
        self.assertEqual(self.call("GET",f"imports/{draft['import_id']}/report")[1],report)

    def test_foreign_bundle_is_rejected_without_foreign_data_in_report(self):
        code,draft=self.call("POST","imports/upload",raw=canonical(bundle_for("C002")),headers={"Idempotency-Key":"http-foreign-key","X-File-Name":"data.json"})
        self.assertEqual(code,201)
        code,report=self.call("POST",f"imports/{draft['import_id']}/preview",dict(expected_revision=1))
        self.assertEqual(code,403);self.assertEqual(report["counts"],{})
        self.assertNotIn("C002",json.dumps(report))

    def test_foreign_resource_ids_on_authorized_company_route_return_no_records(self):
        scope=AccessScope("demo",frozenset({"C002"}),"another-importer",frozenset({"data.import"}))
        draft=self.store.upload(scope,canonical(bundle_for("C002")),"company-b.json","foreign-upload-key")
        report=self.store.preview(scope,draft["import_id"],1)
        saved=self.store.commit(scope,draft["import_id"],commit_fields(report),"foreign-commit-key")
        base=f"imports/{draft['import_id']}"
        requests=[("GET",base,None), ("GET",base+"/report",None),
            ("POST",base+"/preview",dict(expected_revision=1)),("POST",base+"/commit",commit_fields(report)),
            ("PUT",base+"/mapping",dict(expected_revision=1,mapping={})),
            ("GET","snapshots/"+saved["snapshot"]["snapshot_id"],None),
            ("GET","snapshots/"+saved["snapshot"]["snapshot_id"]+"/data",None)]
        for method,path,body in requests:
            with self.subTest(path=path):
                code,value=self.call(method,path,body,headers={"Idempotency-Key":"foreign-resource-key"})
                self.assertEqual(code,404);self.assertEqual(value["counts"],{})
                self.assertNotIn("C002",json.dumps(value))

    def test_permission_revoked_after_body_read_blocks_upload_write(self):
        from sme_fraud.snapshot_api import read_body
        def revoke(handler,**kwargs):
            raw=read_body(handler,**kwargs)
            self.policy["principals"][0]["memberships"][0]["status"]="revoked";self.save_policy()
            return raw
        with patch("sme_fraud.snapshot_api.read_body",side_effect=revoke):
            code,value=self.call("POST","imports/upload",raw=canonical(bundle_for()),headers={"Idempotency-Key":"revoked-upload-key","X-File-Name":"data.json"})
        self.assertEqual(code,403)
        with connection(self.store.path) as conn:self.assertEqual(conn.execute("SELECT count(*) FROM imports").fetchone()[0],0)

    def test_permission_revoked_after_body_read_blocks_commit(self):
        draft,report=self.ready()
        from sme_fraud.snapshot_api import read_json
        def revoke(handler):
            body=read_json(handler)
            self.policy["principals"][0]["memberships"][0]["status"]="revoked";self.save_policy()
            return body
        with patch("sme_fraud.snapshot_api.read_json",side_effect=revoke):
            code,value=self.call("POST",f"imports/{draft['import_id']}/commit",commit_fields(report),headers={"Idempotency-Key":"revoked-commit-key"})
        self.assertEqual(code,403)
        with connection(self.store.path) as conn:self.assertEqual(conn.execute("SELECT count(*) FROM snapshots").fetchone()[0],0)


if __name__=="__main__":unittest.main()
