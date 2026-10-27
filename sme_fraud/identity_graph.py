"""Shared current identity slots and replaceable, company-scoped graph edges."""
from collections import defaultdict, deque
from functools import lru_cache

from .case_identity import component_key
from .identity import normalize
from .temporal_evidence import bank_identity


def master_versions(rows, id_field):
    """Deduplicate snapshots and reject ambiguous identities before as-of use."""
    versions = {}
    for row in rows:
        key = row[id_field], row['recorded_at']
        if key in versions and versions[key] != row:
            raise ValueError(f'Conflicting master revision: {id_field}/{key}')
        versions[key] = row
    return sorted(versions.values(), key=lambda r: (r['recorded_at'], r[id_field]))


class UnionFind:
    def __init__(self):
        self.parent, self.size, self.employees, self.vendors = {}, {}, {}, {}

    def add(self, node, employee=False, vendor=False):
        if node not in self.parent:
            self.parent[node], self.size[node] = node, 1
            self.employees[node], self.vendors[node] = int(employee), int(vendor)

    def root(self, node):
        if node not in self.parent:
            self.add(node)
        while node!=self.parent[node]:
            self.parent[node] = self.parent[self.parent[node]]
            node = self.parent[node]
        return node

    def join(self, left, right):
        l, r = self.root(left), self.root(right)
        if l==r:
            return
        if self.size[l]<self.size[r]:
            l, r = r, l
        self.parent[r] = l
        self.size[l] += self.size[r]
        self.employees[l] += self.employees[r]
        self.vendors[l] += self.vendors[r]


class KnownGraph:
    """Current identity slots, with replaceable edges and as-of evidence paths.

    A (company, source, kind) slot has one current bank/phone/representative.
    Empty targets are retained as tombstones so old mirrored links cannot return.
    At the same observed timestamp a master snapshot outranks its link mirror.
    """
    def __init__(self):
        self.groups = defaultdict(UnionFind)
        self.adjacency = defaultdict(lambda: defaultdict(dict))
        self.current = defaultdict(dict)
        self.identities = defaultdict(dict)
        self.dirty = set()
        self.members = defaultdict(lambda: defaultdict(set))

    @staticmethod
    @lru_cache(maxsize=100000)
    def node(value, kind):
        return f'{kind}:{normalize(value, kind)}'

    def set_member(self, cid, identity, role, present=True):
        node = self.node(identity, 'entity')
        members = self.members[cid][role]
        if (node in members) == present:
            return
        if present:
            members.add(node)
        else:
            members.discard(node)
        self.dirty.add(cid)

    def apply_master(self, item, identity, previous=None, *, typed_bank=True, role=None):
        """A known master snapshot replaces or clears its previous identity slots."""
        cid = item['company_id']
        source = self.node(identity, 'entity')
        if previous and previous['company_id'] != cid:
            if role:
                self.set_member(previous['company_id'], identity, role, False)
            for kind in ('bank_account', 'phone', 'representative'):
                self.replace(previous['company_id'], source, '', item['recorded_at'], kind, master=True)
        if role:
            self.set_member(cid, identity, role)
        for field in ('bank_account', 'phone', 'representative_id'):
            if field == 'representative_id' and field not in item:
                continue
            kind = 'representative' if field == 'representative_id' else field
            token = bank_identity(item.get(field, ''), item.get('bank_code', '')) if typed_bank and field == 'bank_account' else item.get(field, '')
            right_kind = 'entity' if kind == 'representative' else kind
            target = self.node(token, right_kind) if normalize(token, right_kind) else ''
            self.replace(cid, source, target, item['recorded_at'], kind, master=True)

    def apply_link(self, edge, *, typed_bank=True):
        kind = edge['link_type']
        if kind not in {'bank_account', 'phone', 'representative'}:
            return
        status = edge.get('status', 'active') or 'active'
        if status not in {'active', 'revoked', 'deleted', 'inactive'}:
            raise ValueError(f'Invalid graph link status: {status}')
        right_kind = 'entity' if kind == 'representative' else kind
        token = bank_identity(edge['target_id'], edge.get('bank_code', '')) if typed_bank and kind == 'bank_account' else edge['target_id']
        right = self.node(token, right_kind) if normalize(token, right_kind) else ''
        source = self.node(edge['source_id'], 'entity')
        if status == 'active':
            self.replace(edge['company_id'], source, right, edge['observed_at'], kind)
        elif not edge['target_id'] or right:
            self.revoke(edge['company_id'], source, right, edge['observed_at'], kind)

    def replace(self, cid, left, right, at, kind, *, master=False):
        if not left or left.endswith(':'):
            return
        if right and right.endswith(':'):
            right = ''
        slot = (left, kind)
        previous = self.current[cid].get(slot)
        rank = (at, int(master))
        if previous:
            previous_rank, previous_edge = previous
            if rank < previous_rank:
                return
            if rank == previous_rank:
                if right != previous_edge['target']:
                    raise ValueError(f'Conflicting graph identity at {at}: {cid}/{left}/{kind}')
                return
        edge = dict(source=left, target=right, link_type=kind, observed_at=at)
        self.current[cid][slot] = (rank, edge)
        self.dirty.add(cid)

    def group(self, cid):
        # Union-find cannot split a component. Rebuild only after source changes,
        # after the entire observation batch, from the surviving current edges.
        if cid in self.dirty:
            group, adjacency = UnionFind(), defaultdict(dict)
            edges = sorted((edge for _, edge in self.current[cid].values()),
                           key=lambda e: (e['source'], e['link_type'], e['target'], e['observed_at']))
            for edge in edges:
                left, right = edge['source'], edge['target']
                if not right:
                    continue
                group.join(left, right)
                adjacency[left][right] = edge
                adjacency[right][left] = edge
            # Only current company members contribute counts. Retired slots may
            # retain tombstones, but never retain employee/vendor role counts.
            for node in self.members[cid]['employee']:
                group.employees[group.root(node)] += 1
            for node in self.members[cid]['vendor']:
                group.vendors[group.root(node)] += 1
            self.groups[cid], self.adjacency[cid] = group, adjacency
            members = defaultdict(list)
            for node in group.parent:
                if node.startswith('entity:'):
                    members[group.root(node)].append(node)
            self.identities[cid] = {root: (component_key(cid, nodes), tuple(sorted(nodes)))
                                    for root, nodes in members.items()}
            self.dirty.remove(cid)
        return self.groups[cid]

    def counts(self, cid, identity):
        group = self.group(cid)
        root = group.root(self.node(identity, 'entity'))
        return group.employees[root], group.vendors[root]

    def identity(self, cid, node):
        root = self.group(cid).root(node)
        if root not in self.identities[cid]:
            self.identities[cid][root] = component_key(cid, [node]), (node,)
        return self.identities[cid][root]

    def revoke(self, cid, left, right, at, kind):
        previous = self.current[cid].get((left, kind))
        # A cancellation naming an old value must not cancel its replacement.
        # An empty target explicitly clears the entire current identity slot.
        if right and previous and previous[1]['target'] not in {'', right}:
            return
        self.replace(cid, left, '', at, kind)

    def path(self, cid, start, targets, max_depth=6):
        self.group(cid)
        pending, seen = deque([(start, [])]), {start}
        while pending:
            node, path = pending.popleft()
            if node in targets and node != start:
                return path
            if len(path) >= max_depth:
                continue
            for other, edge in sorted(self.adjacency[cid][node].items()):
                if other not in seen:
                    seen.add(other)
                    pending.append((other, path + [edge]))
        return []


