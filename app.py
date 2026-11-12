from flask import Flask, request, jsonify
from flask_cors import CORS
import sqlite3
import uuid
import datetime
import os

app = Flask(__name__)
CORS(app)  # Frontend aur Admin dashboard ko connect karne ke liye

# Database Initialization
def init_db():
    conn = sqlite3.connect('store.db')
    cursor = conn.cursor()
    
    # Stock Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS stock (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_data TEXT NOT NULL,
            is_sold INTEGER DEFAULT 0
        )
    ''')
    
    # Orders Table
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
    
    # Settings Table (Pricing aur Config ke liye)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    conn.commit()
    conn.close()

# Start me DB table create kar do
init_db()

def get_db():
    conn = sqlite3.connect('store.db')
    conn.row_factory = sqlite3.Row
    return conn

# 1. API: Available Stock Count check karne ke liye
@app.route('/api/stock-count', methods=['GET'])
def get_stock_count():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as count FROM stock WHERE is_sold = 0")
    row = cursor.fetchone()
    conn.close()
    return jsonify({"available_stock": row['count']})

# 2. API: Admin dwara Stock Add karne ke liye
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

# 3. API: User Order Create Karega (Pay0 Link generate karne ke liye)
@app.route('/api/create-order', methods=['POST'])
def create_order():
    data = request.json
    mobile = data.get('mobile')
    quantity = int(data.get('quantity', 1))
    
    # Database se current price fetch karna (default 200 agar set na ho)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key = 'base_price'")
    row = cursor.fetchone()
    conn.close()
    
    price_per_item = int(row['value']) if row else 200
    total_amount = quantity * price_per_item

    # Stock check
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as count FROM stock WHERE is_sold = 0")
    available = cursor.fetchone()['count']

    if available < quantity:
        conn.close()
        return jsonify({"success": False, "message": "Stock not available!"}), 400

    order_id = "TSM-" + str(uuid.uuid4().hex[:8]).upper()

    cursor.execute("""
        INSERT INTO orders (order_id, user_contact, quantity, amount, status, created_at)
        VALUES (?, ?, ?, ?, 'PENDING', ?)
    """, (order_id, mobile, quantity, total_amount, str(datetime.datetime.now())))
    conn.commit()
    conn.close()

    # Pay0 Checkout URL Simulation/Generation
    pay0_payment_url = f"https://pay0.co/pay?order_id={order_id}&amount={total_amount}"

    return jsonify({
        "success": True,
        "order_id": order_id,
        "payment_url": pay0_payment_url
    })

# 4. API: Pay0 Instant Webhook (Payment hone par UTR match karke ID dena)
@app.route('/api/pay0-webhook', methods=['POST'])
def pay0_webhook():
    data = request.json
    order_id = data.get('order_id')
    utr_number = data.get('utr')
    status = data.get('status')  # 'SUCCESS'

    if status == 'SUCCESS':
        conn = get_db()
        cursor = conn.cursor()

        # Duplicate UTR Check
        cursor.execute("SELECT * FROM orders WHERE utr_number = ?", (utr_number,))
        if cursor.fetchone():
            conn.close()
            return jsonify({"status": "DUPLICATE_UTR"}), 400

        # Get Order Quantity
        cursor.execute("SELECT quantity FROM orders WHERE order_id = ?", (order_id,))
        order = cursor.fetchone()
        if not order:
            conn.close()
            return jsonify({"status": "ORDER_NOT_FOUND"}), 404

        qty_needed = order['quantity']

        # Fetch unsold stock
        cursor.execute("SELECT id, item_data FROM stock WHERE is_sold = 0 LIMIT ?", (qty_needed,))
        items = cursor.fetchall()

        if len(items) < qty_needed:
            conn.close()
            return jsonify({"status": "OUT_OF_STOCK"}), 400

        delivered_items = []
        for item in items:
            cursor.execute("UPDATE stock SET is_sold = 1 WHERE id = ?", (item['id'],))
            delivered_items.append(item['item_data'])

        delivered_string = "\n".join(delivered_items)

        # Update Order Status to SUCCESS & save delivered items
        cursor.execute("""
            UPDATE orders 
            SET status = 'SUCCESS', utr_number = ?, delivered_item = ? 
            WHERE order_id = ?
        """, (utr_number, delivered_string, order_id))

        conn.commit()
        conn.close()

        return jsonify({"status": "DELIVERED", "order_id": order_id}), 200

    return jsonify({"status": "FAILED"}), 400

# 5. API: Admin ke liye saare orders / UTR logs dekhne ke liye
@app.route('/api/admin/orders', methods=['GET'])
def get_admin_orders():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM orders ORDER BY created_at DESC LIMIT 50")
    rows = cursor.fetchall()
    conn.close()
    
    orders = [dict(row) for row in rows]
    return jsonify(orders)

# 6. API: Admin dwara Pricing update karne ke liye (Naya Joda Gaya Route)
@app.route('/api/admin/update-pricing', methods=['POST'])
def update_pricing():
    data = request.json
    base_price = data.get('base_price', '200')
    coupon_code = data.get('coupon_code', 'TSM10')
    discount_amt = data.get('discount_amt', '20')

    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("REPLACE INTO settings (key, value) VALUES ('base_price', ?)", (base_price,))
    cursor.execute("REPLACE INTO settings (key, value) VALUES ('coupon_code', ?)", (coupon_code,))
    cursor.execute("REPLACE INTO settings (key, value) VALUES ('discount_amt', ?)", (discount_amt,))
    
    conn.commit()
    conn.close()
    return jsonify({"success": True, "message": "Pricing updated successfully!"})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
