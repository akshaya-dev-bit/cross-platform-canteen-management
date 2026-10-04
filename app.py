from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO
import sqlite3
from datetime import datetime

app = Flask(__name__)
app.config["SECRET_KEY"] = "canteen-project"

socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode="threading"
)

DB_NAME = "canteen.db"


def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            price REAL NOT NULL,
            stock INTEGER NOT NULL DEFAULT 0,
            stall TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_name TEXT NOT NULL,
            item TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            total REAL NOT NULL,
            stall TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Pending',
            created_at TEXT NOT NULL
        )
    """)

    items = [
        ("Veg Burger", 60, 20, "Fast Food"),
        ("Masala Dosa", 50, 15, "South Indian"),
        ("Veg Biryani", 90, 10, "Meals"),
        ("Samosa", 20, 30, "Snacks"),
        ("Tea", 15, 50, "Beverages")
    ]

    for item in items:
        cur.execute("""
            INSERT OR IGNORE INTO inventory
            (name, price, stock, stall)
            VALUES (?, ?, ?, ?)
        """, item)

    conn.commit()
    conn.close()


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/reception")
def reception():
    return render_template("reception.html")


@app.route("/stall")
def stall():
    return render_template("stall.html")


@app.route("/admin")
def admin():
    return render_template("admin.html")


@app.get("/api/inventory")
def inventory():
    conn = get_db()

    rows = conn.execute(
        "SELECT * FROM inventory ORDER BY id"
    ).fetchall()

    conn.close()

    return jsonify([dict(row) for row in rows])


@app.get("/api/orders")
def orders():
    conn = get_db()

    rows = conn.execute(
        "SELECT * FROM orders ORDER BY id DESC"
    ).fetchall()

    conn.close()

    return jsonify([dict(row) for row in rows])


@app.post("/api/orders")
def create_order():

    data = request.get_json(silent=True) or {}

    customer = str(
        data.get("customer_name", "")
    ).strip()

    item = str(
        data.get("item", "")
    ).strip()

    try:
        quantity = int(
            data.get("quantity", 0)
        )
    except (TypeError, ValueError):
        quantity = 0

    if not customer or not item or quantity <= 0:
        return jsonify({
            "error": "Enter valid customer, item and quantity."
        }), 400

    conn = get_db()

    product = conn.execute(
        "SELECT * FROM inventory WHERE name = ?",
        (item,)
    ).fetchone()

    if product is None:
        conn.close()

        return jsonify({
            "error": "Item not found."
        }), 404

    if product["stock"] < quantity:
        conn.close()

        return jsonify({
            "error": f"Only {product['stock']} available."
        }), 400

    total = product["price"] * quantity

    created_at = datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    cur = conn.cursor()

    cur.execute("""
        INSERT INTO orders
        (customer_name, item, quantity, total,
         stall, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        customer,
        item,
        quantity,
        total,
        product["stall"],
        "Pending",
        created_at
    ))

    order_id = cur.lastrowid

    cur.execute(
        """
        UPDATE inventory
        SET stock = stock - ?
        WHERE id = ?
        """,
        (quantity, product["id"])
    )

    conn.commit()

    order = conn.execute(
        "SELECT * FROM orders WHERE id = ?",
        (order_id,)
    ).fetchone()

    updated = conn.execute(
        "SELECT * FROM inventory WHERE id = ?",
        (product["id"],)
    ).fetchone()

    conn.close()

    socketio.emit(
        "new_order",
        dict(order)
    )

    socketio.emit(
        "inventory_updated",
        dict(updated)
    )

    return jsonify(dict(order)), 201


@app.put("/api/orders/<int:order_id>")
def update_order(order_id):

    data = request.get_json(
        silent=True
    ) or {}

    status = str(
        data.get("status", "")
    ).strip()

    allowed = {
        "Pending",
        "Preparing",
        "Ready",
        "Completed"
    }

    if status not in allowed:
        return jsonify({
            "error": "Invalid status."
        }), 400

    conn = get_db()

    conn.execute(
        """
        UPDATE orders
        SET status = ?
        WHERE id = ?
        """,
        (status, order_id)
    )

    conn.commit()

    order = conn.execute(
        "SELECT * FROM orders WHERE id = ?",
        (order_id,)
    ).fetchone()

    conn.close()

    if order is None:
        return jsonify({
            "error": "Order not found."
        }), 404

    socketio.emit(
        "order_updated",
        dict(order)
    )

    return jsonify(dict(order))


@app.post("/api/inventory/<int:item_id>/restock")
def restock(item_id):

    data = request.get_json(
        silent=True
    ) or {}

    try:
        amount = int(
            data.get("amount", 0)
        )
    except (TypeError, ValueError):
        amount = 0

    if amount <= 0:
        return jsonify({
            "error": "Invalid restock amount."
        }), 400

    conn = get_db()

    conn.execute(
        """
        UPDATE inventory
        SET stock = stock + ?
        WHERE id = ?
        """,
        (amount, item_id)
    )

    conn.commit()

    item = conn.execute(
        "SELECT * FROM inventory WHERE id = ?",
        (item_id,)
    ).fetchone()

    conn.close()

    if item is None:
        return jsonify({
            "error": "Item not found."
        }), 404

    socketio.emit(
        "inventory_updated",
        dict(item)
    )

    return jsonify(dict(item))


if __name__ == "__main__":

    init_db()

    print("Canteen Management System")
    print("Open http://127.0.0.1:5000")

    socketio.run(
        app,
        host="127.0.0.1",
        port=5000,
        debug=True,
        allow_unsafe_werkzeug=True
    )