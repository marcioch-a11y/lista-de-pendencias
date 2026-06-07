import os
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import config

def get_credentials():
    """
    Obtém as credenciais OAuth2 do usuário.
    Se token.json existir, carrega dele. Caso contrário, inicia o fluxo de login
    com credentials.json e gera o token.json.
    """
    creds = None
    # Verifica se o token já está salvo
    if os.path.exists(config.TOKEN_FILE):
        try:
            creds = Credentials.from_authorized_user_file(config.TOKEN_FILE, config.SCOPES)
        except Exception as e:
            print(f"Aviso: Erro ao carregar token.json: {e}. Iniciando nova autenticação.")

    # Se não houver credenciais válidas, inicia o login
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                print(f"Erro ao atualizar token expirado: {e}. Iniciando fluxo completo.")
                creds = None
        
        if not creds:
            if not os.path.exists(config.CREDENTIALS_FILE):
                raise FileNotFoundError(
                    f"Erro de Autenticação:\n"
                    f"Arquivo de credenciais '{config.CREDENTIALS_FILE.name}' não foi encontrado no diretório do projeto.\n"
                    f"Por favor, crie as credenciais OAuth Desktop no Google Cloud Console, baixe-as, "
                    f"renomeie para 'credentials.json' e coloque-as em: {config.BASE_DIR}"
                )
            
            flow = InstalledAppFlow.from_client_secrets_file(
                str(config.CREDENTIALS_FILE), config.SCOPES
            )
            # Executa o servidor local para receber a autorização no browser
            creds = flow.run_local_server(port=0)
            
        # Salva o token para as próximas execuções
        with open(config.TOKEN_FILE, "w") as token_file:
            token_file.write(creds.to_json())
            
    return creds

def get_service(service_name, version):
    """
    Retorna o cliente da API do Google (ex: 'tasks', 'sheets') com credenciais ativas.
    """
    creds = get_credentials()
    return build(service_name, version, credentials=creds)
