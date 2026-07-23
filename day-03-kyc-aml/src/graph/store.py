"""
Knowledge-graph store.
  Production : Neo4j (Cypher).
  Fallback   : NetworkX DiGraph in-memory when NEO4J_URI is unset.

Both expose the same interface:
    add_node(label, key, props)
    add_edge(src_label, src_key, rel, dst_label, dst_key)
    customer_subgraph(customer_id)   → dict for the agent's GraphRAG context
    applicable_rules(country, ...)   → list of AML-rule dicts governing a customer

The customer_subgraph walk is the GraphRAG step: from one customer we collect the
documents, case, watchlist flags, country, and the AML rules + guidelines that
apply there — the relationship context a pure vector search cannot give.
"""
import logging

from src.config import config
from src.graph import schema as S

logger = logging.getLogger(__name__)


class GraphStore:
    def __init__(self) -> None:
        self.backend = "neo4j" if config.use_neo4j else "networkx"
        self._driver = None
        self._nx = None
        logger.info("Graph store backend: %s", self.backend)

    # ─── Neo4j ───
    def _neo4j(self):
        if self._driver is None:
            from neo4j import GraphDatabase
            self._driver = GraphDatabase.driver(
                config.neo4j_uri, auth=(config.neo4j_user, config.neo4j_password)
            )
            with self._driver.session() as sess:
                for label, key in S.CONSTRAINTS:
                    sess.run(
                        f"CREATE CONSTRAINT IF NOT EXISTS FOR (n:{label}) "
                        f"REQUIRE n.{key} IS UNIQUE"
                    )
        return self._driver

    # ─── NetworkX ───
    def _graph(self):
        if self._nx is None:
            import networkx as nx
            self._nx = nx.MultiDiGraph()
        return self._nx

    @staticmethod
    def _nx_id(label: str, key: str) -> str:
        return f"{label}:{key}"

    # ─── writes ───
    def add_node(self, label: str, key_prop: str, key_val: str, props: dict) -> None:
        if not key_val:
            return
        if self.backend == "neo4j":
            with self._neo4j().session() as sess:
                sess.run(
                    f"MERGE (n:{label} {{{key_prop}: $key}}) SET n += $props",
                    key=key_val, props=props,
                )
        else:
            g = self._graph()
            nid = self._nx_id(label, key_val)
            g.add_node(nid, label=label, key=key_val, **props)

    def add_edge(self, src_label, src_key, rel, dst_label, dst_key) -> None:
        if not (src_key and dst_key):
            return
        if self.backend == "neo4j":
            with self._neo4j().session() as sess:
                sess.run(
                    f"MATCH (a:{src_label} {{{self._key_of(src_label)}: $s}}) "
                    f"MATCH (b:{dst_label} {{{self._key_of(dst_label)}: $d}}) "
                    f"MERGE (a)-[:{rel}]->(b)",
                    s=src_key, d=dst_key,
                )
        else:
            g = self._graph()
            a, b = self._nx_id(src_label, src_key), self._nx_id(dst_label, dst_key)
            if a in g and b in g:
                g.add_edge(a, b, key=rel, rel=rel)

    def bulk_upsert_nodes(self, label: str, key_prop: str, rows: list[dict]) -> None:
        """Batch-create nodes of one label. rows = [{'key':..., 'props':{...}}].
        One Cypher round-trip per batch via UNWIND instead of one per node."""
        if not rows:
            return
        if self.backend == "neo4j":
            with self._neo4j().session() as sess:
                sess.run(
                    f"UNWIND $rows AS row "
                    f"MERGE (n:{label} {{{key_prop}: row.key}}) SET n += row.props",
                    rows=rows,
                )
        else:
            g = self._graph()
            for r in rows:
                if not r["key"]:
                    continue
                g.add_node(self._nx_id(label, r["key"]), label=label, key=r["key"], **r["props"])

    def bulk_upsert_edges(self, src_label, rel, dst_label, pairs: list[tuple]) -> None:
        """Batch-create edges. pairs = [(src_key, dst_key), ...]."""
        if not pairs:
            return
        if self.backend == "neo4j":
            rows = [{"s": s, "d": d} for s, d in pairs if s and d]
            with self._neo4j().session() as sess:
                sess.run(
                    f"UNWIND $rows AS row "
                    f"MATCH (a:{src_label} {{{self._key_of(src_label)}: row.s}}) "
                    f"MATCH (b:{dst_label} {{{self._key_of(dst_label)}: row.d}}) "
                    f"MERGE (a)-[:{rel}]->(b)",
                    rows=rows,
                )
        else:
            g = self._graph()
            for s, d in pairs:
                a, b = self._nx_id(src_label, s), self._nx_id(dst_label, d)
                if a in g and b in g:
                    g.add_edge(a, b, key=rel, rel=rel)

    @staticmethod
    def _key_of(label: str) -> str:
        for lbl, key in S.CONSTRAINTS:
            if lbl == label:
                return key
        return "name"

    # ─── GraphRAG reads ───
    def customer_subgraph(self, customer_id: str) -> dict:
        if self.backend == "neo4j":
            return self._customer_subgraph_neo4j(customer_id)
        return self._customer_subgraph_nx(customer_id)

    def _customer_subgraph_neo4j(self, customer_id: str) -> dict:
        cypher = """
        MATCH (c:Customer {customer_id: $cid})
        OPTIONAL MATCH (c)-[:HAS_DOCUMENT]->(d:Document)
        OPTIONAL MATCH (c)-[:HAS_CASE]->(k:KYCCase)
        OPTIONAL MATCH (c)-[:FLAGGED_AS]->(w:Watchlist)
        OPTIONAL MATCH (c)-[:RESIDENT_OF]->(co:Country)
        OPTIONAL MATCH (r:AMLRule)-[:APPLIES_IN]->(rco:Country)
          WHERE rco = co OR rco.name = 'Global'
        OPTIONAL MATCH (g:Guideline)-[:IMPLEMENTS]->(r)
        RETURN c AS customer,
               collect(DISTINCT d) AS documents,
               collect(DISTINCT k) AS cases,
               collect(DISTINCT w.name) AS watchlists,
               collect(DISTINCT co.name) AS countries,
               collect(DISTINCT r) AS rules,
               collect(DISTINCT g) AS guidelines
        """
        with self._neo4j().session() as sess:
            rec = sess.run(cypher, cid=customer_id).single()
        if not rec or not rec["customer"]:
            return {}
        return {
            "customer": dict(rec["customer"]),
            "documents": [dict(d) for d in rec["documents"] if d],
            "cases": [dict(k) for k in rec["cases"] if k],
            "watchlists": [w for w in rec["watchlists"] if w],
            "countries": [c for c in rec["countries"] if c],
            "rules": [dict(r) for r in rec["rules"] if r],
            "guidelines": [dict(g) for g in rec["guidelines"] if g],
        }

    def _customer_subgraph_nx(self, customer_id: str) -> dict:
        g = self._graph()
        cid = self._nx_id(S.CUSTOMER, customer_id)
        if cid not in g:
            return {}
        out = {"customer": {k: v for k, v in g.nodes[cid].items()},
               "documents": [], "cases": [], "watchlists": [],
               "countries": [], "rules": [], "guidelines": []}
        countries = []
        for _, dst, data in g.out_edges(cid, data=True):
            node = g.nodes[dst]
            rel = data.get("rel")
            if rel == S.HAS_DOCUMENT:
                out["documents"].append(dict(node))
            elif rel == S.HAS_CASE:
                out["cases"].append(dict(node))
            elif rel == S.FLAGGED_AS:
                out["watchlists"].append(node.get("key"))
            elif rel == S.RESIDENT_OF:
                out["countries"].append(node.get("key"))
                countries.append(dst)
        # Country ← APPLIES_IN ← AMLRule ← IMPLEMENTS ← Guideline.
        # Include the resident country's rules plus the 'Global' rule set.
        global_node = self._nx_id(S.COUNTRY, "Global")
        if global_node in g:
            countries = countries + [global_node]
        seen_rules: set[str] = set()
        for co in countries:
            for src, _, data in g.in_edges(co, data=True):
                if data.get("rel") != S.APPLIES_IN or src in seen_rules:
                    continue
                seen_rules.add(src)
                out["rules"].append(dict(g.nodes[src]))
                for gsrc, _, gdata in g.in_edges(src, data=True):
                    if gdata.get("rel") == S.IMPLEMENTS:
                        out["guidelines"].append(dict(g.nodes[gsrc]))
        return out

    def applicable_rules(self, country: str, limit: int = 20) -> list[dict]:
        """AML rules that apply in a country (plus 'Global' rules)."""
        if self.backend == "neo4j":
            cypher = """
            MATCH (r:AMLRule)-[:APPLIES_IN]->(co:Country)
            WHERE co.name = $country OR co.name = 'Global'
            RETURN DISTINCT r AS rule LIMIT $limit
            """
            with self._neo4j().session() as sess:
                return [dict(rec["rule"]) for rec in sess.run(cypher, country=country, limit=limit)]
        g = self._graph()
        out = []
        for target in (country, "Global"):
            cnode = self._nx_id(S.COUNTRY, target)
            if cnode not in g:
                continue
            for src, _, data in g.in_edges(cnode, data=True):
                if data.get("rel") == S.APPLIES_IN:
                    out.append(dict(g.nodes[src]))
                    if len(out) >= limit:
                        return out
        return out

    def stats(self) -> dict:
        if self.backend == "neo4j":
            with self._neo4j().session() as sess:
                nodes = sess.run("MATCH (n) RETURN count(n) AS c").single()["c"]
                edges = sess.run("MATCH ()-[r]->() RETURN count(r) AS c").single()["c"]
            return {"backend": "neo4j", "nodes": nodes, "edges": edges}
        g = self._graph()
        return {"backend": "networkx", "nodes": g.number_of_nodes(), "edges": g.number_of_edges()}

    def close(self) -> None:
        if self._driver is not None:
            self._driver.close()
            self._driver = None


graph_store = GraphStore()
