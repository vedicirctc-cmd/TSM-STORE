from flask import Flask, request, jsonify, redirect
from flask_cors import CORS
import sqlite3
import uuid
import datetime
import os

app = Flask(__name__)
CORS(app)

def init_db():
    conn = sqlite3.connect('store.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS stock (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_data TEXT NOT NULL,
            is_sold INTEGER DEFAULT 0
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            order_id TEXT PRIMARY KEY,
            user_contact TEXT,
            quantity INTEGER,
            amount INTEGER,
            status TEXT DEFAULT 'PENDING',
            utr_number TEXT,
            delivered_item TEXT,
            created_at TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

def get_db():
    conn = sqlite3.connect('store.db')
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/api/stock-count', methods=['GET'])
def get_stock_count():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as count FROM stock WHERE is_sold = 0")
    row = cursor.fetchone()
    conn.close()
    return jsonify({"available_stock": row['count']})

@app.route('/api/admin/add-stock', methods=['POST'])
def add_stock():
    data = request.json
    raw_stock = data.get('stock_data', '')
    lines = raw_stock.split('\n')
    conn = get_db()
    cursor = conn.cursor()
    added_count = 0
    for line in lines:
        item = line.strip()
        if item:
            cursor.execute("INSERT INTO stock (item_data) VALUES (?)", (item,))
            added_count += 1
    conn.commit()
    conn.close()
    return jsonify({"success": True, "added": added_count})

@app.route('/api/create-order', methods=['POST'])
def create_order():
    data = request.json
    mobile = data.get('mobile')
    quantity = int(data.get('quantity', 1))
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key = 'base_price'")
    row = cursor.fetchone()
    conn.close()
    
    price_per_item = int(row['value']) if row and row['value'] else 200
    total_amount = quantity * price_per_item

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as count FROM stock WHERE is_sold = 0")
    available = cursor.fetchone()['count']
    conn.close()

    if available < quantity:
        return jsonify({"success": False, "message": "Stock not available!"}), 400

    order_id = "TSM-" + str(uuid.uuid4().hex[:8]).upper()

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO orders (order_id, user_contact, quantity, amount, status, created_at)
        VALUES (?, ?, ?, ?, 'PENDING', ?)
    """, (order_id, mobile, quantity, total_amount, str(datetime.datetime.now())))
    conn.commit()
    conn.close()

    return jsonify({
        "success": True,
        "order_id": order_id,
        "payment_url": f"https://pay0.shop/paylink?link=4365&amt={total_amount}"
    })

# Helper function jo payment success hone par stock deduct karega
def process_successful_payment(order_id, utr_number):
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT quantity, status FROM orders WHERE order_id = ?", (order_id,))
    order = cursor.fetchone()
    if not order:
        conn.close()
        return False, "ORDER_NOT_FOUND"

    if order['status'] == 'SUCCESS':
        conn.close()
        return True, "ALREADY_SUCCESS"

    qty_needed = order['quantity']

    cursor.execute("SELECT id, item_data FROM stock WHERE is_sold = 0 LIMIT ?", (qty_needed,))
    items = cursor.fetchall()

    if len(items) < qty_needed:
        conn.close()
        return False, "OUT_OF_STOCK"

    delivered_items = []
    for item in items:
        cursor.execute("UPDATE stock SET is_sold = 1 WHERE id = ?", (item['id'],))
        delivered_items.append(item['item_data'])

    delivered_string = "\n".join(delivered_items)

    cursor.execute("""
        UPDATE orders 
        SET status = 'SUCCESS', utr_number = ?, delivered_item = ? 
        WHERE order_id = ?
    """, (utr_number or "AUTO-VERIFIED", delivered_string, order_id))

    conn.commit()
    conn.close()
    return True, "DELIVERED"

# Pay0 Webhook (Supports both POST and GET redirects)
@app.route('/api/pay0-webhook', methods=['GET', 'POST'])
def pay0_webhook():
    # Agar Pay0 redirect karke GET request bhejta hai ya user browser me kholta hai
    if request.method == 'GET':
        order_id = request.args.get('order_id') or request.args.get('order')
        utr = request.args.get('utr') or request.args.get('txid') or "PAY0-PAID"
        if order_id:
            process_successful_payment(order_id, utr)
            return redirect(f"https://tatkalsupermaster.shop/index.html?order_id={order_id}")
        return redirect("https://tatkalsupermaster.shop/index.html")

    # POST Webhook from Pay0 server
    data = request.json or request.form
    order_id = data.get('order_id') or data.get('order')
    utr_number = data.get('utr') or data.get('txid')
    status = data.get('status')

    if status == 'SUCCESS' or data.get('success') == True:
        success, msg = process_successful_payment(order_id, utr_number)
        return jsonify({"status": msg, "order_id": order_id}), 200

    return jsonify({"status": "FAILED"}), 400

@app.route('/api/admin/orders', methods=['GET'])
def get_admin_orders():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM orders ORDER BY created_at DESC LIMIT 50")
    rows = cursor.fetchall()
    conn.close()
    return jsonify([dict(row) for row in rows])

@app.route('/api/admin/update-pricing', methods=['POST'])
def update_pricing():
    data = request.json
    base_price = str(data.get('base_price', '200'))
    coupon_code = str(data.get('coupon_code', 'TSM10'))
    discount_amt = str(data.get('discount_amt', '20'))

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("REPLACE INTO settings (key, value) VALUES ('base_price', ?)", (base_price,))
    cursor.execute("REPLACE INTO settings (key, value) VALUES ('coupon_code', ?)", (coupon_code,))
    cursor.execute("REPLACE INTO settings (key, value) VALUES ('discount_amt', ?)", (discount_amt,))
    conn.commit()
    conn.close()
    return jsonify({"success": True, "message": "Pricing updated successfully!"})

@app.route('/api/settings', methods=['GET'])
def get_settings():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT key, value FROM settings")
    rows = cursor.fetchall()
    conn.close()
    
    settings = {row['key']: row['value'] for row in rows}
    return jsonify({
        "base_price": int(settings.get('base_price', 200)),
        "coupon_code": settings.get('coupon_code', 'TSM10'),
        "discount_amt": int(settings.get('discount_amt', 20))
    })

@app.route('/api/admin/stocks', methods=['GET'])
def get_admin_stocks():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM stock ORDER BY id DESC LIMIT 100")
    rows = cursor.fetchall()
    conn.close()
    return jsonify([dict(row) for row in rows])

@app.route('/api/admin/delete-stock/<int:stock_id>', methods=['DELETE'])
def delete_stock(stock_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM stock WHERE id = ?", (stock_id,))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
