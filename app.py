import os
import json
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from models import get_db, init_db, auto_categorize
from parser import parse_pdf

app = Flask(__name__)
app.secret_key = 'expense-tracker-secret-2024'
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(__file__), 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
init_db()

def current_month():
    return datetime.now().strftime('%Y-%m')

@app.route('/')
def index():
    month = request.args.get('month', current_month())
    conn = get_db()
    months = [r['m'] for r in conn.execute(
        "SELECT DISTINCT substr(date,1,7) as m FROM transactions ORDER BY m DESC"
    ).fetchall()]
    if month not in months:
        months = ([month] + months)[:24]
    conn.close()
    return render_template('index.html', month=month, months=months)

@app.route('/upload', methods=['GET'])
def upload_page():
    return render_template('upload.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        flash('Nenhum arquivo enviado.', 'error')
        return redirect(url_for('upload_page'))
    f = request.files['file']
    if not f.filename or not f.filename.lower().endswith('.pdf'):
        flash('Apenas arquivos PDF são aceitos.', 'error')
        return redirect(url_for('upload_page'))
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], f.filename)
    f.save(filepath)
    transactions = parse_pdf(filepath)
    conn = get_db()
    inserted = 0
    for t in transactions:
        existing = conn.execute(
            'SELECT id FROM transactions WHERE date=? AND description=? AND amount=?',
            (t['date'], t['description'], t['amount'])
        ).fetchone()
        if not existing:
            category = auto_categorize(t['description'])
            conn.execute(
                'INSERT INTO transactions (date, description, amount, category, source_file, created_at) VALUES (?,?,?,?,?,?)',
                (t['date'], t['description'], t['amount'], category, f.filename, datetime.now().isoformat())
            )
            inserted += 1
    conn.commit()
    conn.close()
    flash(f'{inserted} transações importadas com sucesso!', 'success')
    return redirect(url_for('transactions'))

@app.route('/transactions')
def transactions():
    month = request.args.get('month', current_month())
    category = request.args.get('category', '')
    page = int(request.args.get('page', 1))
    per_page = 50
    offset = (page - 1) * per_page
    conn = get_db()
    params = [f"{month}%"]
    where = "WHERE date LIKE ?"
    if category:
        where += " AND category=?"
        params.append(category)
    total = conn.execute(f"SELECT COUNT(*) FROM transactions {where}", params).fetchone()[0]
    rows = conn.execute(
        f"SELECT * FROM transactions {where} ORDER BY date DESC LIMIT ? OFFSET ?",
        params + [per_page, offset]
    ).fetchall()
    cats = [r['name'] for r in conn.execute('SELECT name FROM categories ORDER BY name').fetchall()]
    months = [r['m'] for r in conn.execute(
        "SELECT DISTINCT substr(date,1,7) as m FROM transactions ORDER BY m DESC"
    ).fetchall()]
    conn.close()
    pages = (total + per_page - 1) // per_page
    return render_template('transactions.html',
        transactions=rows, categories=cats,
        months=months, month=month, category=category,
        page=page, pages=pages, total=total
    )

@app.route('/transactions/<int:id>/category', methods=['POST'])
def update_category(id):
    data = request.get_json()
    if not data or 'category' not in data:
        return jsonify({'success': False}), 400
    conn = get_db()
    conn.execute('UPDATE transactions SET category=? WHERE id=?', (data['category'], id))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/transactions/<int:id>', methods=['DELETE'])
def delete_transaction(id):
    conn = get_db()
    conn.execute('DELETE FROM transactions WHERE id=?', (id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/summary')
def api_summary():
    month = request.args.get('month', current_month())
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM transactions WHERE date LIKE ?", (f"{month}%",)
    ).fetchall()
    conn.close()
    total_expenses = sum(r['amount'] for r in rows if r['amount'] < 0)
    total_income = sum(r['amount'] for r in rows if r['amount'] > 0)
    balance = total_income + total_expenses
    by_cat = {}
    daily = {}
    for r in rows:
        if r['amount'] < 0:
            by_cat[r['category']] = by_cat.get(r['category'], 0) + abs(r['amount'])
            daily[r['date']] = daily.get(r['date'], 0) + abs(r['amount'])
    by_category = sorted([{'category': k, 'total': round(v, 2)} for k, v in by_cat.items()], key=lambda x: -x['total'])
    daily_list = sorted([{'date': k, 'total': round(v, 2)} for k, v in daily.items()], key=lambda x: x['date'])
    return jsonify({
        'total_expenses': round(abs(total_expenses), 2),
        'total_income': round(total_income, 2),
        'balance': round(balance, 2),
        'by_category': by_category,
        'daily': daily_list
    })

if __name__ == '__main__':
    app.run(debug=True)
