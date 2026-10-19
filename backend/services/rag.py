"""本地知识库：切分 → 索引（BM25 + 字符 n-gram 向量）→ 混合检索 → 引用。

无需下载向量模型即可离线运行；若在「智能体配置」中填入 OpenAI 兼容的
embedding 模型，则自动额外写入真向量并在检索时融合。
"""
import json
import math
import re
import threading
import urllib.request
from collections import Counter

import jieba

from backend import db

MAX_CHUNK = 460
OVERLAP = 80
VEC_DIM = 1024

STOPWORDS = set(
    "的 了 和 与 及 或 是 在 有 对 为 以 于 中 上 下 也 都 而 及其 等 这 那 其 之 并 但 如果 因为 所以 可以 应 需要 进行 包括".split()
)

_HEAD_PATTERNS = [
    re.compile(r"^#{1,4}\s+"),
    re.compile(r"^[一二三四五六七八九十]+[、.]"),
    re.compile(r"^第[一二三四五六七八九十百]+[章节条]"),
    re.compile(r"^【.+】"),
    re.compile(r"^\d+(\.\d+)+\s"),
]

_index_lock = threading.Lock()
_index_cache = {"version": None, "chunks": [], "idf": {}, "avgdl": 1.0, "df": {}}


def _is_heading(line: str) -> bool:
    line = line.strip()
    if not line or len(line) > 40:
        return False
    return any(p.match(line) for p in _HEAD_PATTERNS)


def clean_heading(line: str) -> str:
    line = line.strip()
    line = re.sub(r"^#{1,4}\s+", "", line)
    return line.strip(" #【】")


def split_document(text: str):
    """标题感知切分，返回 [(heading, content), ...]。"""
    lines = [ln.rstrip() for ln in text.replace("\r\n", "\n").split("\n")]
    chunks = []
    heading = "概述"
    buf = []

    def flush(next_heading=None):
        nonlocal buf
        body = "\n".join(x for x in buf if x.strip()).strip()
        if body:
            # 超长段落二次切分
            if len(body) > MAX_CHUNK * 1.6:
                start = 0
                while start < len(body):
                    piece = body[start:start + MAX_CHUNK]
                    chunks.append((heading, piece.strip()))
                    start += MAX_CHUNK - OVERLAP
            else:
                chunks.append((heading, body))
        buf = []
        if next_heading:
            pass

    for ln in lines:
        if _is_heading(ln):
            flush()
            heading = clean_heading(ln)[:40] or heading
            buf.append(ln)
            continue
        buf.append(ln)
        cur_len = sum(len(x) for x in buf)
        if cur_len >= MAX_CHUNK:
            flush()
            # 重叠：保留尾部一段
            tail = "\n".join(buf[-2:])[-OVERLAP:]
            if tail.strip():
                buf = [tail]
    flush()

    merged = []
    for h, c in chunks:
        if len(c.strip()) < 20 and merged:
            merged[-1] = (merged[-1][0], merged[-1][1] + "\n" + c)
        else:
            merged.append((h, c))
    return merged


def tokenize(text: str):
    words = []
    for w in jieba.lcut(text):
        w = w.strip()
        if not w or w in STOPWORDS:
            continue
        if re.fullmatch(r"[\W_]+", w):
            continue
        words.append(w.lower())
    return words


def char_ngrams(text: str, n=2):
    text = re.sub(r"\s+", "", text.lower())
    grams = [text[i:i + n] for i in range(max(1, len(text) - n + 1))]
    grams += list(text)  # 单字补充，短查询更稳
    return grams


def _hash_vec(tokens, weights):
    vec = {}
    for t in tokens:
        h = hash(t) % VEC_DIM
        vec[h] = vec.get(h, 0.0) + weights.get(t, 1.0)
    norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
    return {k: v / norm for k, v in vec.items()}


def _cosine(a, b):
    if len(a) > len(b):
        a, b = b, a
    return sum(v * b.get(k, 0.0) for k, v in a.items())


def _build_index():
    chunks = db.query(
        """SELECT c.id, c.doc_id, c.idx, c.heading, c.content, c.vector_json,
                  d.title, d.category, d.doc_type, d.version
           FROM kb_chunks c JOIN kb_documents d ON d.id = c.doc_id
           WHERE d.status='ready'"""
    )
    df = Counter()
    tokenized = []
    for c in chunks:
        toks = tokenize(c["content"] + " " + (c["heading"] or ""))
        tokenized.append(toks)
        for t in set(toks):
            df[t] += 1
    total = max(1, len(chunks))
    idf = {t: math.log(1 + (total - n + 0.5) / (n + 0.5)) for t, n in df.items()}
    avgdl = sum(len(t) for t in tokenized) / total if tokenized else 1.0

    entries = []
    for c, toks in zip(chunks, tokenized):
        grams = char_ngrams(c["content"] + (c["heading"] or ""))
        vec = _hash_vec(grams, {})
        ext_vec = None
        if c["vector_json"]:
            try:
                ext_vec = json.loads(c["vector_json"])
            except Exception:
                ext_vec = None
        entries.append({
            "id": c["id"], "doc_id": c["doc_id"], "title": c["title"],
            "heading": c["heading"], "content": c["content"],
            "category": c["category"], "doc_type": c["doc_type"],
            "version": c["version"], "tokens": toks, "tf": Counter(toks),
            "vec": vec, "ext_vec": ext_vec, "len": len(toks),
        })
    _index_cache.update({"chunks": entries, "idf": idf, "avgdl": avgdl, "df": df,
                         "version": total})
    return entries


def ensure_index(force=False):
    with _index_lock:
        total = db.query("SELECT COUNT(*) c FROM kb_chunks", one=True)["c"]
        if force or _index_cache["version"] != total or not _index_cache["chunks"]:
            _build_index()
        return _index_cache


def invalidate():
    _index_cache["version"] = None


def _bm25(entry, q_tokens, idf, avgdl, k1=1.5, b=0.75):
    score = 0.0
    for t in q_tokens:
        f = entry["tf"].get(t)
        if not f:
            continue
        denom = f + k1 * (1 - b + b * entry["len"] / avgdl)
        score += idf.get(t, 0.0) * f * (k1 + 1) / denom
    return score


DISEASE_ALIASES = {
    "高血压": ["高血压", "血压", "降压"],
    "糖尿病": ["糖尿病", "血糖", "糖化", "胰岛素", "降糖"],
    "血脂异常": ["血脂", "胆固醇", "低密度脂蛋白", "他汀"],
    "慢性肾病": ["肾", "egfr", "肌酐", "尿蛋白"],
    "慢阻肺": ["慢阻肺", "copd", "肺功能", "呼吸困难"],
    "冠心病": ["冠心病", "心绞痛", "心梗", "抗血小板"],
}

# 病种类文档：若患者未患该病，则大幅降权，避免跨病种泛化建议
DISEASE_CATEGORY_MATCH = {
    "高血压": ["高血压"],
    "糖尿病": ["糖尿病"],
    "血脂异常": ["血脂"],
    "慢性肾病": ["肾"],
    "慢阻肺": ["慢阻肺", "COPD"],
    "冠心病": ["冠心病", "心梗", "支架"],
}


def search(query: str, patient=None, top_k=4, with_scores=True, doc_ids=None):
    """混合检索：BM25 + 字符向量余弦 + 病种/权威度加权。

    doc_ids 非空时只在这批文档内检索（专家会诊按绑定的知识库作答）。
    """
    idx = ensure_index()
    entries = idx["chunks"]
    if not entries:
        return []
    if doc_ids:
        allow = {int(x) for x in doc_ids}
        entries = [e for e in entries if e.get("doc_id") in allow]
        if not entries:
            return []

    q_tokens = tokenize(query)
    q_vec = _hash_vec(char_ngrams(query), {})
    bm_scores = [_bm25(e, q_tokens, idx["idf"], idx["avgdl"]) for e in entries]
    max_bm = max(bm_scores) or 1.0

    patient_conds = []
    if patient:
        patient_conds = [c["name"] for c in patient.get("conditions", [])]
    q_lower = query.lower()

    scored = []
    for e, bm in zip(entries, bm_scores):
        cos = _cosine(q_vec, e["vec"])
        score = 0.52 * (bm / max_bm) + 0.48 * cos

        # 病种匹配加权
        for cond in patient_conds:
            aliases = DISEASE_ALIASES.get(cond, [cond])
            if any(a in e["title"] or a in (e["heading"] or "") for a in aliases):
                score += 0.10
                break
        # 查询直接点名病种
        for cond, aliases in DISEASE_ALIASES.items():
            if any(a in q_lower for a in aliases):
                if any(a in e["title"] or a in (e["heading"] or "") for a in aliases):
                    score += 0.08
        # 指南类文档优先
        if e.get("doc_type") in ("guideline", "consensus"):
            score += 0.04
        # 跨病种降权：患者没有这个病，就不要拿这个病的专科指南当依据
        cat = e.get("category") or ""
        if patient and cat in DISEASE_CATEGORY_MATCH:
            cond_text = " ".join(patient_conds)
            matched_patient = any(k in cond_text for k in DISEASE_CATEGORY_MATCH[cat])
            asked = any(a in q_lower for a in DISEASE_ALIASES.get(cat, [cat]))
            if not matched_patient and not asked:
                continue
        # 标题命中
        for t in q_tokens:
            if len(t) >= 2 and t in e["title"]:
                score += 0.03
                break

        scored.append((round(min(0.99, score), 4), e))

    scored.sort(key=lambda x: x[0], reverse=True)
    results = []
    for s, e in scored[: max(top_k, 1) * 2]:
        if s < 0.12:
            continue
        results.append({
            "chunk_id": e["id"], "doc_id": e["doc_id"], "title": e["title"],
            "heading": e["heading"], "category": e["category"],
            "doc_type": e["doc_type"], "content": e["content"],
            "score": s if with_scores else None,
        })
        if len(results) >= top_k:
            break
    return results


def embed_texts(texts, cfg):
    """调用 OpenAI 兼容 embedding 接口；失败返回 None（自动回退本地向量）。"""
    model = (cfg or {}).get("embedding_model")
    if not model:
        return None
    base = (cfg.get("base_url") or "").rstrip("/")
    if not base:
        return None
    url = base + "/embeddings"
    try:
        body = json.dumps({"model": model, "input": texts}, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(url, data=body, method="POST")
        req.add_header("Content-Type", "application/json")
        if cfg.get("api_key"):
            req.add_header("Authorization", f"Bearer {cfg['api_key']}")
        with urllib.request.urlopen(req, timeout=30) as resp:
            obj = json.loads(resp.read().decode("utf-8", "ignore"))
        return [d["embedding"] for d in obj.get("data", [])]
    except Exception:
        return None


def ingest_document(title, content, category="综合管理", doc_type="guideline",
                    source="平台内置", version="2024", cfg=None):
    """写入文档 → 切分 → 可选向量化 → 重建索引。"""
    doc_id = db.execute(
        """INSERT INTO kb_documents(title,category,doc_type,source,version,content,status)
           VALUES(?,?,?,?,?,?,'ready')""",
        (title, category, doc_type, source, version, content),
    )
    parts = split_document(content)
    vectors = None
    if cfg and cfg.get("embedding_model"):
        vectors = embed_texts([c for _, c in parts], cfg)

    rows = []
    for i, (head, body) in enumerate(parts):
        vec = json.dumps(vectors[i]) if vectors and i < len(vectors) else None
        rows.append((doc_id, i, head, body, len(tokenize(body)), vec))
    if rows:
        db.executemany(
            "INSERT INTO kb_chunks(doc_id,idx,heading,content,tokens,vector_json) VALUES(?,?,?,?,?,?)",
            rows,
        )
    db.execute("UPDATE kb_documents SET chunk_count=? WHERE id=?", (len(rows), doc_id))
    invalidate()
    ensure_index(force=True)
    return doc_id, len(rows)


def rebuild_all(cfg=None):
    docs = db.query("SELECT * FROM kb_documents")
    db.execute("DELETE FROM kb_chunks")
    total = 0
    for d in docs:
        parts = split_document(d["content"] or "")
        vectors = embed_texts([c for _, c in parts], cfg) if cfg and cfg.get("embedding_model") else None
        rows = []
        for i, (head, body) in enumerate(parts):
            vec = json.dumps(vectors[i]) if vectors and i < len(vectors) else None
            rows.append((d["id"], i, head, body, len(tokenize(body)), vec))
        if rows:
            db.executemany(
                "INSERT INTO kb_chunks(doc_id,idx,heading,content,tokens,vector_json) VALUES(?,?,?,?,?,?)",
                rows,
            )
        total += len(rows)
        db.execute("UPDATE kb_documents SET chunk_count=? WHERE id=?", (len(rows), d["id"]))
    invalidate()
    ensure_index(force=True)
    return total


def kb_stats():
    docs = db.query("SELECT COUNT(*) c FROM kb_documents", one=True)["c"]
    chunks = db.query("SELECT COUNT(*) c FROM kb_chunks", one=True)["c"]
    cats = db.query(
        "SELECT category, COUNT(*) c FROM kb_documents GROUP BY category ORDER BY c DESC"
    )
    return {"documents": docs, "chunks": chunks, "categories": cats}
