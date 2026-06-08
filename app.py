import os
import sys
import socket
import subprocess
from flask import Flask, jsonify, request, render_template_string

# Importa os módulos locais do projeto
import config
import sheets_service

app = Flask(__name__)

@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response

# Base path definitions
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DE_DADOS_PATH = os.path.join(BASE_DIR, "base_de_dados.md")
CONFIG_PATH = os.path.join(BASE_DIR, "config.py")

def get_local_ip():
    """Descobre o endereço IP local do computador na rede Wi-Fi/Ethernet."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('10.255.255.255', 1))
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip

def get_current_provider():
    """Lê o provedor de LLM atualmente configurado no config.py."""
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("LLM_PROVIDER ="):
                    # Extrai a string ex: "gemini" ou "local"
                    return line.split("=")[1].strip().replace('"', '').replace("'", "")
    except Exception:
        pass
    return "gemini"

def update_config_provider(provider):
    """Atualiza a linha do LLM_PROVIDER no config.py."""
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            content = f.read()
            
        # Encontra a linha antiga e substitui
        lines = content.splitlines()
        for i, line in enumerate(lines):
            if line.startswith("LLM_PROVIDER ="):
                lines[i] = f'LLM_PROVIDER = "{provider}"'
                break
                
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        return True
    except Exception as e:
        print(f"Erro ao salvar configuração: {e}")
        return False

# Rota principal - Serve a página web responsiva
@app.route("/")
def index():
    # Carregaremos o HTML dinamicamente a partir de um arquivo estático para ficar organizado
    html_path = os.path.join(BASE_DIR, "index.html")
    if os.path.exists(html_path):
        with open(html_path, "r", encoding="utf-8") as f:
            return render_template_string(f.read())
    return "<h1>Interface index.html não encontrada!</h1>"

# API: Retorna as configurações e endereços de rede
@app.route("/api/status", methods=["GET"])
def api_status():
    local_ip = get_local_ip()
    provider = get_current_provider()
    
    # Verifica se a base de dados existe
    db_exists = os.path.exists(BASE_DE_DADOS_PATH)
    
    return jsonify({
        "local_ip": local_ip,
        "local_url": f"http://{local_ip}:5080",
        "provider": provider,
        "base_de_dados_exists": db_exists
    })

# API: Altera o provedor de IA (Gemini ou Local)
@app.route("/api/config", methods=["POST"])
def api_update_config():
    data = request.json or {}
    new_provider = data.get("provider")
    if new_provider not in ["gemini", "local"]:
        return jsonify({"error": "Provedor inválido"}), 400
        
    success = update_config_provider(new_provider)
    if success:
        return jsonify({"success": True, "provider": new_provider})
    return jsonify({"error": "Falha ao gravar arquivo de configuração"}), 500

# API: Lê o conteúdo de base_de_dados.md
@app.route("/api/base-de-dados", methods=["GET"])
def api_get_db():
    if not os.path.exists(BASE_DE_DADOS_PATH):
        return jsonify({"content": "# 🧠 Base de Dados Master\nAdicione suas regras aqui..."})
    try:
        with open(BASE_DE_DADOS_PATH, "r", encoding="utf-8") as f:
            return jsonify({"content": f.read()})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# API: Salva alterações em base_de_dados.md
@app.route("/api/base-de-dados", methods=["POST"])
def api_save_db():
    data = request.json or {}
    content = data.get("content", "")
    try:
        with open(BASE_DE_DADOS_PATH, "w", encoding="utf-8") as f:
            f.write(content)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# API: Executa a importação das Tarefas do Google Tasks -> Sheets (main.py)
@app.route("/api/sync/to-sheets", methods=["POST"])
def api_sync_to_sheets():
    try:
        # Roda o main.py como subprocesso e captura os logs
        result = subprocess.run(
            [sys.executable, "-u", "main.py"],
            cwd=BASE_DIR,
            capture_output=True,
            text=True,
            encoding="utf-8"
        )
        return jsonify({
            "success": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# API: Executa a sincronização reversa: Sheets -> Google Tasks (sync_to_tasks.py)
@app.route("/api/sync/to-tasks", methods=["POST"])
def api_sync_to_tasks():
    try:
        # Roda o sync_to_tasks.py como subprocesso e captura os logs
        result = subprocess.run(
            [sys.executable, "-u", "sync_to_tasks.py"],
            cwd=BASE_DIR,
            capture_output=True,
            text=True,
            encoding="utf-8"
        )
        return jsonify({
            "success": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# API: Retorna todas as tarefas registradas na planilha
@app.route("/api/tasks", methods=["GET"])
def api_get_tasks():
    try:
        sheets_api = sheets_service.get_sheets_service()
        range_name = f"{config.SHEET_NAME}!A1:Z1000"
        result = sheets_api.spreadsheets().values().get(
            spreadsheetId=config.SPREADSHEET_ID,
            range=range_name
        ).execute()
        rows = result.get("values", [])
        if not rows or len(rows) <= 1:
            return jsonify([])
        
        headers = [str(h).strip() for h in rows[0]]
        tasks = []
        for row in rows[1:]:
            task_dict = {}
            for idx, header in enumerate(headers):
                if idx < len(row):
                    task_dict[header] = row[idx]
                else:
                    task_dict[header] = ""
            tasks.append(task_dict)
        return jsonify(tasks)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# API: Retorna as opções cadastradas nas abas de apoio
@app.route("/api/options", methods=["GET"])
def api_get_options():
    try:
        projetos = sheets_service.get_support_sheet_options("Projetos")
        assuntos = sheets_service.get_support_sheet_options("Assuntos")
        responsaveis = sheets_service.get_support_sheet_options("profissionais")
        return jsonify({
            "projetos": projetos,
            "assuntos": assuntos,
            "responsaveis": responsaveis
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# API: Adiciona uma nova opção a uma aba de apoio
@app.route("/api/options/add", methods=["POST"])
def api_add_option():
    data = request.json or {}
    tipo = data.get("tipo")
    valor = data.get("valor")
    if not tipo or not valor:
        return jsonify({"error": "Parâmetros 'tipo' e 'valor' são obrigatórios."}), 400
        
    sheet_map = {
        "projeto": "Projetos",
        "assunto": "Assuntos",
        "responsavel": "profissionais"
    }
    sheet_title = sheet_map.get(tipo.lower())
    if not sheet_title:
        return jsonify({"error": f"Tipo '{tipo}' inválido."}), 400
        
    success = sheets_service.add_support_sheet_option(sheet_title, valor)
    if success:
        return jsonify({"success": True})
    return jsonify({"error": "Falha ao adicionar a opção."}), 500

# API: Atualiza uma tarefa existente na planilha
@app.route("/api/tasks/update", methods=["POST"])
def api_update_task():
    data = request.json or {}
    task_id = data.get("id")
    fields = data.get("fields", {})
    if not task_id:
        return jsonify({"error": "O parâmetro 'id' é obrigatório."}), 400
        
    success = sheets_service.update_task_in_sheet(task_id, fields)
    if success:
        return jsonify({"success": True})
    return jsonify({"error": "Falha ao atualizar a tarefa na planilha."}), 500

# API: Atualiza múltiplas tarefas na planilha em lote (bulk)
@app.route("/api/tasks/bulk-update", methods=["POST"])
def api_bulk_update_tasks():
    data = request.json or {}
    tasks_list = data.get("tasks", [])
    if not isinstance(tasks_list, list):
        return jsonify({"error": "O parâmetro 'tasks' deve ser uma lista."}), 400
        
    success = sheets_service.bulk_update_tasks_in_sheet(tasks_list)
    if success:
        return jsonify({"success": True})
    return jsonify({"error": "Falha ao atualizar as tarefas na planilha."}), 500

# API: Conclui uma tarefa na planilha (define concluido = "sim")
@app.route("/api/tasks/concluir", methods=["POST"])
def api_concluir_task():
    data = request.json or {}
    task_id = data.get("id")
    if not task_id:
        return jsonify({"error": "O parâmetro 'id' é obrigatório."}), 400
        
    success = sheets_service.update_task_in_sheet(task_id, {"concluido": "sim"})
    if success:
        return jsonify({"success": True})
    return jsonify({"error": "Falha ao concluir a tarefa na planilha."}), 500

if __name__ == "__main__":
    # Garante a criação e migração das abas de apoio ao iniciar o servidor
    try:
        sheets_service.ensure_support_sheets_exist_and_migrate()
    except Exception as e:
        print(f"Aviso: Erro ao realizar migração inicial de abas: {e}")
        
    # Roda ouvindo em 0.0.0.0 para aceitar conexões de celulares e tablets na mesma rede
    app.run(host="0.0.0.0", port=5080, debug=True)
