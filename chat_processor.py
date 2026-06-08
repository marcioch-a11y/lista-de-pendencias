import os
import json
import requests
from dotenv import load_dotenv
from google import genai
from google.genai import types
from typing import Optional
import config
import database
import sheets_service

# Garante o carregamento das variáveis de ambiente
load_dotenv()

def atualizar_data_e_status_tarefa(id_tarefa: int, nova_data: Optional[str] = None, novo_status: Optional[str] = None) -> str:
    """
    Atualiza a data de vencimento e/ou o status de uma tarefa no banco de dados local SQLite
    e espelha imediatamente no Google Sheets e no Google Tasks.

    Args:
        id_tarefa: O ID numérico local da tarefa no SQLite (ex: 5).
        nova_data: A nova data de vencimento no formato YYYY-MM-DD (ou None se não quiser alterar).
        novo_status: O novo status da tarefa, aceitando estritamente '△', 'O' ou 'X' (ou None se não quiser alterar).
    """
    try:
        task = database.get_task_by_id(id_tarefa)
        if not task:
            return f"Erro: Tarefa ID {id_tarefa} não encontrada no banco SQLite local."
            
        # Poka-Yoke: Validação estrita de status
        if novo_status is not None:
            if novo_status not in ['△', 'O', 'X']:
                return f"Erro: Status '{novo_status}' inválido. Deve ser estritamente '△', 'O' ou 'X'."
        else:
            novo_status = task.get("status")
            
        # Formata data se fornecida
        if nova_data is not None:
            # Converte formato brasileiro se aplicável
            if "/" in nova_data:
                parts = nova_data.split("/")
                if len(parts) == 3:
                    nova_data = f"{parts[2]}-{parts[1].zfill(2)}-{parts[0].zfill(2)}"
            # Validação simples
            if nova_data and not (len(nova_data) == 10 and nova_data[4] == '-' and nova_data[7] == '-'):
                return f"Erro: Formato de data '{nova_data}' inválido. Use YYYY-MM-DD."
        else:
            nova_data = task.get("data_vencimento")
            
        # Salva no SQLite local
        db_task = {
            "google_task_id": task.get("google_task_id"),
            "linha_sheets": task.get("linha_sheets"),
            "projeto": task.get("projeto"),
            "responsavel": task.get("responsavel"),
            "assunto": task.get("assunto"),
            "problema_contramedida": task.get("problema_contramedida"),
            "data_vencimento": nova_data,
            "prioridade": task.get("prioridade"),
            "status": novo_status
        }
        database.save_or_update_task(db_task)
        
        # Sincroniza no Sheets
        concluido = "sim" if novo_status == 'O' else "nao"
        dmy = ""
        if nova_data:
            parts = nova_data.split("-")
            if len(parts) == 3:
                dmy = f"{parts[2]}/{parts[1]}/{parts[0]}"
            else:
                dmy = nova_data
                
        fields_sheets = {
            "Status": novo_status,
            "Due Date": dmy,
            "concluido": concluido
        }
        sheets_service.update_task_in_sheet(task.get("google_task_id"), fields_sheets)
        
        # Sincroniza no Google Tasks se concluída
        google_tasks_msg = ""
        if novo_status == 'O' and task.get("google_task_id"):
            try:
                import tasks_service
                tasks_service.complete_task(task.get("google_task_id"))
                google_tasks_msg = " e Google Tasks"
            except Exception as e:
                google_tasks_msg = f" (erro ao sincronizar no Google Tasks: {e})"
                
        return f"Sucesso: Tarefa ID {id_tarefa} atualizada para Status: '{novo_status}' e Data: '{nova_data}' no SQLite, Sheets{google_tasks_msg}."
    except Exception as e:
        return f"Erro ao atualizar a tarefa ID {id_tarefa}: {e}"

def run_chat_session(message: str, provider: str = None) -> dict:
    """
    Executa uma sessão de chat com a IA selecionada (Gemini ou Local LLM).
    Injeta o estado atual das tarefas ativas no prompt do sistema.
    Suporta function calling determinístico (AFC desabilitado para Gemini).
    """
    from datetime import datetime
    
    selected_provider = provider or config.LLM_PROVIDER
    
    # 1. Carrega tarefas ativas para o contexto do sistema
    active_tasks = database.get_all_tasks(include_completed=False)
    
    # Para o LLM Local, limitamos as tarefas a 35 para caber no contexto de 4096 tokens
    if selected_provider == "local" and len(active_tasks) > 35:
        active_tasks = sorted(active_tasks, key=lambda x: (x.get("prioridade", 2), -x.get("id", 0)))[:35]
        
    tasks_lines = []
    for t in active_tasks:
        proj = t["projeto"][:40] if t["projeto"] else ""
        resp = t["responsavel"][:20] if t["responsavel"] else ""
        assunto = t["assunto"][:40] if t["assunto"] else ""
        tasks_lines.append(f"ID:{t['id']}|Projeto:{proj}|Responsável:{resp}|Assunto:{assunto}|Status:{t['status']}")
    tasks_str = "\n".join(tasks_lines)
    
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    system_prompt = (
        "Você é o Engenheiro de Operações do ecossistema Clawdbot da Amaya Agro.\n"
        f"Hoje é: {today_str}\n\n"
        "Seu papel é ajudar o operador na gestão visual e cronograma do Andon.\n"
        "Abaixo está a lista atualizada de tarefas ativas (não concluídas) cadastradas no banco de dados local SQLite (no formato 'ID:<id>|Projeto:<projeto>|Responsável:<responsável>|Assunto:<assunto>|Status:<status>'):\n"
        "--- TAREFAS ATIVAS ---\n"
        f"{tasks_str}\n"
        "----------------------\n\n"
        "Regras Operacionais e Poka-Yoke:\n"
        "1. Se o usuário pedir análises, faça um resumo focando nos gargalos (tarefas com status 'X' ou com prioridade 1).\n"
        "2. Se o usuário der uma instrução de alteração (ex: 'Adie a tarefa 5 para dia 25/06', 'Marque o aniversário do Diego como concluído', 'Bloqueie a tarefa do CRM'), você DEVE obrigatoriamente chamar a função `atualizar_data_e_status_tarefa` com os argumentos corretos.\n"
        "3. Para chamar a função, você precisa do `id` (ID local inteiro) da tarefa. Mapeie o texto do usuário para o assunto das tarefas da lista.\n"
        "4. Se houver qualquer ambiguidade (ex: duas tarefas similares ou o assunto não bater claramente), PARE e pergunte o ID exato ao usuário antes de tomar qualquer ação.\n"
        "5. O status só aceita '△' (em andamento), 'O' (concluído) e 'X' (bloqueado/deu problema). Mapeie termos como 'concluir', 'feito', 'pronto' para 'O'; 'bloqueado', 'deu problema', 'erro' para 'X'; e 'andamento', 'iniciado' para '△'.\n"
        "6. Retorne sempre respostas claras, concisas e em Português do Brasil."
    )
    
    if selected_provider == "local":
        # System prompt específico para o LLM Local instruindo o JSON fallback
        local_system_prompt = system_prompt + (
            "\n\nIMPORTANTE (Regra de Ação): Se você decidir que precisa atualizar uma tarefa (data ou status), "
            "responda ESTRITAMENTE com um objeto JSON no formato abaixo, sem nenhum outro texto explicativo antes ou depois:\n"
            "{\n"
            "  \"action\": \"atualizar_data_e_status_tarefa\",\n"
            "  \"id_tarefa\": <id_da_tarefa_inteiro>,\n"
            "  \"nova_data\": \"YYYY-MM-DD\" ou null,\n"
            "  \"novo_status\": \"△\" ou \"O\" ou \"X\" ou null\n"
            "}\n"
            "Se for apenas uma saudação, dúvida ou análise geral, responda normalmente com texto corrido."
        )

        headers = {"Content-Type": "application/json"}
        payload = {
            "model": config.LOCAL_LLM_MODEL,
            "messages": [
                {"role": "system", "content": local_system_prompt},
                {"role": "user", "content": message}
            ],
            "temperature": 0.0,
            "max_tokens": 400
        }
        
        try:
            response = requests.post(config.LOCAL_LLM_URL, headers=headers, json=payload, timeout=120)
            response.raise_for_status()
            resp_data = response.json()
            
            content = resp_data["choices"][0]["message"]["content"].strip()
            
            # Tenta verificar se o conteúdo possui um padrão JSON de ação
            if "atualizar_data_e_status_tarefa" in content:
                start_idx = content.find("{")
                end_idx = content.rfind("}")
                if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                    json_str = content[start_idx:end_idx + 1]
                    try:
                        action_data = json.loads(json_str)
                        if action_data.get("action") == "atualizar_data_e_status_tarefa":
                            id_tarefa = int(action_data.get("id_tarefa"))
                            nova_data = action_data.get("nova_data")
                            novo_status = action_data.get("novo_status")
                            
                            result_str = atualizar_data_e_status_tarefa(id_tarefa, nova_data, novo_status)
                            return {
                                "message": f"Ação executada localmente: {result_str}",
                                "action_taken": {
                                    "name": "atualizar_data_e_status_tarefa",
                                    "args": {"id_tarefa": id_tarefa, "nova_data": nova_data, "novo_status": novo_status},
                                    "result": result_str
                                }
                            }
                    except Exception as json_err:
                        print(f"Erro ao parsear JSON de ação do LLM Local: {json_err}")
            
            # Se não teve chamada de função, retorna a resposta de texto
            return {"message": content}
            
        except Exception as e:
            return {"error": f"Erro na LLM Local: {e}"}
            
    else:
        # Chamada usando o Gemini (com AFC desativado para interceptar a ação)
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            return {"error": "A variável GEMINI_API_KEY não está configurada no ambiente."}
            
        client = genai.Client(api_key=api_key)
        
        try:
            response = client.models.generate_content(
                model=config.GEMINI_MODEL,
                contents=message,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    tools=[atualizar_data_e_status_tarefa],
                    automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
                    temperature=0.0
                )
            )
            
            if response.function_calls:
                for call in response.function_calls:
                    if call.name == "atualizar_data_e_status_tarefa":
                        args = call.args
                        id_tarefa = int(args.get("id_tarefa"))
                        nova_data = args.get("nova_data")
                        novo_status = args.get("novo_status")
                        
                        result_str = atualizar_data_e_status_tarefa(id_tarefa, nova_data, novo_status)
                        return {
                            "message": f"Ação executada: {result_str}",
                            "action_taken": {
                                "name": "atualizar_data_e_status_tarefa",
                                "args": {"id_tarefa": id_tarefa, "nova_data": nova_data, "novo_status": novo_status},
                                "result": result_str
                            }
                        }
            
            # Se não teve chamada de função, retorna a resposta de texto
            return {"message": response.text.strip()}
            
        except Exception as e:
            return {"error": f"Erro no Gemini: {e}"}
