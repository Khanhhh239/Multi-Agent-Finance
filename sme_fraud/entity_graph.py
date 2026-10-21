"""Typed, company-scoped NetworkX relationships from evidence known at a cutoff.

This context graph includes weak address/tax links. It does not replace the
narrower A3/B2 scoring graph or transfer findings into numeric risk scores.
"""
from collections import defaultdict
from datetime import datetime, timedelta, timezone
import hashlib
import json
import re

import networkx as nx

from .temporal_evidence import bank_identity, bank_token


GRAPH_VERSION = 'entity-network-v1'
VN = timezone(timedelta(hours=7))
FIELDS = ('bank_account', 'phone', 'address', 'tax_code')
NODE_TYPES = ('employee', 'vendor', *FIELDS)
TABLES = ('employees', 'vendors', 'entity_links')


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':')).encode()).hexdigest()


def as_of(value):
    parsed = datetime.fromisoformat(value)
    if parsed.utcoffset() is None:
        raise ValueError('Entity graph timestamps require an explicit timezone')
    return parsed.astimezone(VN).isoformat()


def node_id(company, kind, value):
    if kind not in NODE_TYPES:
        raise ValueError('Unknown entity graph node type')
    return f'{kind}:{digest([company, kind, value])[:24]}'


def normalized(value, kind, bank_code=''):
    if not isinstance(value, str):
        raise ValueError(f'Graph {kind} must be a string; preserve leading zeros')
    token = bank_token(value)
    if kind == 'bank_account':
        return bank_identity(value, bank_code)
    if kind == 'phone':
        if token.startswith('0084') and len(token) == 13:
            token = '0'+token[4:]
        elif token.startswith('84') and len(token) == 11:
            token = '0'+token[2:]
        return token if token.startswith('PHONESYN') or re.fullmatch(r'[0-9]{9,15}', token) else ''
    if kind == 'tax_code':
        return token if token.startswith('MSTSYN') or re.fullmatch(r'(?:[0-9]{10}|[0-9]{13})', token) else ''
    return token


def bounded_int(value, name, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f'{name} must be an integer between {low} and {high}')
    return value


def binding(value, kind, bank_code=''):
    return normalized(value, kind, bank_code) or digest([bank_token(value), bank_token(bank_code)])


class EntityGraph:
    """A deterministic snapshot: rebuilding also removes replaced/deleted edges."""
    def __init__(self, tables, company_id, cutoff):
        if not isinstance(company_id, str) or not company_id.strip():
            raise ValueError('A company_id is required for entity graph queries')
        self.company_id, self.cutoff = company_id, as_of(cutoff)
        self.graph = nx.MultiGraph(schema_version=GRAPH_VERSION, company_id=company_id, as_of=self.cutoff)
        self.entities, self.gaps = {}, []
        slots, revisions = {}, {}
        for table, kind, identifier, label in (
                ('employees', 'employee', 'employee_id', 'full_name'),
                ('vendors', 'vendor', 'vendor_id', 'name')):
            latest = {}
            for raw in tables.get(table, []):
                if raw.get('company_id') != company_id:
                    continue
                identity = raw.get(identifier)
                if not isinstance(identity, str) or not identity or identity != identity.strip():
                    raise ValueError(f'Invalid graph {identifier}')
                at = as_of(raw['recorded_at'])
                key = kind, identity, at
                if key in revisions and revisions[key] != raw:
                    raise ValueError('Conflicting graph master revision')
                revisions[key] = raw
                if at <= self.cutoff and (identity not in latest or at > latest[identity][0]):
                    latest[identity] = at, raw
            for identity, (at, row) in sorted(latest.items()):
                if row.get('status') in {'deleted', 'revoked'}:
                    continue
                actor = node_id(company_id, kind, identity)
                self.entities[(kind, identity)] = actor
                self.graph.add_node(actor, type=kind, entity_id=identity,
                                    label=str(row.get(label) or identity), observed_at=at)
                for field in FIELDS:
                    if field in row:
                        slots[(kind, identity, field)] = ((at, 1), row[field], row.get('bank_code', ''),
                            dict(source_table=table, source_id=identity, observed_at=at, source_sha256=digest(row)))

        by_identity = defaultdict(list)
        for kind, identity in self.entities:
            by_identity[identity].append(kind)
        links = sorted(tables.get('entity_links', []),
                       key=lambda r: (r.get('observed_at', ''), digest(r)))
        for row in links:
            if row.get('company_id') != company_id or row.get('link_type') not in FIELDS:
                continue
            at = as_of(row['observed_at'])
            if at > self.cutoff or row.get('effective_at') and as_of(row['effective_at']) > self.cutoff:
                continue
            identity, field = row['source_id'], row['link_type']
            kinds = by_identity.get(identity, [])
            if row.get('source_kind'):
                kinds = [kind for kind in kinds if kind == row['source_kind']]
            if len(kinds) != 1:
                # Representative-only legacy links are outside the six-type
                # contract. They remain available in existing rule proof paths.
                continue
            slot = kinds[0], identity, field
            previous = slots.get(slot)
            rank = at, 0
            if previous and rank < previous[0]:
                continue
            status = row.get('status') or 'active'
            if status not in {'active', 'revoked', 'deleted', 'inactive'}:
                raise ValueError('Invalid entity graph link status')
            value, bank = row.get('target_id', ''), row.get('bank_code', '')
            if status != 'active':
                if value and previous and binding(value, field, bank) != binding(previous[1], field, previous[2]):
                    continue
                value = ''
            if previous and rank == previous[0] and binding(value, field, bank) != binding(previous[1], field, previous[2]):
                raise ValueError('Conflicting graph link revision')
            slots[slot] = (rank, value, bank, dict(source_table='entity_links', source_id=row.get('link_id') or digest(row),
                                                    observed_at=at, source_sha256=digest(row)))

        for (kind, identity, field), (rank, value, bank, proof) in sorted(slots.items()):
            if not value:
                continue
            if not isinstance(value, str) or not isinstance(bank, str):
                raise ValueError('Graph identity fields must be strings')
            token = normalized(value, field, bank)
            verified = bool(token)
            # Unknown-bank accounts remain visible as separate unconfirmed
            # nodes. Equal digits alone must never merge different institutions.
            if not token:
                token = digest([kind, identity, field, bank_token(value)])
                self.gaps.append(dict(entity_type=kind, entity_id=identity, field=field,
                                      reason='missing_bank_code' if field == 'bank_account' else 'unrecognized_identity_format'))
            target = node_id(company_id, field, token)
            label = (f'{bank_token(bank)} · {bank_token(value)}' if field == 'bank_account' and bank else bank_token(value))
            self.graph.add_node(target, type=field, label=label, value=token,
                                matchable=verified, identity_scope='company')
            actor = self.entities[(kind, identity)]
            key = digest([company_id, kind, identity, field, target])[:24]
            self.graph.add_edge(actor, target, key=key, id=key, relation=field,
                                observed_at=rank[0], evidence=proof,
                                strength='weak_context' if field in {'address', 'tax_code'} else
                                         'identity_match' if verified else 'unconfirmed_identity')
        # NetworkX shortest-path tie breaking follows adjacency insertion order.
        # Canonical insertion makes every query/export independent of source order.
        canonical = nx.MultiGraph(**self.graph.graph)
        canonical.add_nodes_from(sorted(self.graph.nodes(data=True)))
        edges = sorted(self.graph.edges(keys=True, data=True), key=lambda e: e[2])
        canonical.add_edges_from(edges)
        self.graph = canonical

    def actor(self, kind, identity):
        if kind not in {'employee', 'vendor'}:
            raise ValueError('Entity kind must be employee or vendor')
        try:
            return self.entities[(kind, identity)]
        except KeyError:
            raise KeyError('Entity not known in this company at the requested cutoff') from None

    def components(self):
        return sorted((dict(id='component:'+digest([self.company_id, sorted(nodes)])[:24], nodes=sorted(nodes))
                       for nodes in nx.connected_components(self.graph)), key=lambda r: r['id'])

    def shortest_path(self, source, target, *, max_depth=6, relations=None):
        bounded_int(max_depth, 'Path depth', 0, 20)
        allowed = set(FIELDS if relations is None else relations)
        if allowed-set(FIELDS):
            raise ValueError('Unknown graph relation')
        graph = nx.subgraph_view(self.graph, filter_edge=lambda u, v, k: self.graph[u][v][k]['relation'] in allowed)
        if source not in graph or target not in graph:
            raise KeyError('Unknown graph path endpoint')
        paths = nx.single_source_shortest_path(graph, source, cutoff=max_depth)
        nodes = paths.get(target, [])
        links = []
        for left, right in zip(nodes, nodes[1:]):
            key = min(graph[left][right])
            links.append(dict(graph[left][right][key], source=left, target=right, key=key))
        return dict(found=bool(nodes), nodes=nodes, links=links, hops=len(links),
                    company_id=self.company_id, as_of=self.cutoff)

    def findings(self):
        result = []
        for attribute, data in sorted(self.graph.nodes(data=True)):
            field = data['type']
            if field not in FIELDS or not data.get('matchable'):
                continue
            neighbors = sorted(self.graph.neighbors(attribute))
            vendors = [n for n in neighbors if self.graph.nodes[n]['type'] == 'vendor']
            employees = [n for n in neighbors if self.graph.nodes[n]['type'] == 'employee']
            types = []
            if vendors and employees and field in {'bank_account', 'phone'}:
                types.append('vendor_employee_shared_'+field)
            if len(vendors) >= 2 and field in {'bank_account', 'address'}:
                types.append('vendors_shared_'+field)
            for finding_type in types:
                actors = sorted(vendors+employees) if finding_type.startswith('vendor_employee') else vendors
                result.append(dict(id='relation:'+digest([finding_type, attribute, actors])[:24],
                    type=finding_type, attribute_node=attribute, entity_nodes=actors,
                    vendor_ids=sorted(self.graph.nodes[n]['entity_id'] for n in vendors),
                    employee_ids=sorted(self.graph.nodes[n]['entity_id'] for n in employees)
                                 if finding_type.startswith('vendor_employee') else [],
                    evidence_edge_ids=sorted(k for actor in actors for k in self.graph[actor][attribute]),
                    classification='relationship_for_review', affects_rule_score=False))
        return sorted(result, key=lambda r: r['id'])

    def to_json(self, seeds=None, *, depth=2, max_nodes=200):
        bounded_int(depth, 'Network depth', 0, 6)
        if max_nodes is None:
            max_nodes = max(1, len(self.graph))  # Explicit full batch export.
        else:
            bounded_int(max_nodes, 'Maximum graph nodes', 1, 1000)
        if seeds is None:
            distances = {n: 0 for n in self.graph}
        else:
            if len(set(seeds)) > max_nodes:
                raise ValueError('Maximum graph nodes must accommodate all seed entities')
            distances = {}
            for seed in sorted(set(seeds)):
                if seed not in self.graph:
                    raise KeyError('Unknown graph seed')
                for node, distance in nx.single_source_shortest_path_length(self.graph, seed, cutoff=depth).items():
                    distances[node] = min(distance, distances.get(node, distance))
        selected = sorted(distances, key=lambda n: (distances[n], n))[:max_nodes]
        subgraph = self.graph.subgraph(selected)
        payload = nx.node_link_data(subgraph, edges='links')
        payload['nodes'].sort(key=lambda n: n['id'])
        payload['links'].sort(key=lambda e: e['key'])
        # Do not emit a finding with missing participant nodes as if complete.
        selected_set = set(selected)
        payload['findings'] = [f for f in self.findings()
                               if {f['attribute_node'], *f['entity_nodes']} <= selected_set]
        payload['components'] = [sorted(nodes) for nodes in nx.connected_components(subgraph)]
        payload['components'].sort()
        payload['information_gaps'] = sorted(self.gaps, key=lambda r: (r['entity_type'], r['entity_id'], r['field']))
        payload['scope'] = dict(company_id=self.company_id, as_of=self.cutoff, context_only=True,
                               components_scope='returned_subgraph', truncated=len(selected) < len(distances),
                               candidate_nodes=len(distances), returned_nodes=len(selected),
                               full_graph_nodes=len(self.graph), full_graph_edges=self.graph.number_of_edges(),
                               findings_complete=len(selected) == len(self.graph))
        return payload
