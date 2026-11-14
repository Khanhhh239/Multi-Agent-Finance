"""Synthetic-only checks of backend scope, diagnostics and source limitations."""
import copy
from datetime import datetime, timedelta, timezone
from email.message import Message
import hashlib
import http.client
import json
from pathlib import Path
import secrets
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from finance_input import AccessScope
from finance_input.json_io import loads
from sme_fraud.auth import FileAuthorizer
from sme_fraud.imports import validate_input
from sme_fraud.review_server import make_server
from sme_fraud.validation_api import handle_validation

FIXTURE = Path(__file__).parent / "fixtures/input_contract_v1.json"


def bundle_for(company="C001"):
    data = json.loads(FIXTURE.read_text("utf-8"))
    for table, rows in data.items():
        if isinstance(rows, list):
            data[table] = [r for r in rows if r["company_id"] == company]
    return data


def policy_for(token):
    return dict(policy_version="1.0.0", principals=[dict(actor_id="synthetic-reviewer", tenant_id="demo",
        token_sha256=hashlib.sha256(token.encode()).hexdigest(), status="active",
        expires_at=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(),
        memberships=[dict(company_id="C001", role="accountant", status="active", permissions=["data.import"])])])


class ValidationApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)/"policy.json"
        self.token = secrets.token_urlsafe(32)
        self.policy = policy_for(self.token)
        self.save_policy()
        self.authorizer = FileAuthorizer(self.path)
        self.server = make_server(0, self.authorizer)
        self.thread = threading.Thread(target=self.server.serve_forever,daemon=True); self.thread.start()
        self.addCleanup(self.close)

    def save_policy(self):
        self.path.write_text(json.dumps(self.policy),encoding="utf-8")

    def close(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(5)

    def request(self, body=None, company="C001", headers=None, raw=None):
        content = raw if raw is not None else json.dumps(body if body is not None else bundle_for(),ensure_ascii=False).encode("utf-8")
        request_headers = {"Authorization": "Bearer "+self.token, "Content-Type": "application/json"}
        if headers:
            request_headers.update(headers)
        connection = http.client.HTTPConnection("127.0.0.1",self.server.server_port,timeout=10)
        self.addCleanup(connection.close)
        connection.request("POST",f"/api/v1/companies/{company}/imports/validate",content,request_headers)
        response = connection.getresponse()
        return response.status,json.loads(response.read())

    def test_authorized_validation_keeps_signed_rows_and_uses_backend_scope(self):
        status, report = self.request()
        self.assertEqual(status,200)
        self.assertEqual(report["counts"]["transactions"],3)
        self.assertEqual(report["validator_version"],"1.3.0")
        self.assertEqual(set(report["capabilities"]),{"C001"})
        self.assertTrue(report["analysis_limits"]["C001"])
        self.assertEqual(set(Path(self.temp.name).iterdir()),{self.path})  # nothing persisted by validation

    def test_missing_wrong_or_expired_credential_is_401(self):
        for value in ["", "Bearer "+secrets.token_urlsafe(32), "Basic ignored"]:
            with self.subTest(value=value[:6]):
                status, report = self.request(headers={"Authorization":value})
                self.assertEqual(status,401); self.assertFalse(report["counts"])
        self.policy["principals"][0]["expires_at"] = "2020-01-01T00:00:00Z"; self.save_policy()
        self.assertEqual(self.request()[0],401)

    def test_company_b_denied_before_reading_or_parsing_body(self):
        class Unreadable:
            def read(self,*args): raise AssertionError("Unauthorized body was read")
        headers = Message(); headers["Host"]="127.0.0.1:12345"; headers["Authorization"]="Bearer "+self.token
        result=[]
        handler=SimpleNamespace(path="/api/v1/companies/C002/imports/validate",headers=headers,
            server=SimpleNamespace(server_port=12345),rfile=Unreadable(),
            respond=lambda status,report:result.append((status,report)))
        self.assertTrue(handle_validation(handler,self.authorizer))
        self.assertEqual(result[0][0],403)
        self.assertEqual(result[0][1]["counts"],{})
        self.assertEqual(result[0][1]["analysis_limits"],{})

    def test_unauthenticated_body_is_never_read(self):
        class Unreadable:
            def read(self,*args):raise AssertionError("Unauthenticated body was read")
        headers=Message();headers["Host"]="127.0.0.1:12345"
        result=[]
        handler=SimpleNamespace(path="/api/v1/companies/C001/imports/validate",headers=headers,
            server=SimpleNamespace(server_port=12345),rfile=Unreadable(),
            respond=lambda status,report:result.append((status,report)))
        handle_validation(handler,self.authorizer)
        self.assertEqual(result[0][0],401)

    def test_director_without_company_permission_is_still_denied(self):
        member=self.policy["principals"][0]["memberships"][0]
        member.update(role="director",permissions=[]);self.save_policy()
        self.assertEqual(self.request()[0],403)
        self.assertEqual(self.request(company="C002")[0],403)

    def test_revocation_read_on_every_request(self):
        self.assertEqual(self.request()[0],200)
        self.policy["principals"][0]["memberships"][0]["status"]="revoked";self.save_policy()
        self.assertEqual(self.request(raw=b'invalid-json')[0],403)

    def test_global_credential_revocation(self):
        self.policy["principals"][0]["status"]="revoked";self.save_policy()
        self.assertEqual(self.request()[0],401)

    def test_missing_or_invalid_policy_fails_closed_without_data_echo(self):
        self.path.write_text('{"secret":"never_echo_this"}',encoding="utf-8")
        status,report=self.request()
        self.assertEqual(status,503)
        self.assertNotIn("never_echo_this",json.dumps(report))
        self.path.unlink()
        self.assertEqual(self.request()[0],503)

    def test_client_cannot_grant_itself_another_company_or_tenant(self):
        status,report=self.request(bundle_for("C002"))
        self.assertEqual(status,403)
        self.assertFalse(report["counts"]);self.assertFalse(report["capabilities"])
        self.assertNotIn("C002",json.dumps(report))
        data=bundle_for();data["tenant_id"]="another-tenant"
        self.assertEqual(self.request(data)[0],403)

    def test_foreign_row_cannot_be_hidden_in_valid_company_bundle(self):
        data=bundle_for();data["transactions"].append(bundle_for("C002")["transactions"][0])
        status,report=self.request(data)
        self.assertEqual(status,403);self.assertFalse(report["counts"])
        self.assertFalse(report["analysis_limits"])

    def test_even_multi_company_credential_must_validate_one_company_per_route(self):
        self.policy["principals"][0]["memberships"].append(dict(company_id="C002",role="director",status="active",permissions=["data.import"]))
        self.save_policy()
        self.assertEqual(self.request(bundle_for("C002"),company="C002")[0],200)
        all_data=json.loads(FIXTURE.read_text("utf-8"))
        self.assertEqual(self.request(all_data,company="C001")[0],403)

    def test_missing_transaction_id_reports_row_field_and_fix(self):
        data=bundle_for();data["transactions"][1].pop("record_id")
        status,report=self.request(data)
        self.assertEqual(status,422)
        error=next(e for e in report["errors"] if e["field"]=="record_id")
        self.assertEqual(error["table"],"transactions");self.assertEqual(error["row"],2)
        self.assertIn("mã giao dịch",error["message"]);self.assertTrue(error["action"])

    def test_missing_company_column_is_diagnostic_not_fake_authorization_error(self):
        data=bundle_for();data["transactions"][0].pop("company_id")
        status,report=self.request(data)
        self.assertEqual(status,422)
        self.assertTrue(any(e["row"]==1 and e["field"]=="company_id" for e in report["errors"]))
        for value in [None,"",["C001"]," C001 "]:
            with self.subTest(company_id=value):
                data=bundle_for();data["transactions"][0]["company_id"]=value
                status,report=self.request(data)
                self.assertEqual(status,422)
                self.assertTrue(any(e["row"]==1 and e["field"]=="company_id" for e in report["errors"]))

    def test_missing_required_table_names_the_table(self):
        data=bundle_for();data.pop("payment_allocations")
        status,report=self.request(data)
        self.assertEqual(status,422)
        self.assertTrue(any(e["path"]=="/payment_allocations" and e["code"]=="REQUIRED_FIELD" for e in report["errors"]))

    def test_wrong_type_duplicate_and_reference_show_actual_field(self):
        for mutation,expected in [
            (lambda d:d["transactions"][0].update(amount_vnd=1.5),"amount_vnd"),
            (lambda d:d["transactions"].append(copy.deepcopy(d["transactions"][0])),"record_id"),
            (lambda d:d["payment_allocations"][0]["invoice_ref"].update(record_id="not-found"),"invoice_ref"),
        ]:
            with self.subTest(field=expected):
                data=bundle_for();mutation(data)
                status,report=self.request(data)
                self.assertEqual(status,422)
                error=next(e for e in report["errors"] if e["field"]==expected)
                self.assertIsInstance(error["row"],int);self.assertTrue(error["action"])

    def test_nested_reference_required_key_identified(self):
        data=bundle_for();data["payment_allocations"][0]["invoice_ref"].pop("revision")
        status,report=self.request(data)
        self.assertEqual(status,422)
        self.assertTrue(any(e["field"]=="invoice_ref/revision" for e in report["errors"]))

    def test_client_scope_role_extra_fields_are_not_accepted(self):
        data=bundle_for();data["scope"]={"role":"director","company_ids":["C002"]}
        status,report=self.request(data)
        self.assertEqual(status,422)
        self.assertTrue(any(e["path"]=="/scope" and e["code"]=="UNKNOWN_FIELD" for e in report["errors"]))

    def test_broken_json_duplicate_keys_and_nonfinite_values_rejected(self):
        for raw in [b'{',b'{"tenant_id":"demo","tenant_id":"other"}',b'{"x":NaN}',b'{"x":Infinity}',b'\xff']:
            with self.subTest(raw=raw):
                self.assertEqual(self.request(raw=raw)[0],400)

    def test_input_size_rows_and_media_limits(self):
        with patch("sme_fraud.validation_api.MAX_BYTES",10):self.assertEqual(self.request()[0],413)
        with patch("sme_fraud.validation_api.MAX_ROWS",1):self.assertEqual(self.request()[0],413)
        self.assertEqual(self.request(headers={"Content-Type":"text/csv"})[0],415)
        self.assertEqual(self.request(headers={"Content-Encoding":"gzip"})[0],415)

    def test_untrusted_origin_denied(self):
        self.assertEqual(self.request(headers={"Origin":"https://untrusted.example"})[0],403)

    def test_bad_transport_headers_rejected_before_read(self):
        for headers in [{"Content-Length":"bad"},{"Content-Length":"0"},{"Transfer-Encoding":"chunked"}]:
            with self.subTest(headers=headers):self.assertEqual(self.request(headers=headers)[0],400)

    def test_duplicate_authorization_headers_do_not_choose_one(self):
        class Unreadable:
            def read(self,*args):raise AssertionError("Body must not be read")
        headers=Message();headers["Host"]="127.0.0.1:12345"
        headers["Authorization"]="Bearer "+self.token;headers["Authorization"]="Bearer "+self.token
        result=[]
        handler=SimpleNamespace(path="/api/v1/companies/C001/imports/validate",headers=headers,
            server=SimpleNamespace(server_port=12345),rfile=Unreadable(),
            respond=lambda status,report:result.append((status,report)))
        handle_validation(handler,self.authorizer)
        self.assertEqual(result[0][0],401)

    def test_security_errors_do_not_echo_raw_transaction_or_token(self):
        data=bundle_for();data["transactions"][0]["description"]="PII-must-not-echo"
        data["transactions"][0]["amount_vnd"]="sensitive-amount"
        status,report=self.request(data)
        self.assertEqual(status,422)
        output=json.dumps(report)
        for value in [self.token,"PII-must-not-echo","sensitive-amount"]:self.assertNotIn(value,output)


class SourceLimitTests(unittest.TestCase):
    def setUp(self):
        self.data=bundle_for()
        self.scope=AccessScope("demo",frozenset({"C001"}),"synthetic",frozenset({"data.import","evidence.verify"}))

    def limits(self):return validate_input(self.data,self.scope)["analysis_limits"]["C001"]

    def test_one_simulated_document_does_not_clear_other_transactions(self):
        limit=next(l for l in self.limits() if l["analysis"]=="document_verification")
        self.assertEqual(limit["affected_count"],3)
        self.assertIn("chưa đủ căn cứ",limit["message"])

    def test_verified_original_covers_only_linked_transaction(self):
        doc=self.data["supporting_documents"][0]
        doc.update(source_kind="original",verification_status="verified",
            verification=dict(verified_by="synthetic",verified_at=doc["observed_at"],basis="Synthetic verification fixture"))
        doc["source"]["is_simulated"]=False
        limit=next(l for l in self.limits() if l["analysis"]=="document_verification")
        self.assertEqual(limit["affected_count"],2)
        self.assertNotIn("T001",{r["record_id"] for r in limit["affected_rows"]})

    def test_document_linked_to_invoice_is_traced_through_allocations(self):
        doc=self.data["supporting_documents"][0]
        doc.update(source_kind="original",verification_status="verified",
            subject_refs=[dict(table="invoices",record_id="I001",revision=1)],
            verification=dict(verified_by="synthetic",verified_at=doc["observed_at"],basis="Synthetic invoice fixture"))
        doc["source"]["is_simulated"]=False
        limit=next(l for l in self.limits() if l["analysis"]=="document_verification")
        self.assertEqual({r["record_id"] for r in limit["affected_rows"]},{"ADJ001"})

    def test_new_unverified_revision_cannot_use_older_verified_status(self):
        doc=self.data["supporting_documents"][0]
        doc.update(source_kind="original",verification_status="verified",
            verification=dict(verified_by="synthetic",verified_at=doc["observed_at"],basis="Synthetic old fixture"))
        doc["source"]["is_simulated"]=False
        revision=copy.deepcopy(doc);revision.update(revision=2,verification_status="unverified",observed_at="2026-10-11T10:00:00+07:00")
        revision.pop("verification");self.data["supporting_documents"].append(revision)
        limit=next(l for l in self.limits() if l["analysis"]=="document_verification")
        self.assertEqual(limit["affected_count"],3)

    def test_missing_history_does_not_remove_transactions_or_claim_ml_readiness(self):
        report=validate_input(self.data,self.scope)
        self.assertEqual(report["status"],"accepted_with_warnings")
        self.assertEqual(report["counts"]["transactions"],3)
        self.assertTrue(any(l["analysis"]=="bank_change_analysis" for l in report["analysis_limits"]["C001"]))
        self.assertNotIn("ml_ready",report["capabilities"]["C001"])

    def test_missing_approval_coverage_is_per_transaction(self):
        limit=next(l for l in self.limits() if l["analysis"]=="approval_trace")
        self.assertEqual({r["record_id"] for r in limit["affected_rows"]},{"T002"})

    def test_bank_history_for_one_vendor_does_not_cover_another_vendor(self):
        vendor=copy.deepcopy(self.data["vendors"][0]);vendor.update(record_id="V002");self.data["vendors"].append(vendor)
        self.data["transactions"][1]["vendor_ref"]=dict(record_id="V002",revision=1)
        bank=copy.deepcopy(self.data["vendors"][0]);bank.pop("name")
        bank.update(record_id="BH001",vendor_ref=dict(record_id="V001",revision=1),bank_account="00123",bank_code="BANK",verification_status="unverified")
        self.data["vendor_bank_history"]=[bank]
        report=validate_input(self.data,self.scope)
        self.assertTrue(report["capabilities"]["C001"]["bank_change_input"]["available"])
        limit=next(l for l in report["analysis_limits"]["C001"] if l["analysis"]=="bank_change_analysis")
        self.assertEqual({r["record_id"] for r in limit["affected_rows"]},{"T002"})

    def test_strict_shared_parser_never_accepts_duplicate_keys(self):
        with self.assertRaises(ValueError):loads('{"amount_vnd":10,"amount_vnd":20}')


if __name__=="__main__":unittest.main()
