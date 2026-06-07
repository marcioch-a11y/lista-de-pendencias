# Integração Google Tasks -> Gemini LLM -> Google Sheets (Quadro Andon)

Este projeto automatiza a ingestão de tarefas brutas do **Google Tasks**, realiza o processamento de linguagem natural (NLP) com o **Gemini** para estruturar os dados com base em regras Lean (evitando alucinações e incertezas), e os grava diretamente em um Quadro Andon no **Google Sheets** sem criar registros duplicados.

---

## Requisitos Prévios

1. **Python 3.10 ou superior** instalado.
2. **Chave API do Gemini (Google AI Studio)**.
3. **Google API Credentials** (OAuth Desktop Client).

---

## Passo a Passo para Configuração

### 1. Obter as Credenciais do Google (credentials.json)
Para ler suas tarefas e atualizar sua planilha pessoal, o script precisa de autorização OAuth2:
1. Acesse o [Google Cloud Console](https://console.cloud.google.com/).
2. Crie um novo projeto (ex: *Andon Automation*).
3. No menu lateral, vá em **APIs e Serviços** > **Biblioteca**.
4. Busque e ative:
   - **Google Tasks API**
   - **Google Sheets API**
5. Vá em **APIs e Serviços** > **Tela de consentimento OAuth**:
   - Tipo de usuário: **Externo**.
   - Preencha as informações obrigatórias (nome do app, email).
   - **Importante**: Na aba **Usuários de teste**, adicione o seu próprio e-mail do Gmail que contém o Google Tasks e a Planilha.
6. Vá em **APIs e Serviços** > **Credenciais**:
   - Clique em **Criar Credenciais** > **ID do cliente OAuth**.
   - Tipo de aplicativo: **App de Computador (Desktop App)**.
   - Nome: *Andon CLI*.
7. Baixe o arquivo JSON gerado, renomeie-o exatamente para `credentials.json` e salve na raiz deste projeto.

### 2. Configurar o arquivo `.env`
Crie um arquivo chamado `.env` na raiz do projeto e adicione a sua chave de API do Gemini:
```env
GEMINI_API_KEY=sua_chave_aqui
```

### 3. Preparar o Ambiente e Instalar Dependências
No terminal/PowerShell, navegue até a pasta do projeto:
```powershell
# Criação do ambiente virtual
python -m venv venv

# Ativação do ambiente virtual (Windows)
.\venv\Scripts\activate

# Instalação das dependências
pip install -r requirements.txt
```

---

## Como Executar

Com o ambiente virtual ativo e as credenciais (`credentials.json`) na pasta raiz, execute:
```powershell
python main.py
```

### O que acontece na primeira execução?
1. O script abrirá uma janela do navegador solicitando login e autorização na sua conta Google.
2. Autorize os acessos. (Por ser uma credencial de teste criada por você, o navegador pode mostrar um aviso de segurança. Clique em *Avançado* > *Acessar Andon CLI (inseguro)*).
3. Após o login concluído, o terminal exibirá sucesso e gerará o arquivo `token.json` na raiz.
4. As execuções seguintes **serão 100% automatizadas** e não exigirão interação no navegador.

---

## Regras Lean Implementadas
- **Evitar Duplicados**: O script armazena o ID único de cada tarefa do Google Tasks na planilha (coluna `ID Tarefa`). Ele lê essa coluna antes de processar e pula tarefas que já foram importadas.
- **Data Cleanliness (Regra de Incerteza)**: O processador IA (Gemini) foi instruído de forma estrita a deixar os campos `Projeto`, `Contramedida`, `Responsável` ou `Due Date` vazios se houver qualquer ambiguidade ou se a informação não estiver explícita no texto original, prevenindo dados falsos ou "adivinhados".
- **Status Padronizado**: O status é mapeado automaticamente para `X` (Não Iniciado) por padrão, `△` (Em andamento) ou `O` (Concluído) se indicados expressamente no texto.
