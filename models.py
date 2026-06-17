import sqlite3
import json
import os

DB_PATH = os.path.join(os.path.dirname(__file__), 'gastos.db')

DEFAULT_CATEGORIES = {
    "Alimentação": ["mercado", "supermercado", "restaurante", "lanche", "ifood", "rappi", "padaria", "açougue", "hortifruti"],
    "Transporte": ["uber", "99", "combustivel", "gasolina", "posto", "estacionamento", "metro", "onibus", "passagem"],
    "Saúde": ["farmacia", "drogaria", "medico", "clinica", "hospital", "exame", "plano de saude", "odonto"],
    "Moradia": ["aluguel", "condominio", "agua", "luz", "energia", "gas", "internet", "telefone"],
    "Lazer": ["cinema", "teatro", "show", "netflix", "spotify", "amazon", "steam", "jogo"],
    "Compras": ["amazon", "americanas", "magazine", "shopee", "aliexpress", "shein", "roupa", "calcado"],
    "Educação": ["escola", "faculdade", "curso", "livro", "udemy"],
    "Outros": []
}

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT,
        description TEXT,
        amount REAL,
        category TEXT,
        source_file TEXT,
        created_at TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS categories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE,
        keywords TEXT
    )''')
    for name, keywords in DEFAULT_CATEGORIES.items():
        c.execute('INSERT OR IGNORE INTO categories (name, keywords) VALUES (?, ?)',
                  (name, json.dumps(keywords, ensure_ascii=False)))
    conn.commit()
    conn.close()

def auto_categorize(description: str) -> str:
    desc_lower = description.lower()
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT name, keywords FROM categories WHERE name != "Outros"')
    rows = c.fetchall()
    conn.close()
    for row in rows:
        keywords = json.loads(row['keywords'])
        for kw in keywords:
            if kw.lower() in desc_lower:
                return row['name']
    return "Outros"
