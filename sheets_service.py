import google_auth
import config

# Definição dos cabeçalhos esperados do Quadro Andon
EXPECTED_HEADERS = [
    "Assunto",
    "Projeto",
    "Problema/contramedida",
    "Responsável",
    "Due Date",
    "prioridade",
    "Status",
    "ID Tarefa",
    "concluido"
]

def get_sheets_service():
    """
    Retorna o serviço autenticado do Google Sheets API.
    """
    return google_auth.get_service("sheets", "v4")

def ensure_support_sheets_exist_and_migrate():
    """
    Garante que as abas 'Projetos', 'Assuntos' e 'profissionais' existam no Google Sheets.
    Se não existirem, cria-as.
    Na primeira vez ou se estiverem vazias, migra os dados correspondentes únicos
    da aba 'Lista de pendencias' para preenchê-las.
    """
    print("Verificando abas auxiliares (Projetos, Assuntos, profissionais)...")
    service = get_sheets_service()
    
    # Busca metadados da planilha
    spreadsheet = service.spreadsheets().get(spreadsheetId=config.SPREADSHEET_ID).execute()
    existing_sheets = [s.get('properties', {}).get('title') for s in spreadsheet.get('sheets', [])]
    
    required_sheets = {
        "Projetos": "Projeto",
        "Assuntos": "Assunto",
        "profissionais": "Responsável"
    }
    
    # Cria as abas que não existem
    requests = []
    for sheet_title in required_sheets.keys():
        if sheet_title not in existing_sheets:
            print(f"Criando aba '{sheet_title}'...")
            requests.append({
                'addSheet': {
                    'properties': {
                        'title': sheet_title
                    }
                }
            })
            
    if requests:
        service.spreadsheets().batchUpdate(
            spreadsheetId=config.SPREADSHEET_ID,
            body={'requests': requests}
        ).execute()
        # Atualiza a lista de abas existentes
        spreadsheet = service.spreadsheets().get(spreadsheetId=config.SPREADSHEET_ID).execute()
        existing_sheets = [s.get('properties', {}).get('title') for s in spreadsheet.get('sheets', [])]
        
    # Agora lê os dados da aba principal 'Lista de pendencias' para fazer a migração
    main_range = f"{config.SHEET_NAME}!A1:H1000"
    result = service.spreadsheets().values().get(
        spreadsheetId=config.SPREADSHEET_ID,
        range=main_range
    ).execute()
    main_rows = result.get("values", [])
    
    if not main_rows or len(main_rows) <= 1:
        print("Planilha principal está vazia. Nada a migrar.")
        return
        
    headers = [str(h).strip() for h in main_rows[0]]
    
    # Para cada aba de apoio, verifica se está vazia ou precisa de migração
    for sheet_title, col_header in required_sheets.items():
        # Lê a aba de apoio
        support_result = service.spreadsheets().values().get(
            spreadsheetId=config.SPREADSHEET_ID,
            range=f"{sheet_title}!A1:A500"
        ).execute()
        support_rows = support_result.get("values", [])
        
        # Se a aba estiver vazia ou tiver apenas o cabeçalho, realiza a migração
        needs_migration = False
        if not support_rows or len(support_rows) <= 1:
            needs_migration = True
            
        if needs_migration:
            print(f"Migrando dados únicos da coluna '{col_header}' para a aba '{sheet_title}'...")
            try:
                col_idx = headers.index(col_header)
            except ValueError:
                print(f"Coluna '{col_header}' não encontrada na planilha principal.")
                continue
                
            unique_values = set()
            for row in main_rows[1:]:
                if len(row) > col_idx:
                    val = str(row[col_idx]).strip()
                    if val:
                        unique_values.add(val)
                        
            # Escreve os valores únicos na aba de apoio
            write_data = [[col_header]] + [[v] for v in sorted(unique_values)]
            
            # Limpa a aba primeiro
            service.spreadsheets().values().clear(
                spreadsheetId=config.SPREADSHEET_ID,
                range=f"{sheet_title}!A1:Z500"
            ).execute()
            
            # Grava
            service.spreadsheets().values().update(
                spreadsheetId=config.SPREADSHEET_ID,
                range=f"{sheet_title}!A1",
                valueInputOption="USER_ENTERED",
                body={"values": write_data}
            ).execute()
            print(f"Aba '{sheet_title}' populada com {len(unique_values)} itens.")

def get_support_sheet_options(sheet_title):
    """
    Retorna todos os itens cadastrados em uma aba de apoio (excluindo o cabeçalho).
    """
    service = get_sheets_service()
    try:
        result = service.spreadsheets().values().get(
            spreadsheetId=config.SPREADSHEET_ID,
            range=f"{sheet_title}!A2:A500"
        ).execute()
        rows = result.get("values", [])
        return [str(row[0]).strip() for row in rows if row and str(row[0]).strip()]
    except Exception as e:
        print(f"Erro ao obter opções da aba {sheet_title}: {e}")
        return []

def add_support_sheet_option(sheet_title, value):
    """
    Adiciona um novo valor único a uma aba de apoio, se ele já não existir.
    """
    value = str(value).strip()
    if not value:
        return False
        
    options = get_support_sheet_options(sheet_title)
    if value in options:
        return True # Já existe
        
    service = get_sheets_service()
    next_row = len(options) + 2 # +1 do cabeçalho, +1 para a próxima linha
    
    try:
        service.spreadsheets().values().update(
            spreadsheetId=config.SPREADSHEET_ID,
            range=f"{sheet_title}!A{next_row}",
            valueInputOption="USER_ENTERED",
            body={"values": [[value]]}
        ).execute()
        return True
    except Exception as e:
        print(f"Erro ao adicionar opção '{value}' na aba {sheet_title}: {e}")
        return False

def update_task_in_sheet(task_id, updated_fields):
    """
    Atualiza campos específicos de uma tarefa na planilha 'Lista de pendencias'
    procurando pelo seu ID Tarefa.
    """
    service = get_sheets_service()
    range_name = f"{config.SHEET_NAME}!A1:Z1000"
    result = service.spreadsheets().values().get(
        spreadsheetId=config.SPREADSHEET_ID,
        range=range_name
    ).execute()
    rows = result.get("values", [])
    if not rows:
        return False
        
    headers = [str(cell).strip() for cell in rows[0]]
    try:
        id_col_idx = headers.index("ID Tarefa")
    except ValueError:
        print("Erro: Coluna 'ID Tarefa' não encontrada.")
        return False
        
    row_num = None
    target_row = None
    for idx, row in enumerate(rows[1:], start=2):
        if len(row) > id_col_idx and str(row[id_col_idx]).strip() == task_id:
            row_num = idx
            target_row = row
            break
            
    if row_num is None:
        print(f"Tarefa com ID {task_id} não encontrada para atualização.")
        return False
        
    # Prepara a linha atualizada estendendo-a até o tamanho de headers
    new_row = ["" for _ in headers]
    for i in range(min(len(target_row), len(headers))):
        new_row[i] = target_row[i]
        
    # Mapeamento de campos da requisição para os cabeçalhos
    field_mapping = {
        "Assunto": updated_fields.get("Assunto"),
        "Projeto": updated_fields.get("Projeto"),
        "Problema/contramedida": updated_fields.get("Problema/contramedida"),
        "Responsável": updated_fields.get("Responsável"),
        "Due Date": updated_fields.get("Due Date"),
        "prioridade": updated_fields.get("prioridade"),
        "Status": updated_fields.get("Status"),
        "concluido": updated_fields.get("concluido") if updated_fields.get("concluido") is not None else updated_fields.get("Concluido")
    }
    
    # Atualiza apenas os campos enviados
    for col_name, value in field_mapping.items():
        if value is not None and col_name in headers:
            col_idx = headers.index(col_name)
            new_row[col_idx] = str(value)
            
    # Grava na linha encontrada
    write_range = f"{config.SHEET_NAME}!A{row_num}"
    service.spreadsheets().values().update(
        spreadsheetId=config.SPREADSHEET_ID,
        range=write_range,
        valueInputOption="USER_ENTERED",
        body={"values": [new_row]}
    ).execute()
    return True

def setup_and_get_imported_ids():
    """
    Verifica a planilha. Garante que os cabeçalhos esperados comecem na coluna A.
    Remove linhas vazias intermediárias (compactação) e retorna os IDs já importados,
    além de carregar os últimos registros como exemplos históricos.
    """
    print("Conectando ao Google Sheets API...")
    service = get_sheets_service()
    
    # Lê todo o conteúdo da planilha para analisar a estrutura
    range_name = f"{config.SHEET_NAME}!A1:Z1000"
    try:
        result = service.spreadsheets().values().get(
            spreadsheetId=config.SPREADSHEET_ID,
            range=range_name
        ).execute()
    except Exception as e:
        print(f"Erro ao ler a planilha: {e}")
        print("Certifique-se de que o SPREADSHEET_ID e o SHEET_NAME no config.py estão corretos.")
        raise e

    rows = result.get("values", [])
    
    # Prepara os dados compactados tirando linhas em branco no meio
    headers = EXPECTED_HEADERS.copy()
    compacted_rows = []
    
    if rows:
        # Verifica se os cabeçalhos atuais batem com o esperado
        current_headers = [str(cell).strip() for cell in rows[0]]
        if current_headers[:len(EXPECTED_HEADERS)] == EXPECTED_HEADERS:
            compacted_rows.append(current_headers)
        else:
            compacted_rows.append(headers)
            
        # Filtra linhas que sejam totalmente vazias
        for row in rows[1:]:
            if any(str(cell).strip() for cell in row):
                compacted_rows.append(row)
    else:
        compacted_rows.append(headers)
        
    # Se a quantidade de linhas mudou, significa que limpamos gaps ou linhas vazias
    if len(rows) != len(compacted_rows):
        print("Aviso: Linhas vazias ou desalinhamentos detectados na planilha. Compactando dados...")
        # Limpa o intervalo
        service.spreadsheets().values().clear(
            spreadsheetId=config.SPREADSHEET_ID,
            range=range_name
        ).execute()
        # Regrava os dados compactados a partir do topo (A1)
        service.spreadsheets().values().update(
            spreadsheetId=config.SPREADSHEET_ID,
            range=f"{config.SHEET_NAME}!A1",
            valueInputOption="USER_ENTERED",
            body={"values": compacted_rows}
        ).execute()
        
    # Coleta todos os IDs já importados (com base na coluna 'ID Tarefa')
    imported_ids = set()
    try:
        id_col_idx = headers.index("ID Tarefa")
        for row in compacted_rows[1:]:
            # Verifica se a linha tem o valor da coluna 'ID Tarefa'
            if len(row) > id_col_idx:
                task_id = str(row[id_col_idx]).strip()
                if task_id:
                    imported_ids.add(task_id)
    except ValueError:
        print("Erro: Coluna 'ID Tarefa' não encontrada nos cabeçalhos.")
            
    print(f"Total de registros ativos na planilha: {len(compacted_rows) - 1}")
    print(f"IDs de tarefas já importados anteriormente: {len(imported_ids)}")

    # Extrai os últimos 50 registros para servir de exemplo histórico dinâmico (Opção 1)
    recent_examples = []
    for row in compacted_rows[1:][-50:]:
        example_dict = {}
        for idx, col_name in enumerate(headers):
            if col_name != "ID Tarefa" and idx < len(row):
                example_dict[col_name] = row[idx]
        if example_dict:
            recent_examples.append(example_dict)

    return headers, imported_ids, recent_examples

def append_single_task(task, headers=None, next_row_num=None):
    """
    Salva uma única tarefa diretamente na próxima linha livre da planilha,
    evitando a inserção de linhas em branco.
    """
    if headers is None:
        headers, _, _ = setup_and_get_imported_ids()
        
    service = get_sheets_service()
    
    if next_row_num is None:
        # Descobre o número da próxima linha livre lendo o preenchimento da coluna A
        result = service.spreadsheets().values().get(
            spreadsheetId=config.SPREADSHEET_ID,
            range=f"{config.SHEET_NAME}!A1:A1000"
        ).execute()
        current_rows = result.get("values", [])
        next_row_num = len(current_rows) + 1
    
    # Inicializa a linha vazia
    row_values = [""] * len(headers)
    
    field_mapping = {
        "Assunto": task.get("assunto", ""),
        "Projeto": task.get("projeto", ""),
        "Problema/contramedida": task.get("problema_contramedida", ""),
        "Responsável": task.get("responsavel", ""),
        "Due Date": task.get("due_date", ""),
        "prioridade": str(task.get("prioridade", "2")),
        "Status": task.get("status", "△"),
        "ID Tarefa": task.get("id", ""),
        "concluido": task.get("concluido") or task.get("Concluido") or "nao"
    }
    
    # Preenche os valores nas posições corretas correspondentes ao cabeçalho da planilha
    for field_name, value in field_mapping.items():
        if field_name in headers:
            idx = headers.index(field_name)
            row_values[idx] = value
            
    # Grava na linha correspondente via update (A{next_row_num})
    write_range = f"{config.SHEET_NAME}!A{next_row_num}"
    print(f"Gravando fisicamente a tarefa na linha {next_row_num}...")
    service.spreadsheets().values().update(
        spreadsheetId=config.SPREADSHEET_ID,
        range=write_range,
        valueInputOption="USER_ENTERED",
        body={"values": [row_values]}
    ).execute()

def append_andon_tasks(tasks_to_append):
    """
    Função de lote (mantida para retrocompatibilidade).
    """
    if not tasks_to_append:
        return 0
    
    headers, _, _ = setup_and_get_imported_ids()
    service = get_sheets_service()
    
    result = service.spreadsheets().values().get(
        spreadsheetId=config.SPREADSHEET_ID,
        range=f"{config.SHEET_NAME}!A1:A1000"
    ).execute()
    current_rows = result.get("values", [])
    next_row_num = len(current_rows) + 1

    for task in tasks_to_append:
        append_single_task(task, headers=headers, next_row_num=next_row_num)
        next_row_num += 1
    return len(tasks_to_append)

def bulk_update_tasks_in_sheet(tasks_list):
    """
    Atualiza uma lista de tarefas na planilha 'Lista de pendencias' de uma vez só.
    Se a tarefa tiver um ID que comece com 'NEW_' ou não tiver ID, ela é adicionada como nova linha.
    """
    service = get_sheets_service()
    
    # 1. Lê os dados atuais da planilha para mapear linhas e IDs
    range_name = f"{config.SHEET_NAME}!A1:Z1000"
    result = service.spreadsheets().values().get(
        spreadsheetId=config.SPREADSHEET_ID,
        range=range_name
    ).execute()
    rows = result.get("values", [])
    
    headers = EXPECTED_HEADERS.copy()
    if rows:
        current_headers = [str(cell).strip() for cell in rows[0]]
        if current_headers[:len(EXPECTED_HEADERS)] == EXPECTED_HEADERS:
            headers = current_headers
            
    try:
        id_col_idx = headers.index("ID Tarefa")
    except ValueError:
        print("Erro: Coluna 'ID Tarefa' não encontrada nos cabeçalhos.")
        return False

    # Mapeia IDs de tarefas existentes para o número da linha correspondente (1-based index)
    id_to_row_num = {}
    for idx, row in enumerate(rows[1:], start=2):
        if len(row) > id_col_idx:
            t_id = str(row[id_col_idx]).strip()
            if t_id:
                id_to_row_num[t_id] = idx

    # Prepara as atualizações em lote usando batchUpdate
    value_updates = []
    
    # Próxima linha livre para novos registros
    next_row_num = len(rows) + 1 if rows else 2
    
    for task in tasks_list:
        task_id = str(task.get("ID Tarefa", "")).strip()
        is_new = not task_id or task_id.startswith("NEW_")
        
        # Mapeamento de campos da requisição para os cabeçalhos
        field_mapping = {
            "Assunto": task.get("Assunto", ""),
            "Projeto": task.get("Projeto", ""),
            "Problema/contramedida": task.get("Problema/contramedida", ""),
            "Responsável": task.get("Responsável", ""),
            "Due Date": task.get("Due Date", ""),
            "prioridade": str(task.get("prioridade", "2")),
            "Status": task.get("Status", "△"),
            "ID Tarefa": task_id if not is_new else "",
            "concluido": task.get("concluido") or task.get("Concluido") or "nao"
        }
        
        row_values = [""] * len(headers)
        for col_name, val in field_mapping.items():
            if col_name in headers:
                idx = headers.index(col_name)
                row_values[idx] = str(val)
                
        if is_new:
            # Novo item - adiciona na próxima linha
            write_range = f"{config.SHEET_NAME}!A{next_row_num}"
            value_updates.append({
                "range": write_range,
                "values": [row_values]
            })
            next_row_num += 1
        else:
            # Item existente - atualiza na linha correspondente se encontrada
            if task_id in id_to_row_num:
                target_row = id_to_row_num[task_id]
                write_range = f"{config.SHEET_NAME}!A{target_row}"
                value_updates.append({
                    "range": write_range,
                    "values": [row_values]
                })
            else:
                # Caso a tarefa não seja encontrada, insere como nova linha
                write_range = f"{config.SHEET_NAME}!A{next_row_num}"
                value_updates.append({
                    "range": write_range,
                    "values": [row_values]
                })
                next_row_num += 1
                
    if value_updates:
        body = {
            "valueInputOption": "USER_ENTERED",
            "data": value_updates
        }
        service.spreadsheets().values().batchUpdate(
            spreadsheetId=config.SPREADSHEET_ID,
            body=body
        ).execute()
        print(f"Atualização em lote executada. {len(value_updates)} linhas modificadas/inseridas.")
        return True
    return False
