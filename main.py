import os
import sys
from dotenv import load_dotenv
import tasks_service
import sheets_service
from llm_processor import process_task_with_llm

def main():
    # Carrega variáveis de ambiente do arquivo .env (caso exista localmente)
    load_dotenv()

    # Validação inicial da API Key do Gemini
    if not os.environ.get("GEMINI_API_KEY"):
        print("Erro: A variável de ambiente 'GEMINI_API_KEY' não está definida.")
        print("Crie um arquivo '.env' na raiz do projeto com:")
        print("GEMINI_API_KEY=sua_chave_do_google_ai_studio")
        print("\nOu defina a variável diretamente no seu terminal antes de rodar o script.")
        sys.exit(1)

    print("=== INICIANDO INTEGRAÇÃO GOOGLE TASKS -> GEMINI -> GOOGLE SHEETS ===\n")

    # 1. Autenticação e busca de tarefas do Google Tasks
    try:
        pending_tasks = tasks_service.get_pending_tasks()
    except FileNotFoundError as fnf:
        print(fnf)
        sys.exit(1)
    except Exception as e:
        print(f"Erro ao conectar ou ler do Google Tasks: {e}")
        sys.exit(1)

    if not pending_tasks:
        print("Nenhuma tarefa ativa encontrada no Google Tasks. Processo concluído.")
        return

    # 2. Inicialização da planilha e leitura de tarefas já existentes (controle de duplicados)
    try:
        headers, imported_ids, recent_examples = sheets_service.setup_and_get_imported_ids()
    except Exception as e:
        print(f"Erro ao conectar ou preparar o Google Sheets: {e}")
        sys.exit(1)

    # 3. Filtrar tarefas para ignorar as que já foram importadas anteriormente
    new_tasks = [task for task in pending_tasks if task["id"] not in imported_ids]
    
    print(f"\nTarefas pendentes totais: {len(pending_tasks)}")
    print(f"Tarefas já importadas (filtradas): {len(imported_ids)}")
    print(f"Novas tarefas a processar: {len(new_tasks)}")

    if not new_tasks:
        print("\nNenhuma nova tarefa para importar. Processo finalizado com sucesso.")
        return

    # 4. Enviar cada nova tarefa para o cérebro da LLM estruturar os dados e salvar imediatamente
    print("\n--- Iniciando análise e estruturação de texto com Gemini ---")
    
    # Descobre o número da próxima linha livre inicial
    try:
        service = sheets_service.get_sheets_service()
        result = service.spreadsheets().values().get(
            spreadsheetId=sheets_service.config.SPREADSHEET_ID,
            range=f"{sheets_service.config.SHEET_NAME}!A1:A1000"
        ).execute()
        current_rows = result.get("values", [])
        next_row_num = len(current_rows) + 1
    except Exception as e:
        print(f"Erro ao obter a próxima linha da planilha: {e}")
        sys.exit(1)

    inserted_count = 0
    for idx, task in enumerate(new_tasks, 1):
        print(f"\n[{idx}/{len(new_tasks)}] Processando: '{task['title']}'")
        try:
            # Envia título, notas e exemplos do histórico para extração inteligente
            structured_data = process_task_with_llm(task["title"], task["notes"], recent_examples=recent_examples)
            
            # Converte a resposta estruturada para dicionário e anexa o ID da tarefa original
            task_payload = structured_data.model_dump()
            task_payload["id"] = task["id"]
            
            # Se a tarefa possuir uma tarefa Pai, o nome do pai é obrigatoriamente o nome do projeto
            if task.get("parent_title"):
                task_payload["projeto"] = task["parent_title"]
            
            # Print de progresso das informações extraídas
            print(f"  -> Assunto: '{task_payload['assunto']}'")
            print(f"  -> Projeto: '{task_payload['projeto'] or '[Em Branco]'}'")
            print(f"  -> Problema/Contramedida: '{task_payload['problema_contramedida']}'")
            print(f"  -> Responsável: '{task_payload['responsavel'] or '[Em Branco]'}'")
            print(f"  -> Due Date: '{task_payload['due_date'] or '[Em Branco]'}'")
            print(f"  -> Prioridade: '{task_payload['prioridade']}'")
            print(f"  -> Status: '{task_payload['status']}'")
            
            # Escreve imediatamente no Sheets
            sheets_service.append_single_task(task_payload, headers=headers, next_row_num=next_row_num)
            next_row_num += 1
            inserted_count += 1
            
            # Sugestão de enriquecimento da base de dados caso campos fiquem em branco
            missing_fields = []
            if not task_payload.get("projeto"):
                missing_fields.append("Projeto")
            if not task_payload.get("responsavel"):
                missing_fields.append("Responsável")
            if missing_fields:
                print(f"  -> [Dica] {', '.join(missing_fields)} em branco. Adicione palavras-chave em 'base_de_dados.md' para automatizar no futuro!")
            
        except Exception as e:
            print(f"  -> Erro ao processar/salvar esta tarefa: {e}")
            print("  -> Esta tarefa será pulada nesta execução.")

    if inserted_count > 0:
        print(f"\n=== SUCESSO! {inserted_count} novas linhas inseridas no Quadro Andon no Google Sheets. ===")
    else:
        print("\nNenhuma nova tarefa foi adicionada nesta execução.")

if __name__ == "__main__":
    main()
