"""本地知识库管理。"""
import io
import os

from flask import Blueprint, jsonify, request

from backend import db
from backend.api.auth import current_user, login_required
from backend.services import rag

bp = Blueprint("kb", __name__)

ALLOWED = ("txt", "md", "markdown", "pdf")


@bp.get("/kb/documents")
@login_required
def documents():
    q = request.args.get("q", "").strip()
    cat = request.args.get("category", "").strip()
    sql = "SELECT id,title,category,doc_type,source,version,chunk_count,status,created_at," \
          "length(content) AS size FROM kb_documents WHERE 1=1"
    args = []
    if q:
        sql += " AND (title LIKE ? OR content LIKE ?)"
        args += [f"%{q}%", f"%{q}%"]
    if cat:
        sql += " AND category=?"
        args.append(cat)
    sql += " ORDER BY id"
    rows = db.query(sql, args)
    return jsonify({"ok": True, "data": {"items": rows, "stats": rag.kb_stats()}})


@bp.get("/kb/documents/<int:did>")
@login_required
def document_detail(did):
    doc = db.query("SELECT * FROM kb_documents WHERE id=?", (did,), one=True)
    if not doc:
        return jsonify({"ok": False, "error": "文档不存在"}), 404
    chunks = db.query(
        "SELECT id,idx,heading,content,tokens FROM kb_chunks WHERE doc_id=? ORDER BY idx", (did,))
    doc["chunks"] = chunks
    return jsonify({"ok": True, "data": doc})


@bp.post("/kb/documents")
@login_required
def upload_document():
    cfg = db.get_agent_config()
    payload = request.get_json(silent=True) if request.is_json else None
    src = payload if payload is not None else request.form
    title = src.get("title")
    content = src.get("content")
    category = src.get("category") or "综合管理"
    doc_type = src.get("doc_type") or "guideline"
    source = src.get("source") or "本地上传"
    version = src.get("version") or "2025"

    file = request.files.get("file") if not request.is_json else None
    if file and file.filename:
        ext = file.filename.rsplit(".", 1)[-1].lower()
        if ext not in ALLOWED:
            return jsonify({"ok": False, "error": "仅支持 txt / md / pdf 文件"}), 400
        raw = file.read()
        if ext == "pdf":
            try:
                from pypdf import PdfReader
                reader = PdfReader(io.BytesIO(raw))
                content = "\n".join((p.extract_text() or "") for p in reader.pages)
            except Exception as e:
                return jsonify({"ok": False, "error": f"PDF 解析失败：{e}"}), 400
        else:
            content = raw.decode("utf-8", "ignore")
        title = title or os.path.splitext(file.filename)[0]

    if not title or not content or len(content.strip()) < 30:
        return jsonify({"ok": False, "error": "标题与正文不能为空（正文至少 30 字）"}), 400

    did, n = rag.ingest_document(title, content, category, doc_type, source, version, cfg)
    db.audit(current_user()["name"], "kb_upload", f"doc:{did}", f"{title}（{n} 片段）")
    return jsonify({"ok": True, "data": {"id": did, "chunks": n}})


@bp.delete("/kb/documents/<int:did>")
@login_required
def delete_document(did):
    db.execute("DELETE FROM kb_chunks WHERE doc_id=?", (did,))
    db.execute("DELETE FROM kb_documents WHERE id=?", (did,))
    rag.invalidate()
    rag.ensure_index(force=True)
    db.audit(current_user()["name"], "kb_delete", f"doc:{did}", "")
    return jsonify({"ok": True})


@bp.post("/kb/search")
@login_required
def search():
    data = request.get_json(silent=True) or {}
    query = (data.get("query") or "").strip()
    if not query:
        return jsonify({"ok": False, "error": "请输入检索内容"}), 400
    pid = data.get("patient_id")
    patient = None
    if pid:
        from backend.services import agent
        patient = agent.load_patient(int(pid))
    results = rag.search(query, patient=patient, top_k=int(data.get("top_k", 6)))
    db.execute(
        "INSERT INTO kb_query_log(patient_id,query,hits_json,top_score) VALUES(?,?,?,?)",
        (pid, query, ",".join(str(r["chunk_id"]) for r in results),
         results[0]["score"] if results else 0))
    return jsonify({"ok": True, "data": {"results": results, "query": query}})


@bp.post("/kb/rebuild")
@login_required
def rebuild():
    n = rag.rebuild_all(db.get_agent_config())
    db.audit(current_user()["name"], "kb_rebuild", "", f"{n} 片段")
    return jsonify({"ok": True, "data": {"chunks": n}})


@bp.get("/kb/stats")
@login_required
def stats():
    idx = rag.ensure_index()
    return jsonify({"ok": True, "data": {
        "stats": rag.kb_stats(),
        "indexed": len(idx["chunks"]),
        "avg_length": round(idx["avgdl"], 1),
        "vocabulary": len(idx["idf"]),
        "queries": db.query("SELECT COUNT(*) c FROM kb_query_log", one=True)["c"],
    }})
