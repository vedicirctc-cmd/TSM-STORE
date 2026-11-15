@app.route('/api/pay0-webhook', methods=['GET', 'POST'])
def pay0_webhook():
    # Jab Pay0 user ke browser ko redirect karke yahan bhejega (GET request)
    if request.method == 'GET':
        order_id = request.args.get('order_id') or request.args.get('order') or request.args.get('client_txn_id')
        status = request.args.get('status') or request.args.get('txstatus')
        utr = request.args.get('utr') or request.args.get('txid') or request.args.get('bank_txn_id') or "PAY0-REDIRECT"
        
        target_order_id = None

        if order_id:
            target_order_id = order_id
            deliver_stock_for_order(order_id, utr)
        else:
            # Agar Pay0 ne redirect me order_id nahi bheji, toh database me se 
            # sabse aakhiri (latest) PENDING order ko uthakar auto-deliver kar do
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("SELECT order_id FROM orders WHERE status = 'PENDING' ORDER BY created_at DESC LIMIT 1")
            recent_order = cursor.fetchone()
            conn.close()

            if recent_order:
                target_order_id = recent_order['order_id']
                deliver_stock_for_order(target_order_id, "PAY0-AUTO-MATCH")

        # Customer ko seedha success page par bhej do
        if target_order_id:
            return redirect(f"https://tatkalsupermaster.shop/success.html?order_id={target_order_id}")
        else:
            return redirect("https://tatkalsupermaster.shop/index.html")

    # Server-to-Server Background POST Webhook from Pay0
    data = request.json or request.form or {}
    order_id = data.get('order_id') or data.get('order')
    utr_number = str(data.get('utr') or data.get('txid') or data.get('bank_txnid') or "").strip()
    status = str(data.get('status') or "").upper()

    if status in ['SUCCESS', 'COMPLETED', 'PAID'] and order_id:
        success, msg = deliver_stock_for_order(order_id, utr_number or "PAY0-AUTO")
        return jsonify({"status": msg, "order_id": order_id}), 200

    return jsonify({"status": "IGNORED"}), 200
