# Daniel Job Agent

Projeto em Python para organizar e, futuramente, automatizar a busca de vagas
comerciais remotas compatíveis com profissionais no Brasil e na América Latina.

## Estado atual

Esta primeira etapa contém somente a fundação do projeto e o modelo de dados de
uma oportunidade. Ainda **não** há busca de vagas, scraping, inteligência
artificial, conexão com Google Sheets ou automação semanal.

## Estrutura

```text
daniel-job-agent/
├── data/                     # Dados locais gerados durante o desenvolvimento
├── prompts/                  # Prompts que poderão ser usados em uma etapa futura
├── src/
│   └── daniel_job_agent/
│       ├── __init__.py       # Define o pacote Python
│       └── models.py         # Modelo JobOpportunity
├── tests/
│   └── test_job_opportunity.py
├── .env.example              # Exemplo de configurações e segredos
├── .gitignore                # Arquivos que o Git deve ignorar
├── README.md                 # Documentação do projeto
└── requirements.txt          # Dependências Python
```

## Requisitos

- macOS
- Python 3.10 ou mais recente

No Terminal, confirme a instalação:

```bash
python3 --version
```

Se o comando não funcionar, instale o Python pelo site
[python.org](https://www.python.org/downloads/macos/) ou com Homebrew:

```bash
brew install python
```

## Como executar localmente no Mac

1. Abra o Terminal e entre na pasta do projeto:

   ```bash
   cd "/Users/danielparreiras/Documents/ChatGPT/daniel-job-agent"
   ```

2. Crie um ambiente virtual isolado:

   ```bash
   python3 -m venv .venv
   ```

3. Ative o ambiente virtual:

   ```bash
   source .venv/bin/activate
   ```

4. Instale as dependências (nesta etapa, não há pacotes externos):

   ```bash
   python -m pip install -r requirements.txt
   ```

5. Crie seu arquivo local de configuração a partir do exemplo:

   ```bash
   cp .env.example .env
   ```

6. Execute os testes:

   ```bash
   python -m unittest discover -s tests -v
   ```

7. Quando terminar, desative o ambiente virtual:

   ```bash
   deactivate
   ```

## Exemplo de uso do modelo

```python
from datetime import date, datetime, timezone

from daniel_job_agent import JobOpportunity

job = JobOpportunity(
    company="Empresa Exemplo",
    role="Account Executive",
    job_url="https://example.com/jobs/123",
    source="Página de carreiras",
    location="Remote - LATAM",
    remote=True,
    brazil_eligible=True,
    employment_type="Full-time",
    date_found=date.today(),
    match_score=85,
    still_open=True,
    last_checked=datetime.now(timezone.utc),
)

print(job.company, job.match_score)
```

Para executar esse exemplo fora da pasta `tests`, ative o ambiente virtual e
informe ao Python onde está o código-fonte:

```bash
PYTHONPATH=src python seu_arquivo.py
```

## Próximas etapas possíveis

As funcionalidades futuras serão adicionadas aos poucos: coleta de vagas,
regras de compatibilidade, Match Score, persistência, atualização e automação.
Cada integração deve entrar em uma etapa separada e acompanhada de testes.
