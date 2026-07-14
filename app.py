from dotenv import load_dotenv
load_dotenv()

from flask import Flask, render_template, request, jsonify, redirect, send_file, Response
import os, json
from werkzeug.exceptions import HTTPException

from db.database import init_db, get_db
from agents import document_agent, summarizer_agent, quiz_agent, qa_agent, study_plan_agent
from agents.orchestrator import route
from fpdf import FPDF
import tempfile
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY")
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs("db", exist_ok=True)

init_db()

def log_activity(action_type, description):
    try:
        conn = get_db()
        conn.execute("INSERT INTO activity_log (action_type, description) VALUES (?, ?)", (action_type, description))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Failed to log activity: {e}")

@app.route("/")
def index():
    conn = get_db()
    docs = conn.execute("SELECT * FROM documents ORDER BY uploaded_at DESC").fetchall()
    conn.close()
    return render_template("index.html", documents=docs)

@app.route("/upload", methods=["POST"])
def upload():
    try:
        file = request.files.get("file")
        if not file or not file.filename:
            return redirect("/")
            
        filepath = os.path.join(UPLOAD_FOLDER, file.filename)
        file.save(filepath)

        text = document_agent.extract_text(filepath)
        if not text or not text.strip():
            conn = get_db()
            docs = conn.execute("SELECT * FROM documents ORDER BY uploaded_at DESC").fetchall()
            conn.close()
            return render_template("index.html", documents=docs, error="Could not extract text. File might be empty or unsupported.")

        chunks = document_agent.chunk_text(text)

        conn = get_db()
        cur = conn.execute("INSERT INTO documents (filename, raw_text) VALUES (?, ?)",
                            (file.filename, text))
        doc_id = cur.lastrowid
        try:
            embeddings = qa_agent.embed_batch(chunks)
        except Exception as e:
            print(f"Batch embedding failed: {e}")
            embeddings = [None] * len(chunks)

        for i, (chunk, emb) in enumerate(zip(chunks, embeddings)):
            emb_str = json.dumps(emb) if emb else None
            conn.execute("INSERT INTO chunks (document_id, chunk_text, chunk_index, embedding) VALUES (?, ?, ?, ?)",
                          (doc_id, chunk, i, emb_str))
        conn.commit()
        conn.close()
        log_activity("upload", f"Uploaded document: {file.filename}")
        return redirect(f"/document/{doc_id}")
    except Exception as e:
        print(f"Upload exception: {e}")
        conn = get_db()
        docs = conn.execute("SELECT * FROM documents ORDER BY uploaded_at DESC").fetchall()
        conn.close()
        return render_template("index.html", documents=docs, error=f"An error occurred: {str(e)}")

@app.route("/document/<int:doc_id>")
def document_view(doc_id):
    conn = get_db()
    doc = conn.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()
    conn.close()
    if not doc:
        return redirect("/")
    return render_template("document.html", document=doc)

@app.route("/api/summarize/<int:doc_id>")
def api_summarize(doc_id):
    conn = get_db()
    doc = conn.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()
    if not doc:
        conn.close()
        return jsonify({"summary": "Document not found. It may have been cleared by the server."})
    summary = summarizer_agent.summarize(doc["raw_text"])
    conn.execute("INSERT INTO summaries (document_id, summary_text) VALUES (?, ?)",
                 (doc_id, summary))
    conn.commit()
    conn.close()
    return jsonify({"summary": summary})

@app.route("/api/quiz/<int:doc_id>")
def api_quiz(doc_id):
    # Adaptive Difficulty Logic
    conn = get_db()
    attempts = conn.execute("SELECT score, total_questions FROM quiz_attempts WHERE document_id=?", (doc_id,)).fetchall()
    
    if attempts:
        avg_score = sum([a["score"] / a["total_questions"] for a in attempts]) / len(attempts)
        if avg_score >= 0.8:
            difficulty = "hard"
        elif avg_score <= 0.5:
            difficulty = "easy"
        else:
            difficulty = "medium"
    else:
        difficulty = request.args.get("difficulty", "medium")
        
    doc = conn.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()
    if not doc:
        conn.close()
        return jsonify([])

    num_questions = int(request.args.get("num_questions", 5))
    quiz = quiz_agent.generate_quiz(doc["raw_text"], num_questions=num_questions, difficulty=difficulty)
    for q in quiz:
        conn.execute("""INSERT INTO quizzes (document_id, question, options, correct_answer, difficulty)
                         VALUES (?, ?, ?, ?, ?)""",
                     (doc_id, q["question"], json.dumps(q["options"]), q["correct_answer"], difficulty))
    conn.commit()
    conn.close()
    return jsonify(quiz)

@app.route("/api/ask/<int:doc_id>", methods=["POST"])
def api_ask(doc_id):
    question = request.json["question"]
    conn = get_db()
    rows = conn.execute(
        "SELECT c.chunk_text, c.chunk_index, c.embedding, d.filename FROM chunks c JOIN documents d ON c.document_id = d.id WHERE c.document_id=?", 
        (doc_id,)).fetchall()
    conn.close()

    chunks_with_info = []
    for r in rows:
        chunks_with_info.append({
            "chunk_text": r["chunk_text"],
            "chunk_index": r["chunk_index"],
            "embedding": json.loads(r["embedding"]) if r["embedding"] else None,
            "filename": r["filename"]
        })

    relevant = qa_agent.retrieve_relevant_chunks(question, chunks_with_info)
    
    def generate():
        full_response = []
        for text in qa_agent.answer_question_stream(question, relevant):
            full_response.append(text)
            yield text
            
        # Log to DB after stream finishes
        conn_db = get_db()
        conn_db.execute("INSERT INTO chat_history (document_id, question, answer) VALUES (?, ?, ?)",
                        (doc_id, question, "".join(full_response)))
        conn_db.commit()
        conn_db.close()

    return Response(generate(), mimetype='text/plain')

@app.route("/api/ask-all", methods=["POST"])
def api_ask_all():
    question = request.json["question"]
    conn = get_db()
    rows = conn.execute(
        "SELECT c.chunk_text, c.chunk_index, c.embedding, d.filename FROM chunks c JOIN documents d ON c.document_id = d.id"
    ).fetchall()
    conn.close()

    chunks_with_info = []
    for r in rows:
        chunks_with_info.append({
            "chunk_text": r["chunk_text"],
            "chunk_index": r["chunk_index"],
            "embedding": json.loads(r["embedding"]) if r["embedding"] else None,
            "filename": r["filename"]
        })

    relevant = qa_agent.retrieve_relevant_chunks(question, chunks_with_info)
    
    def generate():
        for text in qa_agent.answer_question_stream(question, relevant):
            yield text

    return Response(generate(), mimetype='text/plain')

@app.route("/api/study-plan/<int:doc_id>")
def api_study_plan(doc_id):
    days = int(request.args.get("days", 7))
    conn = get_db()
    summary_row = conn.execute(
        "SELECT * FROM summaries WHERE document_id=? ORDER BY created_at DESC LIMIT 1", (doc_id,)).fetchone()
    summary_text = summary_row["summary_text"] if summary_row else ""
    plan = study_plan_agent.generate_study_plan(summary_text, "", days_until_exam=days)
    
    # Get filename for activity log
    doc = conn.execute("SELECT filename FROM documents WHERE id=?", (doc_id,)).fetchone()
    filename = doc["filename"] if doc else "Document"

    conn.execute("INSERT INTO study_plans (document_id, plan_json, exam_date) VALUES (?, ?, ?)",
                 (doc_id, json.dumps(plan), ""))
    conn.commit()
    conn.close()
    log_activity("plan", f"Generated a {days}-day study plan for {filename}")
    return jsonify(plan)

@app.route("/api/route", methods=["POST"])
def api_route():
    """Single smart endpoint — the orchestrator decides what the user wants."""
    user_input = request.json["query"]
    intent = route(user_input, "")
    return jsonify({"intent": intent})

@app.route("/api/quiz-submit/<int:doc_id>", methods=["POST"])
def api_quiz_submit(doc_id):
    data = request.json
    score = data.get("score", 0)
    total = data.get("total", 0)
    difficulty = data.get("difficulty", "medium")
    
    conn = get_db()
    doc = conn.execute("SELECT filename FROM documents WHERE id=?", (doc_id,)).fetchone()
    filename = doc["filename"] if doc else "Document"

    conn.execute("INSERT INTO quiz_attempts (document_id, score, total_questions, difficulty) VALUES (?, ?, ?, ?)",
                 (doc_id, score, total, difficulty))
    conn.commit()
    conn.close()
    log_activity("quiz", f"Completed quiz on {filename} with score {score}/{total} (Difficulty: {difficulty})")
    return jsonify({"status": "success"})

@app.route("/api/progress/<int:doc_id>")
def api_progress(doc_id):
    conn = get_db()
    attempts = conn.execute("SELECT score, total_questions, created_at FROM quiz_attempts WHERE document_id=? ORDER BY created_at ASC", (doc_id,)).fetchall()
    conn.close()
    
    data = []
    for a in attempts:
        data.append({
            "score": a["score"],
            "total": a["total_questions"],
            "date": a["created_at"]
        })
    return jsonify(data)

@app.route("/api/export-plan/<int:doc_id>")
def api_export_plan(doc_id):
    conn = get_db()
    plan_row = conn.execute("SELECT plan_json FROM study_plans WHERE document_id=? ORDER BY created_at DESC LIMIT 1", (doc_id,)).fetchone()
    conn.close()
    
    if not plan_row:
        return "No study plan found", 404
        
    plan = json.loads(plan_row["plan_json"])
    
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(200, 10, txt="AI Study Plan", ln=True, align='C')
    pdf.ln(10)
    
    for day, details in plan.items():
        pdf.set_font("Arial", 'B', 14)
        pdf.cell(200, 10, txt=str(day).replace('_', ' ').title(), ln=True)
        
        pdf.set_font("Arial", '', 12)
        pdf.cell(200, 8, txt=f"Estimated Hours: {details.get('est_hours', 'N/A')}", ln=True)
        
        pdf.set_font("Arial", 'B', 12)
        pdf.cell(200, 8, txt="Topics:", ln=True)
        pdf.set_font("Arial", '', 12)
        for t in details.get('topics', []):
            pdf.cell(200, 8, txt=f"- {t}", ln=True)
            
        pdf.set_font("Arial", 'B', 12)
        pdf.cell(200, 8, txt="Tasks:", ln=True)
        pdf.set_font("Arial", '', 12)
        for t in details.get('tasks', []):
            pdf.cell(200, 8, txt=f"- {t}", ln=True)
            
        pdf.ln(5)
        
    fd, temp_path = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)
    pdf.output(temp_path)
    
    return send_file(temp_path, as_attachment=True, download_name=f"study_plan_{doc_id}.pdf")

@app.route("/dashboard")
def dashboard():
    conn = get_db()
    # Fetch stats
    total_docs = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
    total_quizzes = conn.execute("SELECT COUNT(*) FROM quiz_attempts").fetchone()[0]
    
    avg_score_row = conn.execute("SELECT AVG(CAST(score AS FLOAT)/total_questions) FROM quiz_attempts WHERE total_questions > 0").fetchone()
    avg_score = round(avg_score_row[0] * 100, 1) if avg_score_row and avg_score_row[0] is not None else 0
    
    total_plans = conn.execute("SELECT COUNT(*) FROM study_plans").fetchone()[0]
    
    # Recent documents
    recent_docs = conn.execute("SELECT * FROM documents ORDER BY uploaded_at DESC LIMIT 5").fetchall()
    
    # Recent activity logs
    recent_activities = conn.execute("SELECT * FROM activity_log ORDER BY created_at DESC LIMIT 10").fetchall()
    
    # Fetch all quiz attempts for aggregate chart
    attempts = conn.execute("SELECT score, total_questions, created_at FROM quiz_attempts ORDER BY created_at ASC").fetchall()
    attempts_data = [{"score": a["score"], "total": a["total_questions"], "date": a["created_at"]} for a in attempts]
    
    conn.close()
    return render_template("dashboard.html", 
                           total_docs=total_docs, 
                           total_quizzes=total_quizzes, 
                           avg_score=avg_score, 
                           total_plans=total_plans,
                           recent_docs=recent_docs,
                           recent_activities=recent_activities,
                           attempts_data=json.dumps(attempts_data))

@app.route("/profile", methods=["GET", "POST"])
def profile():
    conn = get_db()
    if request.method == "POST":
        name = request.form.get("name", "Student")
        email = request.form.get("email", "student@domain.com")
        study_goal = request.form.get("study_goal", "Prepare for exams")
        target_exam_date = request.form.get("target_exam_date", "")
        
        conn.execute("""UPDATE users SET name=?, email=?, study_goal=?, target_exam_date=? WHERE id=1""",
                     (name, email, study_goal, target_exam_date))
        conn.commit()
        log_activity("profile_update", f"Updated profile details for {name}")
        return redirect("/profile")
        
    user = conn.execute("SELECT * FROM users WHERE id=1").fetchone()
    
    # Calculate badges
    total_docs = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
    total_quizzes = conn.execute("SELECT COUNT(*) FROM quiz_attempts").fetchone()[0]
    max_score_row = conn.execute("SELECT MAX(CAST(score AS FLOAT)/total_questions) FROM quiz_attempts WHERE total_questions > 0").fetchone()
    max_score = max_score_row[0] if max_score_row else None
    total_plans = conn.execute("SELECT COUNT(*) FROM study_plans").fetchone()[0]
    
    badges = []
    if total_docs >= 1:
        badges.append({"name": "Bronze Scholar", "desc": "Uploaded at least 1 document.", "icon": "📚"})
    if total_quizzes >= 3:
        badges.append({"name": "Quiz Warrior", "desc": "Attempted at least 3 quizzes.", "icon": "⚔️"})
    if max_score is not None and max_score >= 0.8:
        badges.append({"name": "Top Scorer", "desc": "Achieved a score of 80%+ on any quiz.", "icon": "🏆"})
    if total_plans >= 1:
        badges.append({"name": "Master Planner", "desc": "Generated at least 1 study plan.", "icon": "📅"})
        
    conn.close()
    return render_template("profile.html", user=user, badges=badges)

@app.route("/api/debug-logs")
def debug_logs():
    try:
        with open("error_log.txt", "r") as f:
            return Response(f.read(), mimetype="text/plain")
    except Exception as e:
        return f"No logs found: {e}"

@app.errorhandler(Exception)
def handle_exception(e):
    import traceback
    with open("error_log.txt", "a") as f:
        f.write(traceback.format_exc() + "\n")
        
    # Pass through HTTP errors
    if isinstance(e, HTTPException):
        return e
    print(f"Unhandled Exception: {e}")
    # Render a user-friendly error page or JSON
    if request.path.startswith("/api/"):
        return jsonify({"error": "An internal server error occurred.", "details": str(e)}), 500
    
    conn = get_db()
    try:
        docs = conn.execute("SELECT * FROM documents ORDER BY uploaded_at DESC").fetchall()
    except Exception:
        docs = []
    finally:
        conn.close()
    return render_template("index.html", documents=docs, error=f"An unexpected error occurred: {str(e)}"), 500

if __name__ == "__main__":
    app.run(debug=True, port=5050)
