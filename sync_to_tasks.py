import sys
import os
from datetime import datetime
from dotenv import load_dotenv

# Garante acesso aos módulos do projeto
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import config
import google_auth
import sheets_service

def format_date_to_rfc3339(date_str):
    """Converte DD/MM/AAAA para o formato RFC3339 exigido pela API do Google Tasks."""
    if not date_str or not date_str.strip():
        return None
    try:
        dt = datetime.strptime(date_str.strip(), "%d/%m/%Y")
        return dt.strftime("%Y-%m-%dT00:00:00.000Z")
    except Exception:
        return None

def sync_sheets_to_tasks():
    print("=== INICIANDO SINCRONIZAÇÃO REVERSA: SHEETS -> GOOGLE TASKS ===\n")
    
    load_dotenv()
    
    # 1. Conecta aos serviços
    try:
        sheets_api = sheets_service.get_sheets_service()
        tasks_api = google_auth.get_service("tasks", "v1")
    except Exception as e:
        print(f"Erro ao conectar com as APIs do Google: {e}")
        return

    # 2. Lê os dados atuais da planilha
    range_name = f"{config.SHEET_NAME}!A1:Z1000"
    try:
        result = sheets_api.spreadsheets().values().get(
            spreadsheetId=config.SPREADSHEET_ID,
            range=range_name
        ).execute()
    except Exception as e:
        print(f"Erro ao ler a planilha: {e}")
        return

    rows = result.get("values", [])
    if not rows or len(rows) <= 1:
        print("Nenhum dado encontrado na planilha para sincronizar.")
        return

    headers = [str(h).strip() for h in rows[0]]
    
    # Verifica a existência das colunas necessárias
    required_cols = ["Assunto", "Projeto", "Problema/contramedida", "Responsável", "Due Date", "prioridade", "Status", "ID Tarefa"]
    for col in required_cols:
        if col not in headers:
            print(f"Erro: Coluna obrigatória '{col}' não encontrada nos cabeçalhos da planilha.")
            return

    # Mapeamento de índices de coluna
    col_idx = {col: headers.index(col) for col in required_cols}
    col_letters = ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L", "M", "N", "O", "P"]
    id_col_letter = col_letters[col_idx["ID Tarefa"]]
    
    print(f"Total de linhas na planilha para verificar: {len(rows) - 1}")
    updated_count = 0

    # 3. Varre cada linha da planilha e sincroniza no Google Tasks
    for idx, row in enumerate(rows[1:], 2):
        # Verifica se temos o ID da tarefa ou se ela é nova
        task_id = ""
        if len(row) > col_idx["ID Tarefa"]:
            task_id = str(row[col_idx["ID Tarefa"]]).strip()
            
        is_new = not task_id or task_id.startswith("NEW_")
            
        # Extrai os dados da planilha
        assunto = str(row[col_idx["Assunto"]]).strip() if len(row) > col_idx["Assunto"] else ""
        if not assunto:
            continue # Pula linhas sem assunto
            
        projeto = str(row[col_idx["Projeto"]]).strip() if len(row) > col_idx["Projeto"] else ""
        problema = str(row[col_idx["Problema/contramedida"]]).strip() if len(row) > col_idx["Problema/contramedida"] else ""
        responsavel = str(row[col_idx["Responsável"]]).strip() if len(row) > col_idx["Responsável"] else ""
        due_date = str(row[col_idx["Due Date"]]).strip() if len(row) > col_idx["Due Date"] else ""
        prioridade = str(row[col_idx["prioridade"]]).strip() if len(row) > col_idx["prioridade"] else ""
        status = str(row[col_idx["Status"]]).strip() if len(row) > col_idx["Status"] else ""

        if is_new:
            print(f"\nCriando nova tarefa no Google Tasks: '{assunto[:30]}'")
        else:
            print(f"\nVerificando tarefa ID: {task_id[:10]}... ('{assunto[:30]}')")

        try:
            # Reconstrói as anotações organizadas para o Google Tasks
            notes_payload = f"{problema}\n\n---\nProjeto: {projeto}\nResponsável: {responsavel}\nPrioridade: {prioridade}\nStatus: {status}"
            
            # Monta o corpo da requisição de atualização
            task_body = {
                "title": assunto,
                "notes": notes_payload
            }

            # Configura a data se estiver no formato correto
            formatted_due = format_date_to_rfc3339(due_date)
            if formatted_due:
                task_body["due"] = formatted_due

            # Sincroniza a conclusão da tarefa
            if status.upper() == "O":
                task_body["status"] = "completed"
            else:
                task_body["status"] = "needsAction"

            if is_new:
                # Cria a nova tarefa no Google Tasks
                created_task = tasks_api.tasks().insert(
                    tasklist=config.TASKS_LIST_ID,
                    body=task_body
                ).execute()
                
                new_id = created_task.get("id")
                print(f"  -> Nova tarefa criada com ID: {new_id[:10]}...")
                
                # Escreve o ID gerado de volta na planilha para esta linha
                sheets_api.spreadsheets().values().update(
                    spreadsheetId=config.SPREADSHEET_ID,
                    range=f"{config.SHEET_NAME}!{id_col_letter}{idx}",
                    valueInputOption="USER_ENTERED",
                    body={"values": [[new_id]]}
                ).execute()
            else:
                # Atualiza tarefa existente
                tasks_api.tasks().patch(
                    tasklist=config.TASKS_LIST_ID,
                    task=task_id,
                    body=task_body
                ).execute()
                print(f"  -> Sincronizado com sucesso no Google Tasks!")
                
            updated_count += 1

        except Exception as e:
            msg_type = "criar" if is_new else "atualizar"
            print(f"  -> Erro ao {msg_type} tarefa no Google Tasks: {e}")

    print(f"\n=== SUCESSO! {updated_count} tarefas processadas no seu Google Tasks. ===")

if __name__ == "__main__":
    sync_sheets_to_tasks()
