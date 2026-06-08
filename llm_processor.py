import os
import time
import requests
import json
from google import genai
from google.genai import types
from pydantic import BaseModel, Field
from typing import Optional
import config

# Define o modelo de saída estruturado (Pydantic V2)
class AndonTask(BaseModel):
    assunto: str = Field(
        description="Um resumo muito curto, direto e objetivo do assunto (ex: 'Comprar microfone', 'Ajuste de tabela')."
    )
    projeto: Optional[str] = Field(
        default="", 
        description="O nome do projeto. Se não tiver 100% de certeza absoluta com base no texto ou na Base de Dados, deixe o campo como string vazia."
    )
    problema_contramedida: str = Field(
        description="Descrição detalhada consolidando o problema e ações necessárias a partir do título e descrição originais."
    )
    responsavel: Optional[str] = Field(
        default="", 
        description="O nome da pessoa designada (ex: Mônica, André, Joy, Edson, Felipe Junqueira, Milton Amaya). Se não tiver 100% de certeza absoluta, deixe o campo como string vazia."
    )
    due_date: Optional[str] = Field(
        default="", 
        description="A data de vencimento no formato DD/MM/AAAA. Se o ano for omitido, assuma 2026. Se não houver data, deixe o campo como string vazia."
    )
    prioridade: int = Field(
        default=2,
        description="Definir prioridade como um inteiro de 1 a 3. 1 é mais prioritário, 3 é menos prioritário. Tente inferir a prioridade ou use 2 como padrão."
    )
    status: str = Field(
        default="△",
        description="Definir estritamente como '△' (ongoing/andamento ou tem problema não fatal) por padrão. Se indicar concluído, use 'O'. Se indicar problema crítico/bloqueado (deu M), use 'X'."
    )

def load_knowledge_base():
    """
    Carrega o arquivo de base de dados master.
    """
    kb_path = os.path.join(os.path.dirname(__file__), "base_de_dados.md")
    if os.path.exists(kb_path):
        try:
            with open(kb_path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            print(f"Aviso ao ler a base de dados master (base_de_dados.md): {e}")
    return ""

def process_task_with_local_llm(title: str, notes: str, recent_examples: list = None, valid_projects: list = None, valid_subjects: list = None, valid_responsibles: list = None) -> AndonTask:
    """
    Consome o LLM local rodando no LM Studio através de uma API compatível com OpenAI.
    Usa mensagens separadas de system e user e ativa o modo JSON.
    """
    print(f"Processando tarefa '{title[:30]}...' localmente no LM Studio ({config.LOCAL_LLM_MODEL})...")
    
    knowledge_base = load_knowledge_base()
    
    examples_str = ""
    if recent_examples:
        examples_str = "\n--- HISTÓRICO RECENTE DE MAPEAMENTOS (APRENDIZADO DINÂMICO) ---\n" + json.dumps(recent_examples, indent=2, ensure_ascii=False) + "\n"

    valid_projects_str = ", ".join([f"'{p}'" for p in valid_projects]) if valid_projects else "Nenhum"
    valid_subjects_str = ", ".join([f"'{s}'" for s in valid_subjects]) if valid_subjects else "Nenhum"
    valid_responsibles_str = ", ".join([f"'{r}'" for r in valid_responsibles]) if valid_responsibles else "Nenhum"

    system_prompt = (
        "Você é um robô de estruturação de dados especializado em melhoria contínua e Lean Data Cleanliness, "
        "atuando como assistente virtual da empresa Amaya Agro / Ribeira ML.\n"
        "Suas decisões de mapeamento (Projeto, Responsável, etc.) devem obedecer estritamente à BASE DE DADOS MASTER da empresa fornecida abaixo:\n"
        f"\n{knowledge_base}\n"
        f"{examples_str}"
        "\nRegras Lean de Extrema Limpeza e Restrição de Opções:\n"
        "1. RESTRIÇÃO ESTRITA DE VALORES: Os campos 'projeto', 'assunto' e 'responsavel' devem conter UNICAMENTE valores que constem exatamente nas listas abaixo. Se o valor ideal não constar em sua respectiva lista (ou houver qualquer incerteza), deixe o campo vazio (\"\"). Não crie novos valores de forma alguma.\n"
        f"  - Lista de Projetos Válidos: [{valid_projects_str}]\n"
        f"  - Lista de Assuntos Válidos: [{valid_subjects_str}]\n"
        f"  - Lista de Responsáveis Válidos: [{valid_responsibles_str}]\n\n"
        "2. REGRA ESTRITA DE INCERTEZA: Se você não tiver 100% de certeza absoluta sobre 'projeto', 'responsavel' ou 'due_date' com base na tarefa, na Base de Dados ou no Histórico Recente, deixe o campo correspondente obrigatoriamente como string vazia \"\". Não invente ou presuma. Não crie novos assuntos, projetos ou responsáveis.\n"
        "3. Uso de Palavras-Chave e Gatilhos: Consulte a tabela 'MAPA DE PALAVRAS-CHAVE E ASSOCIAÇÕES' e a descrição da equipe/projetos na Base de Dados. Se o Título ou Descrição contiver gatilhos ou palavras-chave ali especificadas (ex: 'Artvac', 'Easysoft', 'Joy', 'NPK'), preencha o Projeto e Responsável correspondente exatamente como mapeado na Base.\n"
        "4. Prioridade: Atribua 1 (mais prioritário) a 3 (menos prioritário). Padrão é 2.\n"
        "5. Status: '△' para em andamento/problema não-fatal (padrão), 'O' para concluído, 'X' para bloqueado/deu problema grave (deu M).\n"
        "6. Datas: Formate como DD/MM/AAAA (ano 2026). Se for uma tarefa agrícola sazonal da seção 5 da Base de Dados e não tiver prazo definido, estime um prazo curto de 7 a 14 dias. Caso contrário, deixe vazio."
    )
    
    user_content = f"""Tarefa Bruta a ser analisada:
Título: {title}
Descrição: {notes}

Retorne um JSON contendo exatamente estas chaves:
{{
  "assunto": "Resumo muito curto e objetivo",
  "projeto": "Nome do projeto ou vazio",
  "problema_contramedida": "Descrição consolidada do problema",
  "responsavel": "Nome ou vazio",
  "due_date": "DD/MM/AAAA ou vazio",
  "prioridade": 2,
  "status": "△ ou O ou X"
}}"""

    headers = {"Content-Type": "application/json"}
    payload = {
        "model": config.LOCAL_LLM_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ],
        "temperature": 0.0,
        "max_tokens": 300
    }
    
    try:
        response = requests.post(config.LOCAL_LLM_URL, headers=headers, json=payload, timeout=180)
        response.raise_for_status()
        resp_data = response.json()
        
        # Extrai o conteúdo da resposta do chat completions
        content = resp_data["choices"][0]["message"]["content"].strip()
        
        # Extrai estritamente o bloco JSON contido na resposta (caso o modelo coloque algum texto fora)
        start_idx = content.find("{")
        end_idx = content.rfind("}")
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            content = content[start_idx:end_idx + 1]
        
        # Converte para a classe Pydantic para validação
        task_data = AndonTask.model_validate_json(content)
        return task_data
    except Exception as e:
        print(f"Erro ao processar localmente via LM Studio: {e}")
        print("Certifique-se de que o LM Studio está rodando e o servidor local está ativo em http://localhost:1234")
        raise e

def process_task_with_llm(title: str, notes: str, recent_examples: list = None, provider: str = None, valid_projects: list = None, valid_subjects: list = None, valid_responsibles: list = None) -> AndonTask:
    """
    Usa a API selecionada (Gemini ou Local no LM Studio)
    para extrair os dados estruturados de uma tarefa bruta.
    Se provider for fornecido, ignora a configuração global.
    """
    selected_provider = provider or config.LLM_PROVIDER
    if selected_provider == "local":
        return process_task_with_local_llm(title, notes, recent_examples, valid_projects, valid_subjects, valid_responsibles)

    # Fluxo Padrão: Gemini API
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError(
            "Erro: A variável de ambiente 'GEMINI_API_KEY' não está definida.\n"
            "Por favor, configure esta variável com sua chave do Google AI Studio."
        )

    # Inicializa o cliente oficial google-genai
    client = genai.Client(api_key=api_key)

    knowledge_base = load_knowledge_base()
    
    examples_str = ""
    if recent_examples:
        examples_str = "\n---\nHISTÓRICO RECENTE DE MAPEAMENTOS DA PLANILHA (APRENDIZADO DINÂMICO):\n" + json.dumps(recent_examples, indent=2, ensure_ascii=False) + "\n---\n"

    valid_projects_str = ", ".join([f"'{p}'" for p in valid_projects]) if valid_projects else "Nenhum"
    valid_subjects_str = ", ".join([f"'{s}'" for s in valid_subjects]) if valid_subjects else "Nenhum"
    valid_responsibles_str = ", ".join([f"'{r}'" for r in valid_responsibles]) if valid_responsibles else "Nenhum"

    # Constrói o prompt direcionando as regras
    prompt = (
        "Você é um Engenheiro de IA especializado em melhoria contínua e Lean Data Cleanliness, "
        "atuando como assistente virtual da empresa Amaya Agro / Ribeira ML.\n\n"
        "Suas decisões de mapeamento (Projeto, Responsável, etc.) devem obedecer estritamente à BASE DE DADOS MASTER da empresa fornecida abaixo:\n\n"
        "---\n"
        "BASE DE DADOS MASTER:\n"
        f"{knowledge_base}\n"
        "---\n"
        f"{examples_str}\n\n"
        "Sua missão é extrair dados estruturados a partir do Título e Descrição de uma tarefa pendente para montar um Quadro Andon.\n\n"
        f"Tarefa Original:\n- TÍTULO: {title}\n- DESCRIÇÃO/ANOTAÇÕES: {notes}\n\n"
        "Regras Operacionais Críticas e Restrição de Opções:\n"
        "1. **RESTRIÇÃO ESTRITA DE VALORES**:\n"
        "   Os campos 'projeto', 'assunto' e 'responsavel' devem conter UNICAMENTE valores que constem exatamente nas listas abaixo. Se o valor ideal não constar em sua respectiva lista (ou houver qualquer incerteza), deixe o campo correspondente em branco (string vazia \"\"). Não crie novos valores de forma alguma.\n"
        f"   - Lista de Projetos Válidos: [{valid_projects_str}]\n"
        f"   - Lista de Assuntos Válidos: [{valid_subjects_str}]\n"
        f"   - Lista de Responsáveis Válidos: [{valid_responsibles_str}]\n\n"
        "2. **Regra Estrita de Incerteza**:\n"
        "   Se você não tiver 100% de certeza absoluta sobre qualquer um dos seguintes campos: 'projeto', 'responsavel' ou 'due_date' com base no texto fornecido, na Base de Dados Master ou no Histórico Recente, deixe o campo correspondente em branco (string vazia \"\"). Não invente, não presuma e não tente inferir informações do nada. Não crie novos assuntos, projetos ou responsáveis. É preferível deixar em branco do que preencher incorretamente.\n\n"
        "3. **Uso de Palavras-Chave e Gatilhos da Base de Dados**:\n"
        "   Consulte a tabela \"MAPA DE PALAVRAS-CHAVE E ASSOCIAÇÕES\" e a descrição da equipe/projetos. Se o Título ou Descrição contiver gatilhos ou palavras-chave ali especificadas (ex: \"Artvac\", \"Easysoft\", \"Joy\", \"NPK\"), preencha o Projeto e Responsável correspondente exatamente como mapeado na Base.\n\n"
        "4. **Determinação de Prioridade**:\n"
        "   Defina o campo 'prioridade' de 1 a 3. Onde 1 é o mais urgente/importante e 3 é o menos. Tente deduzir a prioridade a partir do título/notas ou use 2 como padrão se não houver indicação clara.\n\n"
        "5. **Conversão de Datas (due_date) e Sazonalidade**:\n"
        "   Se houver uma data de vencimento mencionada, formate como DD/MM/AAAA (ano 2026).\n"
        "   Se for uma tarefa relacionada a operações agrícolas sazonais descritas na seção 5 da Base de Dados e NÃO tiver prazo definido, atribua um prazo curto de 1 a 2 semanas (adicionando 7 a 14 dias no formato DD/MM/AAAA a partir de Junho/2026). Caso contrário, deixe vazio.\n\n"
        "6. **Mapeamento de Status**:\n"
        "   O status da tarefa deve ser mapeado estritamente como:\n"
        "   - '△' (ongoing/em andamento ou tem problema não fatal): É o status padrão para novas tarefas.\n"
        "   - 'O' (Concluído): Somente se o texto explicitamente indicar concluído.\n"
        "   - 'X' (deu M / bloqueado / problema crítico): Somente se o texto indicar um erro/bloqueio grave.\n\n"
        "Retorne os dados formatados conforme o esquema JSON solicitado."
    )

    print(f"Processando tarefa '{title[:30]}...' com Gemini ({config.GEMINI_MODEL})...")
    
    max_retries = 4
    retry_delay = 12  # Começa com 12s para respeitar a cota de 5 RPM caso ela seja muito estrita
    
    for attempt in range(max_retries):
        try:
            # Chama a API solicitando resposta estruturada JSON conforme o schema Pydantic AndonTask
            response = client.models.generate_content(
                model=config.GEMINI_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=AndonTask,
                    temperature=0.0, # Zero para máxima previsibilidade e obediência às regras
                ),
            )
            
            # Converte o retorno JSON direto para a classe do Pydantic
            task_data = AndonTask.model_validate_json(response.text)
            
            # Pequeno intervalo de segurança entre requisições de sucesso
            time.sleep(1)
            return task_data
            
        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                if attempt < max_retries - 1:
                    print(f"  [Rate Limit] Limite de cota atingido. Aguardando {retry_delay}s antes de tentar novamente (Tentativa {attempt + 1}/{max_retries})...")
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Backoff exponencial (12s -> 24s -> 48s)
                    continue
            
            print(f"Erro ao processar/deserializar resposta do Gemini: {e}")
            raise e

    raise Exception(f"Falha ao processar tarefa após {max_retries} tentativas devido a limites de requisição da API.")
