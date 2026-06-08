import os
import sys
import socket
import subprocess
from datetime import datetime
from flask import Flask, jsonify, request, render_template_string, redirect, send_from_directory
from dotenv import load_dotenv

# Carrega variáveis de ambiente do arquivo .env
load_dotenv()

# Importa os módulos locais do projeto
import config
import sheets_service
import database

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
GANTT_PROJECTS_PATH = os.path.join(BASE_DIR, "gantt_projects.json")

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
        # Lê o provedor enviado na requisição (via JSON ou Query Param)
        req_data = request.json or {}
        provider = req_data.get("provider") or request.args.get("provider")
        
        args = [sys.executable, "-u", "main.py"]
        if provider in ["gemini", "local"]:
            args.extend(["--provider", provider])

        # Roda o main.py como subprocesso e captura os logs
        result = subprocess.run(
            args,
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

def map_sqlite_to_andon_format(db_task):
    # Converte YYYY-MM-DD para DD/MM/YYYY para o Andon UI
    ymd = db_task.get("data_vencimento") or ""
    dmy = ""
    if ymd and "-" in ymd:
        parts = ymd.split("-")
        if len(parts) == 3:
            dmy = f"{parts[2]}/{parts[1]}/{parts[0]}"
        else:
            dmy = ymd
    else:
        dmy = ymd
        
    return {
        "id": db_task.get("id"),
        "ID Tarefa": db_task.get("google_task_id") or "",
        "Projeto": db_task.get("projeto") or "",
        "Responsável": db_task.get("responsavel") or "",
        "Assunto": db_task.get("assunto") or "",
        "Problema/contramedida": db_task.get("problema_contramedida") or "",
        "Due Date": dmy,
        "prioridade": str(db_task.get("prioridade") or "2"),
        "Status": db_task.get("status") or "△",
        "concluido": "sim" if db_task.get("status") == "O" else "nao"
    }

def sync_sheets_to_sqlite():
    """
    Sincroniza os dados do Google Sheets para o SQLite.
    Garante que alterações na planilha reflitam no banco local.
    """
    try:
        sheets_api = sheets_service.get_sheets_service()
        range_name = f"{config.SHEET_NAME}!A1:Z1000"
        result = sheets_api.spreadsheets().values().get(
            spreadsheetId=config.SPREADSHEET_ID,
            range=range_name
        ).execute()
        rows = result.get("values", [])
        if not rows or len(rows) <= 1:
            return
        
        headers = [str(h).strip() for h in rows[0]]
        try:
            id_col_idx = headers.index("ID Tarefa")
        except ValueError:
            return
            
        for idx, row in enumerate(rows[1:], start=2):
            if len(row) <= id_col_idx:
                continue
            google_id = str(row[id_col_idx]).strip()
            if not google_id:
                continue
                
            task_dict = {}
            for h_idx, header in enumerate(headers):
                if h_idx < len(row):
                    task_dict[header] = row[h_idx]
                else:
                    task_dict[header] = ""
                    
            status = task_dict.get("Status", "△")
            if status not in ['△', 'O', 'X']:
                status = '△'
            if task_dict.get("concluido") == "sim":
                status = 'O'
                
            try:
                prio = int(task_dict.get("prioridade", 2))
            except ValueError:
                prio = 2
                
            dmy = task_dict.get("Due Date", "")
            ymd = ""
            if dmy:
                parts = dmy.split("/")
                if len(parts) == 3:
                    ymd = f"{parts[2]}-{parts[1].zfill(2)}-{parts[0].zfill(2)}"
                else:
                    ymd = dmy
                    
            db_task = {
                "google_task_id": google_id,
                "linha_sheets": idx,
                "projeto": task_dict.get("Projeto", ""),
                "responsavel": task_dict.get("Responsável", ""),
                "assunto": task_dict.get("Assunto", ""),
                "problema_contramedida": task_dict.get("Problema/contramedida", ""),
                "data_vencimento": ymd,
                "prioridade": prio,
                "status": status
            }
            database.save_or_update_task(db_task)
    except Exception as e:
        print(f"Erro ao sincronizar do Sheets para SQLite: {e}")

# API: Retorna todas as tarefas registradas na planilha (usando SQLite)
@app.route("/api/tasks", methods=["GET"])
def api_get_tasks():
    try:
        sync_sheets_to_sqlite()
        db_tasks = database.get_all_tasks(include_completed=False)
        andon_tasks = [map_sqlite_to_andon_format(t) for t in db_tasks]
        return jsonify(andon_tasks)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# API: Retorna todas as tarefas locais do SQLite (para o Gantt)
@app.route("/api/tarefas", methods=["GET"])
def api_get_all_tarefas():
    try:
        sync_sheets_to_sqlite()
        include_comp = request.args.get("include_completed", "false").lower() == "true"
        tasks = database.get_all_tasks(include_completed=include_comp)
        return jsonify(tasks)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# API: Cria uma nova tarefa no SQLite e adiciona no Sheets
@app.route("/api/tarefas", methods=["POST"])
def api_create_tarefa():
    data = request.json or {}
    status = data.get("status", "△")
    # Poka-Yoke: Validação estrita do Status
    if status not in ['△', 'O', 'X']:
        return jsonify({"error": f"Status inválido: '{status}'. Deve ser estritamente '△', 'O' ou 'X'."}), 400
        
    try:
        sheets_api = sheets_service.get_sheets_service()
        result = sheets_api.spreadsheets().values().get(
            spreadsheetId=config.SPREADSHEET_ID,
            range=f"{config.SHEET_NAME}!A1:A1000"
        ).execute()
        current_rows = result.get("values", [])
        next_row_num = len(current_rows) + 1
        
        import uuid
        fake_google_id = f"LOCAL_{uuid.uuid4().hex}"
        
        db_task = {
            "google_task_id": fake_google_id,
            "linha_sheets": next_row_num,
            "projeto": data.get("projeto", ""),
            "responsavel": data.get("responsavel", ""),
            "assunto": data.get("assunto", ""),
            "problema_contramedida": data.get("problema_contramedida", ""),
            "data_vencimento": data.get("data_vencimento", ""),
            "prioridade": int(data.get("prioridade", 2)),
            "status": status
        }
        
        new_id = database.save_or_update_task(db_task)
        
        # Envia para o Sheets
        ymd = db_task.get("data_vencimento", "")
        dmy = ""
        if ymd:
            parts = ymd.split("-")
            if len(parts) == 3:
                dmy = f"{parts[2]}/{parts[1]}/{parts[0]}"
            else:
                dmy = ymd
                
        fields_sheets = {
            "assunto": db_task.get("assunto"),
            "projeto": db_task.get("projeto"),
            "problema_contramedida": db_task.get("problema_contramedida"),
            "responsavel": db_task.get("responsavel"),
            "due_date": dmy,
            "prioridade": str(db_task.get("prioridade")),
            "status": status,
            "id": fake_google_id,
            "concluido": "sim" if status == 'O' else "nao"
        }
        
        headers, _, _ = sheets_service.setup_and_get_imported_ids()
        sheets_service.append_single_task(fields_sheets, headers=headers, next_row_num=next_row_num)
        
        return jsonify({"success": True, "task": database.get_task_by_id(new_id)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# API: Detalhes de uma única tarefa por ID do SQLite
@app.route("/api/tarefas/<int:task_id>", methods=["GET"])
def api_get_tarefa_by_id(task_id):
    try:
        task = database.get_task_by_id(task_id)
        if not task:
            return jsonify({"error": "Tarefa não encontrada"}), 404
        return jsonify(task)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# API: Atualiza uma tarefa por ID no SQLite e sincroniza no Sheets/Google Tasks
@app.route("/api/tarefas/<int:task_id>", methods=["POST"])
def api_update_tarefa(task_id):
    data = request.json or {}
    try:
        task = database.get_task_by_id(task_id)
        if not task:
            return jsonify({"error": "Tarefa não encontrada"}), 404
            
        # Poka-Yoke: Validação estrita do Status
        status = data.get("status")
        if status is not None:
            if status not in ['△', 'O', 'X']:
                return jsonify({"error": f"Status inválido: '{status}'. Deve ser estritamente '△', 'O' ou 'X'."}), 400
        else:
            status = task.get("status")
            
        # Prepara o payload para atualizar no SQLite
        db_task = {
            "google_task_id": task.get("google_task_id"),
            "linha_sheets": task.get("linha_sheets"),
            "projeto": data.get("projeto", task.get("projeto")),
            "responsavel": data.get("responsavel", task.get("responsavel")),
            "assunto": data.get("assunto", task.get("assunto")),
            "problema_contramedida": data.get("problema_contramedida", task.get("problema_contramedida")),
            "data_vencimento": data.get("data_vencimento", task.get("data_vencimento")),
            "prioridade": int(data.get("prioridade")) if data.get("prioridade") is not None else task.get("prioridade"),
            "status": status
        }
        
        # Atualiza localmente no SQLite
        database.save_or_update_task(db_task)
        
        # Sincroniza para o Google Sheets
        concluido = "sim" if status == 'O' else "nao"
        
        ymd = db_task.get("data_vencimento", "")
        dmy = ""
        if ymd:
            parts = ymd.split("-")
            if len(parts) == 3:
                dmy = f"{parts[2]}/{parts[1]}/{parts[0]}"
            else:
                dmy = ymd
                
        fields_sheets = {
            "Projeto": db_task.get("projeto"),
            "Responsável": db_task.get("responsavel"),
            "Assunto": db_task.get("assunto"),
            "Problema/contramedida": db_task.get("problema_contramedida"),
            "Due Date": dmy,
            "prioridade": str(db_task.get("prioridade")),
            "Status": status,
            "concluido": concluido
        }
        
        sheets_service.update_task_in_sheet(task.get("google_task_id"), fields_sheets)
        
        # Se status mudou para 'O' (Concluído), atualiza também no Google Tasks
        if status == 'O' and task.get("google_task_id"):
            try:
                import tasks_service
                tasks_service.complete_task(task.get("google_task_id"))
            except Exception as e:
                print(f"Erro ao concluir tarefa no Google Tasks: {e}")
                
        return jsonify({"success": True, "task": database.get_task_by_id(task_id)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Rotas para servir o app React do Gantt a partir da mesma porta
@app.route('/gantt')
def redirect_gantt():
    return redirect('/gantt/')

@app.route('/gantt/')
@app.route('/gantt/<path:path>')
def serve_gantt(path='index.html'):
    if not path or path == "":
        path = "index.html"
    return send_from_directory(os.path.join(BASE_DIR, 'static', 'gantt'), path)

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
        
    # Atualiza no SQLite
    task = database.get_task_by_google_id(task_id)
    if task:
        db_task = {
            "google_task_id": task_id,
            "linha_sheets": task.get("linha_sheets"),
            "projeto": task.get("projeto"),
            "responsavel": task.get("responsavel"),
            "assunto": task.get("assunto"),
            "problema_contramedida": task.get("problema_contramedida"),
            "data_vencimento": task.get("data_vencimento"),
            "prioridade": task.get("prioridade"),
            "status": "O"  # Concluído
        }
        database.save_or_update_task(db_task)
    
    # Atualiza no Sheets
    success = sheets_service.update_task_in_sheet(task_id, {"concluido": "sim", "Status": "O"})
    
    # Atualiza no Google Tasks
    if task_id:
        try:
            import tasks_service
            tasks_service.complete_task(task_id)
        except Exception as e:
            print(f"Erro ao concluir no Google Tasks: {e}")
            
    if success:
        return jsonify({"success": True})
    return jsonify({"error": "Falha ao concluir a tarefa na planilha."}), 500

# API: Retorna todos os projetos do Gantt para sincronização
@app.route("/api/gantt/projects", methods=["GET"])
def api_get_gantt_projects():
    if not os.path.exists(GANTT_PROJECTS_PATH):
        return jsonify([])
    try:
        with open(GANTT_PROJECTS_PATH, "r", encoding="utf-8") as f:
            import json
            return jsonify(json.load(f))
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# API: Salva todos os projetos do Gantt para sincronização
@app.route("/api/gantt/projects", methods=["POST"])
def api_save_gantt_projects():
    data = request.json
    if not isinstance(data, list):
        return jsonify({"error": "Os dados devem ser uma lista de projetos"}), 400
    try:
        with open(GANTT_PROJECTS_PATH, "w", encoding="utf-8") as f:
            import json
            json.dump(data, f, indent=2, ensure_ascii=False)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# API: Chat operacional inteligente com suporte a Function Calling
@app.route("/api/chat", methods=["POST"])
def api_chat():
    data = request.json or {}
    message = data.get("message")
    provider = data.get("provider")
    
    if not message:
        return jsonify({"error": "Parâmetro 'message' é obrigatório."}), 400
        
    try:
        import chat_processor
        response_dict = chat_processor.run_chat_session(message, provider=provider)
        return jsonify(response_dict)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    # Garante a criação do banco local SQLite ao iniciar o servidor
    try:
        database.init_db()
    except Exception as e:
        print(f"Aviso: Erro ao inicializar o banco local SQLite: {e}")
        
    # Garante a criação e migração das abas de apoio ao iniciar o servidor
    try:
        sheets_service.ensure_support_sheets_exist_and_migrate()
    except Exception as e:
        print(f"Aviso: Erro ao realizar migração inicial de abas: {e}")
        
    # Roda ouvindo em 0.0.0.0 para aceitar conexões de celulares e tablets na mesma rede
    app.run(host="0.0.0.0", port=5080, debug=True, use_reloader=False)
