# Daniel Job Agent

Projeto em Python para organizar e, futuramente, automatizar a busca de vagas
comerciais remotas compatíveis com profissionais no Brasil e na América Latina.

## Estado atual

O projeto já possui o modelo de uma oportunidade e uma primeira camada local de
regras para organizar vagas recebidas pelo código. As regras normalizam dados,
classificam cargos e localização, identificam possíveis duplicatas, calculam um
Match Score e sugerem se a vaga deve ser mantida, revisada ou rejeitada.

O acompanhamento manual do processo seletivo fica separado dos dados do anúncio.
Ainda **não** há busca de vagas, scraping, inteligência artificial, conexão com
Google Sheets, APIs externas ou automação semanal.

## Estrutura

```text
daniel-job-agent/
├── data/                     # Dados locais gerados durante o desenvolvimento
├── prompts/                  # Prompts que poderão ser usados em uma etapa futura
├── src/
│   └── daniel_job_agent/
│       ├── __init__.py       # Define o pacote Python
│       ├── models.py         # Vaga e acompanhamento manual do CRM
│       └── rules.py          # Regras locais de classificação e decisão
├── tests/
│   ├── test_job_opportunity.py
│   └── test_rules.py
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
   cd "/Users/danielparreiras/job-search-agent"
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

## Acompanhamento manual do CRM

Cada `JobOpportunity` possui um campo `tracking`. Ele guarda o status da
candidatura, data de aplicação, contato do recrutador, próximo passo e notas.
Esses dados ficam agrupados em `ApplicationTracking` para que futuras
atualizações automáticas do anúncio não os sobrescrevam.

Os status disponíveis começam em `NOT_APPLIED` e incluem as etapas de aplicação,
entrevistas, oferta, rejeição e desistência.

## Como funciona o fluxo de decisão

Para cada vaga fornecida localmente ao Python:

1. Empresa, cargo e localização podem ter espaços corrigidos sem alterar
   agressivamente os nomes.
2. O cargo recebe prioridade `HIGH`, `MEDIUM` ou `IRRELEVANT`.
3. A localização recebe elegibilidade `ELIGIBLE`, `NOT_ELIGIBLE` ou `UNKNOWN`.
4. O Match Score soma pesos documentados para cargo, localização e trabalho
   remoto. O resultado sempre fica entre 0 e 100.
5. A decisão final é:
   - `KEEP`: cargo relevante, localização elegível e bom score;
   - `REVIEW`: faltam informações ou o título ainda não é reconhecido;
   - `REJECT`: cargo explicitamente irrelevante ou localização incompatível.

A deduplicação considera duas vagas iguais quando a URL normalizada coincide ou
quando empresa e cargo normalizados coincidem. Parâmetros de rastreamento da URL
não criam uma vaga nova.

Os pesos do score ficam em `ScoreWeights`, portanto podem ser ajustados sem
alterar o restante do fluxo. As funções de regra apenas leem a vaga: elas não
mudam o anúncio nem o acompanhamento manual.

## Limitações atuais

- A lista de cargos reconhecidos é intencionalmente pequena.
- A regra de `Account Manager` ainda considera apenas o título; não analisa a
  descrição para confirmar responsabilidade comercial.
- A elegibilidade reconhece somente expressões geográficas simples e explícitas.
- A deduplicação não usa identificadores de plataformas nem similaridade de texto.
- O Match Score considera somente informações já presentes no modelo e não usa
  experiência profissional, descrição da vaga ou IA.
- `brazil_eligible` foi mantido por compatibilidade, mas a nova regra geográfica
  usa o texto de `location`; a unificação desses dois dados fica para uma etapa
  futura.

## Próxima pequena etapa sugerida

Adicionar uma descrição opcional da vaga e usá-la somente para refinar casos
ambíguos, como confirmar se `Account Manager` possui responsabilidade comercial.
Essa melhoria deve continuar local e acompanhada de novos testes antes de
qualquer integração externa.
