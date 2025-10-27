# app/services/retriever.py
from __future__ import annotations
from typing import List, Dict, Any, Tuple, Optional
import math, re, json
from collections import Counter, defaultdict

TOKEN_RX = re.compile(r"[A-Za-z0-9][A-Za-z0-9\-]{1,}")

STANDARD_ALIASES = {
    "soc2": {"soc2", "soc 2", "soc 2 tsc", "trust services", "tsc"},
    "nist sp 800 53 rev5": {"nist sp 800-53", "nist sp 800-53 rev.5", "nist sp 800 53 rev5", "nist 800-53", "nist 800 53", "nist sp 800-53 rev5"},
    "iso iec 27001 2022": {"iso27001", "iso/iec 27001:2022", "iso 27001 2022", "iso 27001"},
    "pci dss v4 0 1": {"pci", "pci dss", "pci dss v4.0", "pci dss v4.0.1"},
}

SOC2_CTRL_RX = re.compile(r"\bCC\d+(?:\.\d+)?\b", re.I)

def normalize_standard(s: str) -> str:
    if not s:
        return ""
    base = re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()
    for canon, alset in STANDARD_ALIASES.items():
        if base in alset or any(base == re.sub(r"[^a-z0-9]+", " ", a.lower()).strip() for a in alset):
            return canon
    return base

def tokenize(text: str) -> List[str]:
    if not text:
        return []
    return [t.lower() for t in TOKEN_RX.findall(text)]

def _parse_meta(d: Dict[str, Any]) -> Dict[str, Any]:
    md = d.get("metadata")
    if isinstance(md, dict):
        return md
    if isinstance(md, str):
        try:
            return json.loads(md)
        except Exception:
            return {}
    return {}

def doc_text(d: Dict[str, Any]) -> str:
    md = _parse_meta(d)
    extra = []
    for k in ("standard", "families", "controls", "tags", "manual_tags", "doc_type"):
        v = md.get(k)
        if isinstance(v, list):
            extra.extend(v)
        elif isinstance(v, str):
            extra.append(v)
    return f"{d.get('title','')} \n{d.get('text','')} \n{' '.join(map(str, extra))}"

def _standard_matches(d: Dict[str, Any], standard: Optional[str]) -> bool:
    if not standard:
        return True
    md = _parse_meta(d)
    s = md.get("standard", "")
    want = normalize_standard(standard)
    vals = " ".join(s) if isinstance(s, list) else str(s)
    have = normalize_standard(vals)
    return bool(want) and (want in have)

def _doc_type(d: Dict[str, Any]) -> str:
    md = _parse_meta(d)
    return str(md.get("doc_type", "")).upper().strip()

def _soc2_ids_from(tags: Optional[List[str]], query: str) -> List[str]:
    ids: List[str] = []
    if tags:
        ids.extend(t for t in tags if SOC2_CTRL_RX.match(t or ""))
    ids.extend(SOC2_CTRL_RX.findall(query or ""))
    ids = [x.upper() for x in ids]
    out, seen = [], set()
    for x in ids:
        if x not in seen:
            out.append(x); seen.add(x)
    return out

def _control_present(d: Dict[str, Any], ids: List[str]) -> bool:
    if not ids:
        return True
    md = _parse_meta(d)
    controls = {str(c).upper() for c in md.get("controls", [])} if isinstance(md.get("controls"), list) else set()
    if any(c in controls for c in ids):
        return True
    txt = (d.get("title","") + " " + d.get("text","")).upper()
    return any(c in txt for c in ids)

class _Index:
    def __init__(self, docs: List[Dict[str, Any]]):
        self.docs = docs
        self.N = len(docs)
        self.term_df: Dict[str, int] = defaultdict(int)
        self.doc_tf: List[Counter] = []
        self.doc_len: List[int] = []
        for d in docs:
            toks = tokenize(doc_text(d))
            tf = Counter(toks)
            self.doc_tf.append(tf)
            self.doc_len.append(sum(tf.values()))
            for term in tf.keys():
                self.term_df[term] += 1
        self.avgdl = (sum(self.doc_len)/self.N) if self.N else 0.0

    def idf_bm25(self, term: str) -> float:
        n = self.term_df.get(term, 0)
        if n == 0:
            return 0.0
        return math.log((self.N - n + 0.5) / (n + 0.5) + 1)

    def idf_tfidf(self, term: str) -> float:
        n = self.term_df.get(term, 0)
        if n == 0:
            return 0.0
        return math.log(1 + self.N / n)

    def score_bm25(self, q_toks: List[str], k1: float = 1.2, b: float = 0.75) -> List[float]:
        scores = [0.0] * self.N
        q_terms = set(q_toks)
        for i in range(self.N):
            dl = self.doc_len[i] or 1
            tf = self.doc_tf[i]
            s = 0.0
            for t in q_terms:
                f = tf.get(t, 0)
                if f == 0:
                    continue
                idf = self.idf_bm25(t)
                denom = f + k1 * (1 - b + b * dl / (self.avgdl or 1))
                s += idf * (f * (k1 + 1)) / denom
            scores[i] = s
        return scores

    def score_tfidf_cosine(self, q_toks: List[str]) -> List[float]:
        q_tf = Counter(q_toks)
        q_vec: Dict[str, float] = {}
        for t, f in q_tf.items():
            idf = self.idf_tfidf(t)
            q_vec[t] = (1 + math.log(f)) * idf if f > 0 and idf > 0 else 0.0
        q_norm = math.sqrt(sum(v*v for v in q_vec.values())) or 1.0

        scores = [0.0] * self.N
        for i in range(self.N):
            tf = self.doc_tf[i]
            dot = 0.0
            d_norm_sq = 0.0
            for t, f in tf.items():
                idf = self.idf_tfidf(t)
                w = (1 + math.log(f)) * idf if f > 0 and idf > 0 else 0.0
                d_norm_sq += w*w
                if t in q_vec:
                    dot += q_vec[t] * w
            d_norm = math.sqrt(d_norm_sq) or 1.0
            scores[i] = dot / (q_norm * d_norm)
        return scores

def _normalize(xs: List[float]) -> List[float]:
    if not xs:
        return xs
    lo, hi = min(xs), max(xs)
    if hi - lo < 1e-12:
        return [0.0]*len(xs)
    return [(x - lo) / (hi - lo) for x in xs]

def _hybrid(scores_a: List[float], scores_b: List[float], w: float) -> List[float]:
    A, B = _normalize(scores_a), _normalize(scores_b)
    return [w*a + (1.0 - w)*b for a, b in zip(A, B)]

def _bigram_overlap(q: str, t: str) -> float:
    def bigrams(s: str) -> set:
        toks = tokenize(s)
        return set(zip(toks, toks[1:])) if len(toks) >= 2 else set()
    q_bi, t_bi = bigrams(q), bigrams(t)
    if not q_bi or not t_bi:
        return 0.0
    inter = len(q_bi & t_bi)
    return inter / (len(q_bi) + 1e-9)

def _tag_bonus(
    d: Dict[str, Any],
    standard: Optional[str],
    tags: Optional[List[str]],
    q_ctrls: List[str],
    include_company: bool,
) -> float:
    md = _parse_meta(d)
    bonus = 0.0
    if tags:
        lt = [t.lower() for t in tags if t.strip()]
        m = [t.lower() for t in md.get("manual_tags", [])] if isinstance(md.get("manual_tags"), list) else []
        if m and any(t in m for t in lt):
            bonus += 0.50
        for key, w in (("controls", 0.35), ("families", 0.25), ("tags", 0.20)):
            vals = md.get(key, [])
            if isinstance(vals, list):
                vl = [str(v).lower() for v in vals]
                if any(t in vl for t in lt):
                    bonus += w
    if standard and _standard_matches(d, standard):
        bonus += 0.25
    if q_ctrls and _control_present(d, q_ctrls):
        bonus += 0.40
    # nudge company evidence when requested so it shows up in top-K
    if include_company and _doc_type(d) == "COMPANY":
        bonus += 0.15
    return min(bonus, 1.6)

def _rank(
    docs: List[Dict[str, Any]],
    base_scores: List[float],
    topk: int,
    query: str,
    standard: Optional[str],
    tags: Optional[List[str]],
    q_ctrls: List[str],
    include_company: bool,
) -> List[Dict[str, Any]]:
    prox = []
    for i, d in enumerate(docs):
        prox.append(_bigram_overlap(query, doc_text(d)) + _tag_bonus(d, standard, tags, q_ctrls, include_company))
    P = _normalize(prox)
    H = _normalize(base_scores)
    final = [0.65*h + 0.35*p for h, p in zip(H, P)]

    idxs = list(range(len(docs)))
    idxs.sort(key=lambda i: final[i], reverse=True)
    idxs = idxs[:max(topk*3, topk)]
    out = []
    for i in idxs[:topk]:
        di = dict(docs[i])
        di["_score"] = float(final[i])
        out.append(di)
    return out

class HybridRetriever:
    def __init__(self, store: Any):
        self.store = store
        self._cache = {"pol_v": -1, "pol_index": None, "ev_v": -1, "ev_index": None}

    def _memory_all(self, kind: str) -> Tuple[List[Dict[str, Any]], int]:
        docs = getattr(self.store, "policies" if kind == "policy" else "evidence", [])
        ver = getattr(self.store, "version", 0)
        return docs, ver

    def _ensure_index(self, kind: str):
        try:
            from app.services.weaviate_store import WeaviateStore  # type: ignore
            if isinstance(self.store, WeaviateStore):
                return
        except Exception:
            pass
        docs, ver = self._memory_all(kind)
        key = "pol_index" if kind == "policy" else "ev_index"
        vkey = "pol_v" if kind == "policy" else "ev_v"
        if self._cache[key] is None or self._cache[vkey] != ver:
            self._cache[key] = _Index(docs)
            self._cache[vkey] = ver

    # ---- filtering helpers ----
    def _apply_filters(
        self,
        docs: List[Dict[str, Any]],
        standard: Optional[str],
        strict_standard: bool,
        include_company: bool,
        q_ctrls: List[str],
    ) -> List[Dict[str, Any]]:
        """
        Standard/company gating:
          - If strict & standard: keep STANDARD that match the standard; keep COMPANY iff include_company.
        SOC2 control-ID gating:
          - If SOC2 and q_ctrls present: REQUIRE control IDs for STANDARD docs only,
            but ALWAYS retain COMPANY docs (when include_company=True).
        """
        if not docs:
            return docs

        # First, standard/company gating
        if strict_standard and standard:
            tmp: List[Dict[str, Any]] = []
            for d in docs:
                dtype = _doc_type(d)
                if dtype == "COMPANY":
                    if include_company:
                        tmp.append(d)
                else:
                    if _standard_matches(d, standard):
                        tmp.append(d)
            docs = tmp

        if not docs or not (standard and normalize_standard(standard) == "soc2" and q_ctrls):
            return docs

        # Control-ID gating for STANDARD docs only
        std_kept = [d for d in docs if _doc_type(d) != "COMPANY"]
        comp_kept = [d for d in docs if _doc_type(d) == "COMPANY"]

        std_ctrl = [d for d in std_kept if _control_present(d, q_ctrls)]
        # If we found any matching STANDARD chunks, use them + all COMPANY (if any)
        if std_ctrl:
            return std_ctrl + comp_kept

        # Otherwise, fall back to original list (don’t drop company evidence)
        return docs

    # ---- searches ----
    def _search_memory(self, query: str, topk: int, kind: str,
                       frameworks: Optional[List[str]], standard: Optional[str],
                       tags: Optional[List[str]], strict_standard: bool,
                       include_company: bool, q_ctrls: List[str]):
        self._ensure_index(kind)
        idx: _Index = self._cache["pol_index"] if kind == "policy" else self._cache["ev_index"]
        if idx is None or idx.N == 0:
            return []

        docs = self._apply_filters(idx.docs, standard, strict_standard, include_company, q_ctrls)
        if not docs:
            return []

        temp_idx = _Index(docs)
        q_toks = tokenize(query)
        bm25 = temp_idx.score_bm25(q_toks)
        tfidf = temp_idx.score_tfidf_cosine(q_toks)
        base = _hybrid(bm25, tfidf, w=0.6)

        if kind == "policy" and frameworks:
            fset = {f.lower() for f in frameworks}
            base = [s if docs[i].get("framework","").lower() in fset else -1.0 for i, s in enumerate(base)]

        return _rank(docs, base, topk, query, standard, tags, q_ctrls, include_company)

    def _search_weaviate(self, query: str, topk: int, kind: str,
                         frameworks: Optional[List[str]], standard: Optional[str],
                         tags: Optional[List[str]], strict_standard: bool,
                         include_company: bool, q_ctrls: List[str]):
        if kind == "policy":
            cands = self.store.search_policies(query, limit=max(64, topk), frameworks=frameworks)
        else:
            cands = self.store.search_evidence(query, limit=max(64, topk))
        cands = self._apply_filters(cands, standard, strict_standard, include_company, q_ctrls)
        if not cands:
            return []
        idx = _Index(cands)
        q_toks = tokenize(query)
        bm25 = idx.score_bm25(q_toks)
        tfidf = idx.score_tfidf_cosine(q_toks)
        base = _hybrid(bm25, tfidf, w=0.6)
        return _rank(cands, base, topk, query, standard, tags, q_ctrls, include_company)

    def search(self, query: str, frameworks: Optional[List[str]], k_policies: int, k_evidence: int,
               standard: Optional[str], tags: Optional[List[str]],
               strict_standard: bool = True, include_company: bool = False):
        q_ctrls = _soc2_ids_from(tags, query)

        try:
            from app.services.weaviate_store import WeaviateStore  # type: ignore
            is_weav = isinstance(self.store, WeaviateStore)
        except Exception:
            is_weav = False

        if is_weav:
            pol = self._search_weaviate(query, k_policies, "policy", frameworks, standard, tags,
                                        strict_standard, include_company, q_ctrls)
        else:
            pol = self._search_memory(query, k_policies, "policy", frameworks, standard, tags,
                                      strict_standard, include_company, q_ctrls)

        # Evidence — balanced when include_company=True (no change to your previous logic)
        if include_company and strict_standard and standard:
            if is_weav:
                std_only = self._search_weaviate(query, max(8, k_evidence), "evidence", None, standard, tags, True, False, q_ctrls)
                both = self._search_weaviate(query, max(8, k_evidence), "evidence", None, standard, tags, True, True, q_ctrls)
            else:
                std_only = self._search_memory(query, max(8, k_evidence), "evidence", None, standard, tags, True, False, q_ctrls)
                both = self._search_memory(query, max(8, k_evidence), "evidence", None, standard, tags, True, True, q_ctrls)

            comp_only = [d for d in both if _doc_type(d) == "COMPANY"]

            n_std = max(1, k_evidence // 2)
            n_comp = max(1, k_evidence - n_std)
            evd = std_only[:n_std] + comp_only[:n_comp]
            if len(evd) < k_evidence:
                pool = std_only + comp_only
                seen = {id(obj) for obj in evd}
                for d in pool:
                    if id(d) in seen:
                        continue
                    evd.append(d)
                    if len(evd) >= k_evidence:
                        break
        else:
            if is_weav:
                evd = self._search_weaviate(query, k_evidence, "evidence", None, standard, tags,
                                            strict_standard, include_company, q_ctrls)
            else:
                evd = self._search_memory(query, k_evidence, "evidence", None, standard, tags,
                                          strict_standard, include_company, q_ctrls)

        return pol, evd
