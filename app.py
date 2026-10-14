import json
import sqlite3
from pathlib import Path

from flask import Flask, g, jsonify, request

from dispatcher import classify

BASE = Path(__file__).resolve().parent
CASES_FILE = BASE / "cases_training.json"

app = Flask(__name__, static_folder="static", static_url_path="")

DB_FILE = BASE / "dispatcher.sqlite3"

CATEGORIES = {"техника", "сеть", "помещение", "другое"}
PRIORITIES = {"высокий", "обычный"}


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_FILE)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = get_db()

    db.executescript("""
        CREATE TABLE IF NOT EXISTS collections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            collection_id INTEGER NOT NULL
                REFERENCES collections(id) ON DELETE CASCADE,
            text TEXT NOT NULL,
            ai_category TEXT,
            ai_priority TEXT,
            ai_question TEXT NOT NULL DEFAULT '',
            review_category TEXT,
            review_priority TEXT,
            reviewed_at TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_requests_collection
        ON requests(collection_id, id);
    """)

    db.execute(
        "INSERT OR IGNORE INTO collections (name) VALUES (?)",
        ("Входящие",),
    )
    db.execute(
        "INSERT OR IGNORE INTO collections (name) VALUES (?)",
        ("Учебные обращения",),
    )

    # Однократно переносим примеры из JSON в SQLite.
    training_collection = db.execute(
        "SELECT id FROM collections WHERE name = ?",
        ("Учебные обращения",),
    ).fetchone()

    existing = db.execute(
        "SELECT COUNT(*) FROM requests WHERE collection_id = ?",
        (training_collection["id"],),
    ).fetchone()[0]

    if existing == 0 and CASES_FILE.exists():
        with CASES_FILE.open(encoding="utf-8") as file:
            examples = json.load(file)

        if isinstance(examples, list):
            for item in examples:
                if not isinstance(item, dict) or not isinstance(item.get("text"), str):
                    continue

                category = item.get("category")
                priority = item.get("priority")

                db.execute(
                    """
                    INSERT INTO requests (
                        collection_id, text, review_category, review_priority
                    )
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        training_collection["id"],
                        item["text"].strip(),
                        category if category in CATEGORIES else None,
                        priority if priority in PRIORITIES else None,
                    ),
                )

    db.commit()



@app.get("/")
def index():
    return app.send_static_file("index.html")


@app.get("/api/cases")
def cases():
    try:
        with CASES_FILE.open(encoding="utf-8") as file:
            data = json.load(file)

        if not isinstance(data, list):
            raise ValueError("Файл cases_training.json должен содержать список.")

        return jsonify(data)
    except (OSError, json.JSONDecodeError, ValueError) as error:
        app.logger.exception("Не удалось загрузить учебные обращения")
        return jsonify({"error": str(error)}), 500


@app.post("/api/classify")
def classify_api():
    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify({"error": "Ожидался JSON-объект."}), 400

    request_id = data.get("request_id")
    db = get_db()

    if request_id is not None:
        row = db.execute(
            "SELECT id, text FROM requests WHERE id = ?",
            (request_id,),
        ).fetchone()

        if row is None:
            return jsonify({"error": "Обращение не найдено."}), 404

        # При повторной классификации используем текст из базы.
        text = row["text"]
    else:
        text = data.get("text")
        if not isinstance(text, str) or not 1 <= len(text.strip()) <= 1000:
            return jsonify({
                "error": "Введите обращение длиной от 1 до 1000 символов."
            }), 400
        text = text.strip()

    try:
        result = classify(text)

        if request_id is None:
            inbox = db.execute(
                "SELECT id FROM collections WHERE name = ?",
                ("Входящие",),
            ).fetchone()

            cursor = db.execute(
                """
                INSERT INTO requests (
                    collection_id, text, ai_category, ai_priority, ai_question
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    inbox["id"],
                    text,
                    result["category"],
                    result["priority"],
                    result["question"],
                ),
            )
            request_id = cursor.lastrowid
        else:
            db.execute(
                """
                UPDATE requests
                SET ai_category = ?, ai_priority = ?, ai_question = ?
                WHERE id = ?
                """,
                (
                    result["category"],
                    result["priority"],
                    result["question"],
                    request_id,
                ),
            )

        db.commit()
        return jsonify({**result, "id": request_id})

    except Exception as error:
        db.rollback()
        app.logger.exception("Ошибка классификации обращения")
        return jsonify({"error": f"Не удалось обработать обращение: {error}"}), 502

@app.patch("/api/requests/<int:request_id>/review")
def save_review(request_id):
    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify({"error": "Ожидался JSON-объект."}), 400

    category = data.get("category")
    priority = data.get("priority")

    if category not in CATEGORIES or priority not in PRIORITIES:
        return jsonify({"error": "Недопустимая категория или приоритет."}), 400

    cursor = get_db().execute(
        """
        UPDATE requests
        SET review_category = ?,
            review_priority = ?,
            reviewed_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (category, priority, request_id),
    )
    get_db().commit()

    if cursor.rowcount == 0:
        return jsonify({"error": "Обращение не найдено."}), 404

    return jsonify({"saved": True})


@app.get("/api/history")
def history():
    rows = get_db().execute(
        """
        SELECT id, text, category, priority, question, created_at
        FROM requests
        ORDER BY id DESC
        LIMIT 100
        """
    ).fetchall()

    return jsonify([dict(row) for row in rows])

@app.get("/api/collections")
def get_collections():
    rows = get_db().execute("""
        SELECT c.id, c.name, COUNT(r.id) AS request_count
        FROM collections c
        LEFT JOIN requests r ON r.collection_id = c.id
        GROUP BY c.id
        ORDER BY c.id
    """).fetchall()

    return jsonify([dict(row) for row in rows])


@app.get("/api/collections/<int:collection_id>/requests")
def get_collection_requests(collection_id):
    rows = get_db().execute(
        """
        SELECT id, text, ai_category, ai_priority, ai_question,
               review_category, review_priority
        FROM requests
        WHERE collection_id = ?
        ORDER BY id
        """,
        (collection_id,),
    ).fetchall()

    return jsonify([dict(row) for row in rows])


@app.post("/api/collections")
def create_collection():
    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify({"error": "Ожидался JSON-объект."}), 400

    name = data.get("name")
    items = data.get("requests")

    if not isinstance(name, str) or not name.strip() or len(name.strip()) > 100:
        return jsonify({"error": "Название набора должно содержать 1–100 символов."}), 400
    if not isinstance(items, list) or not items:
        return jsonify({"error": "Передайте непустой список requests."}), 400
    if len(items) > 1000:
        return jsonify({"error": "В одном наборе допускается не более 1000 обращений."}), 400

    db = get_db()

    try:
        cursor = db.execute(
            "INSERT INTO collections (name) VALUES (?)",
            (name.strip(),),
        )
        collection_id = cursor.lastrowid

        for item in items:
            if not isinstance(item, dict):
                continue

            text = item.get("text")
            if not isinstance(text, str) or not 1 <= len(text.strip()) <= 1000:
                continue

            category = item.get("category")
            priority = item.get("priority")

            db.execute(
                """
                INSERT INTO requests (
                    collection_id, text, review_category, review_priority
                )
                VALUES (?, ?, ?, ?)
                """,
                (
                    collection_id,
                    text.strip(),
                    category if category in CATEGORIES else None,
                    priority if priority in PRIORITIES else None,
                ),
            )

        db.commit()
        return jsonify({"id": collection_id, "name": name.strip()}), 201

    except sqlite3.IntegrityError:
        db.rollback()
        return jsonify({"error": "Набор с таким названием уже существует."}), 409


with app.app_context():
    init_db()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
