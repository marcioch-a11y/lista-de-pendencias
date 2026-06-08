import os
import sqlite3
from datetime import datetime

# Caminho absoluto para o arquivo do banco de dados
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "clawdbot.db")

def get_db_connection():
    """
    Abre uma conexão com o banco de dados SQLite e configura para retornar dicionários.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """
    Inicializa o banco de dados criando a tabela 'tarefas' se ela não existir.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tarefas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            google_task_id TEXT UNIQUE,
            linha_sheets INTEGER,
            projeto TEXT,
            responsavel TEXT,
            assunto TEXT,
            problema_contramedida TEXT,
            data_vencimento TEXT,
            prioridade INTEGER,
            status TEXT CHECK (status IN ('△', 'O', 'X')),
            data_entrada TEXT,
            data_fechamento TEXT
        )
    """)
    conn.commit()
    conn.close()
    print(f"Banco de dados SQLite inicializado com sucesso em: {DB_PATH}")

def save_or_update_task(task_data):
    """
    Salva ou atualiza uma tarefa no SQLite.
    Se o google_task_id for fornecido e já existir, atualiza os campos.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    google_id = task_data.get("google_task_id")
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Validação Poka-Yoke do Status
    status = task_data.get("status", "△")
    if status not in ['△', 'O', 'X']:
        raise ValueError(f"Status inválido: {status}. Deve ser estritamente '△', 'O' ou 'X'.")

    # Verifica se já existe por google_task_id
    existing = None
    if google_id:
        cursor.execute("SELECT id, status, data_entrada FROM tarefas WHERE google_task_id = ?", (google_id,))
        existing = cursor.fetchone()
        
    if existing:
        # Se o status mudou para Concluído ('O') e não tinha data_fechamento, crava data_fechamento
        data_fechamento = None
        if status == 'O':
            cursor.execute("SELECT data_fechamento FROM tarefas WHERE id = ?", (existing["id"],))
            row = cursor.fetchone()
            data_fechamento = row["data_fechamento"] if row["data_fechamento"] else now_str
            
        cursor.execute("""
            UPDATE tarefas
            SET linha_sheets = COALESCE(?, linha_sheets),
                projeto = ?,
                responsavel = ?,
                assunto = ?,
                problema_contramedida = ?,
                data_vencimento = ?,
                prioridade = ?,
                status = ?,
                data_fechamento = ?
            WHERE id = ?
        """, (
            task_data.get("linha_sheets"),
            task_data.get("projeto", ""),
            task_data.get("responsavel", ""),
            task_data.get("assunto", ""),
            task_data.get("problema_contramedida", ""),
            task_data.get("data_vencimento", ""),
            task_data.get("prioridade", 2),
            status,
            data_fechamento,
            existing["id"]
        ))
        task_id = existing["id"]
    else:
        # Novo registro
        data_entrada = now_str
        data_fechamento = now_str if status == 'O' else None
        
        cursor.execute("""
            INSERT INTO tarefas (
                google_task_id, linha_sheets, projeto, responsavel, assunto, 
                problema_contramedida, data_vencimento, prioridade, status, 
                data_entrada, data_fechamento
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            google_id,
            task_data.get("linha_sheets"),
            task_data.get("projeto", ""),
            task_data.get("responsavel", ""),
            task_data.get("assunto", ""),
            task_data.get("problema_contramedida", ""),
            task_data.get("data_vencimento", ""),
            task_data.get("prioridade", 2),
            status,
            data_entrada,
            data_fechamento
        ))
        task_id = cursor.lastrowid
        
    conn.commit()
    conn.close()
    return task_id

def get_all_tasks(include_completed=False):
    """
    Retorna a lista de tarefas registradas no SQLite.
    Se include_completed for False, filtra apenas tarefas com status != 'O'.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if include_completed:
        cursor.execute("SELECT * FROM tarefas ORDER BY prioridade ASC, id DESC")
    else:
        cursor.execute("SELECT * FROM tarefas WHERE status != 'O' ORDER BY prioridade ASC, id DESC")
        
    rows = cursor.fetchall()
    conn.close()
    
    # Converte os Rows do SQLite em dicionários comuns do Python
    tasks = []
    for row in rows:
        tasks.append(dict(row))
    return tasks

def get_task_by_id(task_id):
    """
    Busca uma única tarefa pelo ID do banco de dados local.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM tarefas WHERE id = ?", (task_id,))
    row = cursor.fetchone()
    conn.close()
    
    return dict(row) if row else None

def get_task_by_google_id(google_id):
    """
    Busca uma única tarefa pelo ID do Google Tasks.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM tarefas WHERE google_task_id = ?", (google_id,))
    row = cursor.fetchone()
    conn.close()
    
    return dict(row) if row else None

def update_linha_sheets(google_task_id, row_num):
    """
    Atualiza rapidamente qual é a linha física correspondente no Google Sheets.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE tarefas SET linha_sheets = ? WHERE google_task_id = ?", (row_num, google_task_id))
    conn.commit()
    conn.close()
