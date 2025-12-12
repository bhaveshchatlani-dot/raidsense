from flask import Flask, request, render_template_string, send_file
from pathlib import Path
import json
import time
import os

# Reuse your existing functions from app.py
from app import analyse_notes_with_openai, render_markdown

app = Flask(__name__)

HTML = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>RAIDSense</title>




  <style>
    body { font-family: -apple-system, system-ui, Arial; margin: 40px; max-width: 1100px; }
    textarea { width: 100%; height: 220px; padding: 12px; }
    button { padding: 10px 14px; cursor: pointer; }
    .box { border: 1px solid #ddd; padding: 16px; border-radius: 12px; margin-top: 16px; }
    .row { display: flex; gap: 12px; flex-wrap: wrap; align-items: center; }
    .pill { display: inline-block; padding: 4px 10px; border: 1px solid #ddd; border-radius: 999px; font-size: 13px; }
    table { width: 100%; border-collapse: collapse; margin-top: 8px; }
    th, td { text-align: left; border-bottom: 1px solid #eee; padding: 10px 8px; vertical-align: top; }
    th { font-size: 13px; color: #444; }
    .muted { color: #666; font-size: 13px; }
    pre { white-space: pre-wrap; background: #fafafa; padding: 12px; border-radius: 10px; border: 1px solid #eee; }
    a { margin-right: 12px; }
  </style>
</head>
<body>
  <h1>RAIDSense</h1>
  <p class="muted">Paste meeting notes, then generate RAID.</p>
  <p><a href="/history">View history</a></p>

<form method="post" action="/generate" enctype="multipart/form-data">
  <p class="muted">Option A: Upload a .txt file</p>
  <input type="file" name="notes_file" accept=".txt" />

  <p class="muted" style="margin-top:14px;">Option B: Or paste notes</p>
  <textarea name="notes" placeholder="Paste meeting notes here...">{{ notes }}</textarea>
  <br><br>
  <button type="submit">Generate RAID</button>
</form>

  {% if raid %}
    <div class="box">
      <div class="row">
        <h2 style="margin:0;">Results</h2>
        <span class="pill">Risks: {{ raid.risks|length }}</span>
        <span class="pill">Assumptions: {{ raid.assumptions|length }}</span>
        <span class="pill">Issues: {{ raid.issues|length }}</span>
        <span class="pill">Dependencies: {{ raid.dependencies|length }}</span>
      </div>

      <h3>Risks</h3>
      {% if raid.risks|length == 0 %}
        <p class="muted">None identified</p>
      {% else %}
        <table>
          <thead><tr><th>Title</th><th>Detail</th><th>Mitigation</th></tr></thead>
          <tbody>
            {% for r in raid.risks %}
              <tr><td><b>{{ r.title }}</b></td><td>{{ r.detail }}</td><td>{{ r.mitigation }}</td></tr>
            {% endfor %}
          </tbody>
        </table>
      {% endif %}

      <h3>Assumptions</h3>
      {% if raid.assumptions|length == 0 %}
        <p class="muted">None identified</p>
      {% else %}
        <table>
          <thead><tr><th>Title</th><th>Detail</th><th>Validation step</th></tr></thead>
          <tbody>
            {% for a in raid.assumptions %}
              <tr><td><b>{{ a.title }}</b></td><td>{{ a.detail }}</td><td>{{ a.validation_step }}</td></tr>
            {% endfor %}
          </tbody>
        </table>
      {% endif %}

      <h3>Issues</h3>
      {% if raid.issues|length == 0 %}
        <p class="muted">None identified</p>
      {% else %}
        <table>
          <thead><tr><th>Title</th><th>Detail</th><th>Next step</th></tr></thead>
          <tbody>
            {% for i in raid.issues %}
              <tr><td><b>{{ i.title }}</b></td><td>{{ i.detail }}</td><td>{{ i.next_step }}</td></tr>
            {% endfor %}
          </tbody>
        </table>
      {% endif %}

      <h3>Dependencies</h3>
      {% if raid.dependencies|length == 0 %}
        <p class="muted">None identified</p>
      {% else %}
        <table>
          <thead><tr><th>Title</th><th>Detail</th><th>Owner</th><th>Due date</th></tr></thead>
          <tbody>
            {% for d in raid.dependencies %}
              <tr><td><b>{{ d.title }}</b></td><td>{{ d.detail }}</td><td>{{ d.owner }}</td><td>{{ d.due_date }}</td></tr>
            {% endfor %}
          </tbody>
        </table>
      {% endif %}

      <div style="margin-top: 14px;">
        <a href="/download/md/{{ run_id }}">Download MD</a>
        <a href="/download/json/{{ run_id }}">Download JSON</a>
      </div>
    </div>

    <div class="box">
      <h2>Report (Markdown)</h2>
      <pre>{{ raid_md }}</pre>
    </div>
  {% endif %}
</body>
</html>
"""

OUTPUT_DIR = Path("outputs")
OUTPUT_DIR.mkdir(exist_ok=True)

def list_runs():
    files = sorted(OUTPUT_DIR.glob("*_RAID.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    runs = []
    for f in files:
        run_id = f.name.replace("_RAID.json", "")
        runs.append(run_id)
    return runs

def save_outputs(run_id: str, raid_data: dict, raid_md: str, notes: str):
    (OUTPUT_DIR / f"{run_id}_RAID.json").write_text(json.dumps(raid_data, indent=2), encoding="utf-8")
    (OUTPUT_DIR / f"{run_id}_RAID.md").write_text(raid_md, encoding="utf-8")
    (OUTPUT_DIR / f"{run_id}_notes.txt").write_text(notes, encoding="utf-8")

@app.get("/")
def home():
    return render_template_string(HTML, notes="", raid=None, raid_md="", run_id="")

@app.post("/generate")
def generate():
    notes = ""

    # 1) Try file upload first
    uploaded = request.files.get("notes_file")
    if uploaded and uploaded.filename:
        try:
            notes = uploaded.read().decode("utf-8").strip()
        except Exception:
            return render_template_string(
                HTML,
                notes="",
                raid=None,
                raid_md="Could not read that file. Make sure it's a UTF-8 .txt file.",
                run_id="",
            )

    # 2) If no file (or empty), fall back to pasted text
    if not notes:
        notes = request.form.get("notes", "").strip()

    if not notes:
        return render_template_string(
            HTML, notes="", raid=None, raid_md="Please upload a .txt file or paste some notes.", run_id=""
        )

    raid_data = analyse_notes_with_openai(notes)
    raid_md = render_markdown(raid_data)

    run_id = str(int(time.time()))
    save_outputs(run_id, raid_data, raid_md, notes)

    return render_template_string(HTML, notes=notes, raid=raid_data, raid_md=raid_md, run_id=run_id)

@app.get("/download/<fmt>/<run_id>")
def download(fmt, run_id):
    if fmt not in ("md", "json"):
        return "Invalid format", 400

    path = OUTPUT_DIR / f"{run_id}_RAID.{fmt}"
    if not path.exists():
        return "File not found", 404

    return send_file(path, as_attachment=True)

@app.get("/history")
def history():
    runs = list_runs()
    items = "".join([f"<li><a href='/run/{rid}'>{rid}</a></li>" for rid in runs]) or "<li>No runs yet.</li>"
    return f"""
    <h1>RAIDSense History</h1>
    <p><a href="/">Back</a></p>
    <ul>{items}</ul>
    """

@app.get("/run/<run_id>")
def view_run(run_id):
    json_path = OUTPUT_DIR / f"{run_id}_RAID.json"
    md_path = OUTPUT_DIR / f"{run_id}_RAID.md"
    notes_path = OUTPUT_DIR / f"{run_id}_notes.txt"

    if not json_path.exists() or not md_path.exists():
        return "Run not found", 404

    raid_data = json.loads(json_path.read_text(encoding="utf-8"))
    raid_md = md_path.read_text(encoding="utf-8")
    notes = notes_path.read_text(encoding="utf-8") if notes_path.exists() else ""

    return render_template_string(HTML, notes=notes, raid=raid_data, raid_md=raid_md, run_id=run_id)

if __name__ == "__main__":
   if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)