import os
from dotenv import load_dotenv
from llm_processor import process_task_with_llm

def test_cases():
    load_dotenv()
    
    if not os.environ.get("GEMINI_API_KEY"):
        print("Aviso: GEMINI_API_KEY não definida no ambiente. Não é possível rodar o teste com a API real.")
        print("Defina a chave no terminal ou crie um arquivo .env")
        return

    test_tasks = [
        {
            "title": "Projeto CRM: Corrigir erro 500 na rota de login",
            "notes": "O login está travando ao tentar conectar com a base do Firebase. Contramedida: Revisar token de autenticação no config. Responsável: André. Prazo de entrega: 25/06/2026"
        },
        {
            "title": "Ajustar layout do cabeçalho da dashboard",
            "notes": "O logotipo está quebrando em telas menores. Mover os botões para o menu hambúrguer."
        },
        {
            "title": "Reunião de Alinhamento com cliente",
            "notes": "Vencimento até 15 de julho. Confirmar presença de Monica e Marcio."
        }
    ]

    print("=== INICIANDO TESTE DE EXTRAÇÃO DO GEMINI ===\n")
    for idx, task in enumerate(test_tasks, 1):
        print(f"--- Caso {idx} ---")
        print(f"Bruto -> Título: {task['title']}")
        print(f"Bruto -> Descrição: {task['notes']}")
        try:
            result = process_task_with_llm(task["title"], task["notes"])
            print("\nResultado Estruturado (Gemini Output):")
            print(f"  Projeto: '{result.projeto}'")
            print(f"  Item/Problema: '{result.item_problema}'")
            print(f"  Contramedida: '{result.contramedida}'")
            print(f"  Responsável: '{result.responsavel}'")
            print(f"  Due Date: '{result.due_date}'")
            print(f"  Status: '{result.status}'")
            print("-" * 30 + "\n")
        except Exception as e:
            print(f"Erro no teste: {e}\n")

if __name__ == "__main__":
    test_cases()
