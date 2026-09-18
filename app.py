from flask import Flask, render_template, request

from search.db import connect, list_sources, search as run_search

app = Flask(__name__)


@app.route("/")
def index():
    query = request.args.get("q", "").strip()
    conn = connect()
    all_sources = list_sources(conn)
    selected_sources = [s for s in request.args.getlist("source") if s in all_sources] or all_sources

    results = []
    if query:
        results = run_search(conn, query, sources=selected_sources)
    return render_template(
        "index.html",
        query=query,
        results=results,
        all_sources=all_sources,
        selected_sources=selected_sources,
    )


if __name__ == "__main__":
    app.run(debug=True, port=5000)
