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

    # Pay0 Checkout URL with correct amount & link
    pay0_payment_url = f"https://pay0.shop/paylink?link=4365&amt={total_amount}"

    return jsonify({
        "success": True,
        "order_id": order_id,
        "payment_url": pay0_payment_url
    })
