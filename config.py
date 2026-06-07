import os
from pathlib import Path

# Diretório base do projeto
BASE_DIR = Path(__file__).resolve().parent

# Configurações do Google API
# ID extraído de: https://docs.google.com/spreadsheets/d/1DZI092Fj22DO6rWzKN0xSLSYAfgT4Gkvu2gQhiajS6U/edit
SPREADSHEET_ID = "1DZI092Fj22DO6rWzKN0xSLSYAfgT4Gkvu2gQhiajS6U"
SHEET_NAME = "Lista de pendencias"  # Altere se a aba de destino tiver outro nome

# ID da lista de tarefas do Google Tasks (ID correspondente à 'Lista de tarefas')
TASKS_LIST_ID = "MDQ3NDE3OTkxMDk4MTQ1MzE1Nzc6NDIxODI3NTQ5ODExMzgzMjow"

# Caminho dos arquivos de credenciais e tokens
CREDENTIALS_FILE = BASE_DIR / "credentials.json"
TOKEN_FILE = BASE_DIR / "token.json"

# Escopos de autorização necessários para o Google API
SCOPES = [
    "https://www.googleapis.com/auth/tasks.readonly",  # Apenas leitura das tarefas
    "https://www.googleapis.com/auth/spreadsheets",   # Leitura e escrita nas planilhas
]

# Configurações de IA (Gemini)
# O SDK google-genai busca automaticamente a variável GEMINI_API_KEY no ambiente
GEMINI_MODEL = "gemini-3.1-flash-lite"  # Usando o 3.1 Flash Lite que possui cota ativa

# Provedor de LLM: 'gemini' ou 'local' (para LM Studio)
LLM_PROVIDER = "local"

# Configurações do LM Studio (Local LLM)
LOCAL_LLM_URL = "http://127.0.0.1:1234/v1/chat/completions"
LOCAL_LLM_MODEL = "gemma"  # LM Studio aceitará qualquer nome, mas definimos como gemma para clareza

