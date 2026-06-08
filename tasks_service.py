import google_auth
import config

def get_pending_tasks(tasklist_id=config.TASKS_LIST_ID):
    """
    Conecta à API do Google Tasks e extrai a lista de tarefas pendentes,
    suportando paginação e resolvendo a hierarquia de subtarefas.
    Retorna uma lista de dicionários contendo: id, title, notes e parent_title (se houver).
    """
    print("Conectando ao Google Tasks API...")
    service = google_auth.get_service("tasks", "v1")
    
    all_items = []
    page_token = None
    
    # 1. Busca todas as tarefas da lista usando paginação
    while True:
        results = service.tasks().list(
            tasklist=tasklist_id,
            showCompleted=True,  # Traz inclusive completas para podermos mapear títulos de pais completados
            showHidden=True,
            maxResults=100,
            pageToken=page_token
        ).execute()
        
        all_items.extend(results.get("items", []))
        page_token = results.get("nextPageToken")
        if not page_token:
            break
            
    print(f"Total de tarefas encontradas no Google Tasks (histórico completo): {len(all_items)}")
    
    # Mapeamento rápido de ID -> Título para resolver nomes de pais
    task_map = {item["id"]: item.get("title", "") for item in all_items}
    
    # Identifica quais tarefas são pais (possuem subitens)
    parent_ids = set()
    for item in all_items:
        parent_id = item.get("parent")
        if parent_id:
            parent_ids.add(parent_id)
            
    # Filtra: queremos apenas tarefas que:
    # 1. Não estejam completadas (status != 'completed')
    # 2. Não sejam tarefas Pai (pois os pais são a categoria/projeto dos subitens)
    pending_tasks = []
    for item in all_items:
        is_completed = item.get("status") == "completed"
        is_parent = item["id"] in parent_ids
        
        if not is_completed and not is_parent:
            parent_title = None
            parent_id = item.get("parent")
            if parent_id:
                parent_title = task_map.get(parent_id)
                
            pending_tasks.append({
                "id": item["id"],
                "title": item.get("title", ""),
                "notes": item.get("notes", ""),
                "parent_title": parent_title,
                "starred": item.get("starred", False)
            })
            
    print(f"Total de tarefas pendentes filtradas para importação: {len(pending_tasks)}")
    return pending_tasks

def complete_task(task_id, tasklist_id=config.TASKS_LIST_ID):
    """
    Marca uma tarefa como concluída no Google Tasks.
    """
    print(f"Marcando tarefa {task_id[:10]}... como concluída no Google Tasks")
    service = google_auth.get_service("tasks", "v1")
    service.tasks().patch(
        tasklist=tasklist_id,
        task=task_id,
        body={"status": "completed"}
    ).execute()
