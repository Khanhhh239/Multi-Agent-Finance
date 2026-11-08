"""Behavioral contracts for the six-type, temporal NetworkX context graph."""
import copy
import json
import unittest

import networkx as nx

from sme_fraud.entity_graph import EntityGraph


CUTOFF = '2025-08-12T12:00:00+07:00'
INITIAL = '2025-01-01T00:00:00+07:00'


def sources():
    def actor(kind, identity, **values):
        return dict(company_id='C001', **{kind+'_id': identity}, recorded_at=INITIAL,
                    bank_account='00123456789', bank_code='BANK_A', phone='0912345678',
                    address='Số 1, Đường A', tax_code='0100000001', **values)
    return dict(employees=[actor('employee', 'E1', full_name='Nhân viên 1')],
                vendors=[actor('vendor', 'V1', name='Nhà cung cấp 1'),
                         actor('vendor', 'V2', name='Nhà cung cấp 2')], entity_links=[])


class EntityGraphTest(unittest.TestCase):
    def test_typed_multigraph_and_json_round_trip_cover_all_six_types(self):
        graph = EntityGraph(sources(), 'C001', CUTOFF)
        self.assertIsInstance(graph.graph, nx.MultiGraph)
        data = json.loads(json.dumps(graph.to_json(), ensure_ascii=False))
        self.assertEqual({n['type'] for n in data['nodes']},
                         {'employee', 'vendor', 'bank_account', 'phone', 'address', 'tax_code'})
        restored = nx.node_link_graph(data, edges='links')
        self.assertEqual(restored.number_of_edges(), graph.graph.number_of_edges())
        self.assertEqual(set(restored), set(graph.graph))
        self.assertTrue(all(e['evidence']['observed_at'] <= CUTOFF for e in data['links']))

    def test_requested_shared_identity_findings_are_grouped_with_evidence(self):
        graph = EntityGraph(sources(), 'C001', CUTOFF)
        findings = {f['type']: f for f in graph.findings()}
        self.assertEqual(set(findings), {'vendor_employee_shared_bank_account', 'vendor_employee_shared_phone',
                                         'vendors_shared_bank_account', 'vendors_shared_address'})
        for finding in findings.values():
            self.assertEqual(finding['vendor_ids'], ['V1', 'V2'])
            self.assertFalse(finding['affects_rule_score'])
            self.assertTrue(finding['evidence_edge_ids'])
        self.assertEqual(findings['vendor_employee_shared_phone']['employee_ids'], ['E1'])

    def test_connected_component_and_bounded_shortest_path(self):
        graph = EntityGraph(sources(), 'C001', CUTOFF)
        vendor, employee = graph.actor('vendor', 'V1'), graph.actor('employee', 'E1')
        self.assertEqual(len(graph.components()), 1)
        result = graph.shortest_path(vendor, employee, relations=['bank_account'])
        self.assertTrue(result['found'])
        self.assertEqual(result['hops'], 2)
        self.assertEqual([e['relation'] for e in result['links']], ['bank_account', 'bank_account'])
        self.assertFalse(graph.shortest_path(vendor, employee, max_depth=1)['found'])

    def test_weak_address_connection_is_queryable_but_not_a_bank_path(self):
        tables = sources()
        for index, row in enumerate([*tables['employees'], *tables['vendors']]):
            row.update(bank_account=str(10000000000+index), phone=str(9111111100+index),
                       tax_code=str(1000000000+index))
        graph = EntityGraph(tables, 'C001', CUTOFF)
        left, right = graph.actor('vendor', 'V1'), graph.actor('vendor', 'V2')
        path = graph.shortest_path(left, right)
        self.assertTrue(path['found'])
        self.assertTrue(all(e['strength'] == 'weak_context' for e in path['links']))
        self.assertFalse(graph.shortest_path(left, right, relations=['bank_account', 'phone'])['found'])
        self.assertEqual([f['type'] for f in graph.findings()], ['vendors_shared_address'])

    def test_bank_institution_and_missing_bank_codes_do_not_merge_accounts(self):
        for codes in (('BANK_A', 'BANK_B', 'BANK_C'), ('', '', '')):
            tables = sources()
            for row, bank in zip([*tables['employees'], *tables['vendors']], codes):
                row['bank_code'] = bank
            graph = EntityGraph(tables, 'C001', CUTOFF)
            self.assertEqual(sum(d['type'] == 'bank_account' for _, d in graph.graph.nodes(data=True)), 3)
            self.assertFalse(any('bank_account' in f['type'] for f in graph.findings()))
            if not any(codes):
                self.assertEqual(len(graph.gaps), 3)

    def test_phone_country_formatting_address_normalization_and_leading_zeros(self):
        tables = sources()
        tables['vendors'][0].update(phone='+84 912 345 678', address='SO 1 DUONG A',
                                     bank_account='0012 345-6789')
        graph = EntityGraph(tables, 'C001', CUTOFF)
        self.assertEqual(sum(d['type'] == 'phone' for _, d in graph.graph.nodes(data=True)), 1)
        self.assertEqual(sum(d['type'] == 'address' for _, d in graph.graph.nodes(data=True)), 1)
        self.assertTrue(any(d.get('label') == 'BANKA · 00123456789' for _, d in graph.graph.nodes(data=True)))

    def test_blank_identities_do_not_create_shared_attribute_nodes(self):
        tables = sources()
        for row in [*tables['employees'], *tables['vendors']]:
            row.update(bank_account='', phone='', address='', tax_code='')
        graph = EntityGraph(tables, 'C001', CUTOFF)
        self.assertEqual(len(graph.graph), 3)
        self.assertEqual(graph.graph.number_of_edges(), 0)
        self.assertEqual(len(graph.components()), 3)
        self.assertFalse(graph.findings())

    def test_future_revisions_and_links_cannot_change_past_graph(self):
        tables = sources()
        before = EntityGraph(tables, 'C001', CUTOFF).to_json()
        tables['vendors'].append(dict(tables['vendors'][0], recorded_at='2025-09-01T00:00:00+07:00', phone='0988888888'))
        tables['entity_links'].append(dict(company_id='C001', source_id='V1', target_id='0999999999',
                                          link_type='phone', observed_at='2025-09-01T00:00:00+07:00'))
        self.assertEqual(EntityGraph(tables, 'C001', CUTOFF).to_json(), before)

    def test_replacement_and_clearing_rebuild_components_and_retire_mirrors(self):
        tables = sources()
        first = tables['vendors'][0]
        tables['entity_links'].append(dict(company_id='C001', source_id='V1', target_id=first['phone'],
                                          link_type='phone', observed_at=INITIAL))
        for new_phone in ('0988888888', ''):
            changed = copy.deepcopy(tables)
            changed['vendors'].append(dict(first, recorded_at='2025-08-01T00:00:00+07:00', phone=new_phone))
            graph = EntityGraph(changed, 'C001', CUTOFF)
            hits = [f for f in graph.findings() if f['type'] == 'vendor_employee_shared_phone']
            self.assertEqual(hits[0]['vendor_ids'], ['V2'])

    def test_master_tombstone_wins_over_same_time_link_independent_of_order(self):
        tables = sources()
        tables['vendors'][0]['phone'] = ''
        tables['entity_links'] = [dict(company_id='C001', source_id='V1', target_id='0912345678',
                                       link_type='phone', observed_at=INITIAL)]
        graph = EntityGraph(tables, 'C001', CUTOFF)
        hits = [f for f in graph.findings() if f['type'] == 'vendor_employee_shared_phone']
        self.assertEqual(hits[0]['vendor_ids'], ['V2'])

    def test_revoke_old_link_does_not_cancel_its_replacement(self):
        tables = sources()
        tables['entity_links'] = [dict(company_id='C001', source_id='V1', target_id='0988888888',
                                       link_type='phone', observed_at='2025-07-01T00:00:00+07:00'),
                                  dict(company_id='C001', source_id='V1', target_id='0912345678',
                                       link_type='phone', observed_at='2025-07-02T00:00:00+07:00', status='revoked')]
        graph = EntityGraph(tables, 'C001', CUTOFF)
        actor = graph.actor('vendor', 'V1')
        self.assertTrue(any(graph.graph.nodes[n].get('label') == '0988888888' for n in graph.graph.neighbors(actor)))

    def test_source_order_and_duplicate_rows_do_not_change_json_or_component_ids(self):
        tables = sources()
        before = EntityGraph(tables, 'C001', CUTOFF)
        changed = {name: list(reversed(rows))+copy.deepcopy(rows) for name, rows in tables.items()}
        after = EntityGraph(changed, 'C001', CUTOFF)
        self.assertEqual(after.to_json(), before.to_json())
        self.assertEqual(after.components(), before.components())

    def test_same_raw_id_and_identity_in_two_companies_never_cross_boundaries(self):
        tables = sources()
        for name in ('employees', 'vendors'):
            tables[name] += [dict(r, company_id='C002') for r in tables[name]]
        first, second = (EntityGraph(tables, company, CUTOFF) for company in ('C001', 'C002'))
        self.assertFalse(set(first.graph) & set(second.graph))
        self.assertEqual(len(first.graph), len(second.graph))

    def test_parent_and_branch_tax_ids_remain_distinct(self):
        tables = sources()
        tables['vendors'][0]['tax_code'] = '0100000001-001'
        graph = EntityGraph(tables, 'C001', CUTOFF)
        self.assertEqual(sum(d['type'] == 'tax_code' for _, d in graph.graph.nodes(data=True)), 2)

    def test_bounded_visualization_is_explicit_and_does_not_emit_incomplete_findings(self):
        graph = EntityGraph(sources(), 'C001', CUTOFF)
        result = graph.to_json([graph.actor('vendor', 'V1')], max_nodes=2)
        self.assertTrue(result['scope']['truncated'])
        self.assertEqual(len(result['nodes']), 2)
        self.assertFalse(result['findings'])
        self.assertFalse(graph.to_json(max_nodes=None)['scope']['truncated'])

    def test_malformed_conflicting_versions_and_invalid_queries_are_rejected(self):
        for update in ({'phone': 912345678}, {'bank_account': 12345678}):
            tables = sources()
            tables['vendors'][0].update(update)
            with self.subTest(update=update), self.assertRaises(ValueError):
                EntityGraph(tables, 'C001', CUTOFF)
        tables = sources()
        tables['vendors'].append(dict(tables['vendors'][0], phone='0988888888'))
        with self.assertRaisesRegex(ValueError, 'Conflicting'):
            EntityGraph(tables, 'C001', CUTOFF)
        graph = EntityGraph(sources(), 'C001', CUTOFF)
        with self.assertRaises(ValueError):
            graph.to_json(max_nodes=0)
        with self.assertRaises(KeyError):
            graph.actor('vendor', 'NO_SUCH_VENDOR')
