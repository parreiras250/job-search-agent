# Daniel Job Agent

Projeto em Python para organizar e, futuramente, automatizar a busca de vagas
comerciais remotas compatíveis com profissionais no Brasil e na América Latina.

## Estado atual

O projeto já possui o modelo de uma oportunidade e uma primeira camada local de
regras para organizar vagas recebidas pelo código. As regras normalizam dados,
classificam cargos e localização, identificam possíveis duplicatas, calculam um
Match Score e sugerem se a vaga deve ser mantida, revisada ou rejeitada.

Uma vaga também pode ser comparada a um `CandidateProfile`. O perfil padrão do
Daniel registra somente informações profissionais relevantes, como experiência,
cargos desejados, ferramentas, indústrias e preferências de trabalho.

O acompanhamento manual do processo seletivo fica separado dos dados do anúncio.
Greenhouse, Lever, Jobicy e Remotive podem ser consultados manualmente por seus
endpoints públicos.
O resultado processado também pode ser salvo localmente em SQLite, permitindo
reconhecer vagas novas, já conhecidas ou atualizadas entre execuções.
Um comando principal conecta as consultas broad de Jobicy e Remotive ao pipeline
e ao histórico SQLite. O CRM pode ser sincronizado com Google Sheets, e um
LaunchAgent opcional permite executar esse mesmo fluxo semanalmente no Mac.
Ainda **não** há descoberta automática de empresas, scraping, inteligência
artificial, servidor cloud ou notificações.

## Estrutura

```text
daniel-job-agent/
├── data/                     # Dados locais gerados durante o desenvolvimento
├── prompts/                  # Prompts que poderão ser usados em uma etapa futura
├── src/
│   └── daniel_job_agent/
│       ├── __init__.py       # Define o pacote Python
│       ├── agent.py          # Orquestra discovery, pipeline e persistência
│       ├── crm.py            # Leitura, filtros e edição segura do CRM local
│       ├── crm_cli.py        # CLI para listar, atualizar e prever exportação
│       ├── demo.py           # Demonstração executável no terminal
│       ├── demo_data.py      # Registros brutos e vagas fictícias
│       ├── discovery.py      # Combinação Jobicy + Remotive
│       ├── discovery_demo.py # Ranking global das fontes amplas
│       ├── enrichment.py     # Extração determinística de sinais explícitos
│       ├── greenhouse_demo.py # Consulta manual de um board público
│       ├── google_sheets.py  # Push visual e pull manual seguro do Sheets
│       ├── google_sheets_cli.py # CLI OAuth com push e pull explícitos
│       ├── ingestion.py      # Adapters e ingestão local em lote
│       ├── lever_demo.py     # Consulta manual de postings públicos Lever
│       ├── jobicy_demo.py    # Descoberta manual ampla no Jobicy
│       ├── remotive_demo.py  # Descoberta manual ampla na Remotive
│       ├── lifecycle.py      # Política conservadora de presença e fechamento
│       ├── lifecycle_demo.py # Demonstração offline de misses e reabertura
│       ├── models.py         # Vaga e acompanhamento manual do CRM
│       ├── multi_query_demo.py # Discovery controlado por múltiplas queries
│       ├── pipeline.py       # Processamento em lote e ranking
│       ├── persistence_demo.py # Demonstração offline do histórico SQLite
│       ├── profiles.py       # Perfil profissional padrão do Daniel
│       ├── repository.py     # Persistência local centralizada em SQLite
│       ├── report_cli.py     # Consulta latest/history/show dos relatórios
│       ├── report_demo.py    # Demonstração Markdown totalmente offline
│       ├── reporting.py      # Contagens compartilhadas dos demos reais
│       ├── reports.py        # Snapshot executivo e armazenamento Markdown
│       ├── run_agent.py      # CLI principal do fluxo end-to-end
│       ├── scheduler.py      # Configuração e controle do LaunchAgent
│       ├── scheduler_cli.py  # Install/status/start/stop/run-now/uninstall
│       ├── rules.py          # Regras locais de classificação e decisão
│       ├── search_strategy.py # Estratégia e métricas multi-query
│       ├── sources.py        # Leitura HTTP de fontes externas
│       └── weekly_run.py     # Workflow semanal, lock, Sheets e histórico
├── tests/
│   ├── test_candidate_profile.py
│   ├── test_agent.py
│   ├── test_crm.py
│   ├── test_career_fit.py
│   ├── test_discovery.py
│   ├── test_enrichment.py
│   ├── test_greenhouse_source.py
│   ├── test_google_sheets.py
│   ├── test_ingestion.py
│   ├── test_job_opportunity.py
│   ├── test_lever_source.py
│   ├── test_lifecycle.py
│   ├── test_jobicy_source.py
│   ├── test_remotive_source.py
│   ├── test_pipeline.py
│   ├── test_repository.py
│   ├── test_reports.py
│   ├── test_rules.py
│   ├── test_search_strategy.py
│   └── test_scheduler.py
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

Uma avaliação completa também explica o resultado:

```python
from daniel_job_agent import create_daniel_profile, evaluate_match

profile = create_daniel_profile()
evaluation = evaluate_match(job, profile)

print(evaluation.score)
print(evaluation.positive_reasons)
print(evaluation.potential_gaps)
print(evaluation.unknowns)
```

Para executar esse exemplo fora da pasta `tests`, ative o ambiente virtual e
informe ao Python onde está o código-fonte:

```bash
PYTHONPATH=src python seu_arquivo.py
```

## Ingestão local

Ingestão é a etapa que transforma dados brutos de uma fonte em objetos
`JobOpportunity` padronizados. Cada fonte pode chamar os mesmos dados por nomes
diferentes, por exemplo `title`, `position_name` ou `job_title`. Um adapter conhece
o formato de uma fonte e faz essa tradução.

O projeto contém três simuladores totalmente locais:

- `GenericJobAdapter`;
- `MockGreenhouseAdapter`;
- `MockLeverAdapter`.

Os adapters fictícios não acessam Greenhouse, Lever ou qualquer serviço externo.
Eles apenas convertem dicionários Python fornecidos localmente.

```text
raw source data
→ adapter
→ JobOpportunity
→ pipeline
→ ranking
```

Dados brutos podem ter espaços extras, booleanos como `"true"` e números simples
como texto. `JobOpportunity` é o formato interno único que o restante do projeto
entende. Essa separação impede que o pipeline precise conhecer detalhes de cada
fonte externa.

Os campos essenciais são empresa, cargo, URL, fonte e localização. O nome da
fonte é fornecido pelo próprio adapter. Se outro campo essencial estiver ausente
ou vazio, o adapter retorna `MISSING_REQUIRED_FIELDS`. Conversões inválidas que
impedem a criação da vaga retornam `VALIDATION_ERROR`. Campos opcionais ausentes
são listados em `optional_fields_missing` e não causam falha. Se um campo
opcional estiver presente mas não puder ser convertido, a vaga é preservada com
esse campo como `None` e a perda é registrada como `IngestionWarning`.

Os campos `remote` e `brazil_eligible` usam três estados: `True` significa
confirmação positiva, `False` confirmação negativa e `None` informação
desconhecida. A ausência desses campos na fonte produz `None`, nunca `False`.

`ingest_batch()` continua processando depois de um erro e devolve as oportunidades
válidas e os erros separadamente. `combine_ingestion_batches()` reúne resultados
de diferentes adapters antes de enviar apenas as oportunidades válidas ao
pipeline.

## Greenhouse público

[Greenhouse](https://www.greenhouse.com/) é uma plataforma usada por empresas
para publicar e administrar processos seletivos. Um job board público é a página
de vagas publicadas por uma empresa. O projeto lê somente o endpoint público de
listagem da [Greenhouse Job Board API](https://developers.greenhouse.io/job-board),
sem API key, login ou acesso ao sistema interno de recrutamento.

```text
Greenhouse public Job Board
→ GreenhouseJobSource
→ GreenhouseJobAdapter
→ JobOpportunity
→ deterministic enrichment
→ pipeline
→ ranking
```

`JobSource` define apenas a responsabilidade de obter registros brutos externos.
`GreenhouseJobSource` monta uma URL validada, faz um único HTTP GET com timeout e
User-Agent e transforma erros HTTP, conexão, timeout e JSON inválido em
`SourceResult`. Uma resposta com zero vagas é um sucesso com status `NO_JOBS`.

`GreenhouseJobAdapter` converte os campos reais do payload público para
`JobOpportunity`. Source e adapter são separados porque obter JSON pela rede é
uma responsabilidade diferente de validar e padronizar cada vaga. O pipeline
continua conhecendo apenas `JobOpportunity` e não contém código do Greenhouse.

A listagem pública fornece título, URL, localização e, com `content=true`, o
conteúdo da descrição. Ela não fornece de forma estruturada e consistente
remoto, elegibilidade para o Brasil, salário, experiência, ferramentas ou
indústria. Esses campos começam como `None`; somente os sinais explícitos
documentados abaixo podem ser enriquecidos localmente.

### Consulta manual de um board real

Identifique o token público na URL do board e informe também o nome de exibição
da empresa:

```bash
PYTHONPATH=src python -m daniel_job_agent.greenhouse_demo BOARD_TOKEN "Company Name"
```

Esse comando realiza uma única consulta controlada, converte as vagas válidas e
mostra até dez oportunidades ordenadas. Ele não envia candidaturas e não deve ser
usado para descobrir tokens ou consultar empresas em massa. A consulta real não
faz parte dos testes automatizados.

A saída também mostra `Jobs received`, `Jobs converted`, `Unique jobs`,
`Duplicates detected`, `KEEP`, `REVIEW` e `REJECT`. A linha de conferência deixa
explícito que oportunidades únicas são a soma das três decisões.

## Lever público

O projeto também lê postings públicos da
[Lever Postings API](https://github.com/lever/postings-api), sem API key, login
ou acesso à Data API privada. Apenas vagas publicadas são consultadas.

```text
Lever public postings
→ LeverJobSource
→ LeverJobAdapter
→ deterministic enrichment
→ pipeline
→ ranking
```

`LeverJobSource` reutiliza o mesmo transporte HTTP, timeout, User-Agent e
tratamento estruturado de erros usado pelo Greenhouse. A validação específica do
Lever espera uma lista JSON. Lista vazia produz `NO_JOBS`, não erro.

`LeverJobAdapter` mapeia título, localização, URL hospedada, descrição e tipo de
contratação quando esses campos aparecem de forma estruturada. Os blocos
textuais oficiais do posting são reunidos no campo `description`; o adapter não
interpreta seu significado. Remoto, elegibilidade para o Brasil, salário, anos,
SaaS, B2B, ferramentas e indústria permanecem `None` até que o enrichment
encontre algum dos sinais explícitos que ele já suporta.

### Consulta manual de um site Lever

Informe explicitamente o slug público e o nome de exibição da empresa:

```bash
PYTHONPATH=src python -m daniel_job_agent.lever_demo COMPANY_SLUG "Company Name"
```

Para um site hospedado na instância europeia:

```bash
PYTHONPATH=src python -m daniel_job_agent.lever_demo COMPANY_SLUG "Company Name" --region eu
```

O comando faz uma única consulta e mostra recebidas, convertidas, warnings,
erros, únicas, duplicatas, decisões e as dez primeiras oportunidades. Não existe
descoberta automática de slugs nem consulta de várias empresas.

## Jobicy público

O [Jobicy Remote Jobs API](https://jobicy.com/jobs-rss-feed) acrescenta uma
fonte de descoberta ampla, sem substituir as consultas por empresa do
Greenhouse e do Lever.

Os três tipos ficam assim: Greenhouse consulta uma empresa específica, Lever
consulta uma empresa específica e Jobicy pesquisa um job board amplo com vagas
de várias empresas. Isso permite iniciar o discovery por mercado e categoria,
mantendo a mesma avaliação local usada para todas as origens.

```text
Jobicy public Remote Jobs API
→ JobicyJobSource
→ JobicyJobAdapter
→ deterministic enrichment
→ pipeline
→ ranking
```

A source faz exatamente um GET e aceita os filtros públicos `count` (de 1 a
100), `geo`, `industry` e `tag`. O adapter preserva ID, título, empresa,
indústria, tipo, geografia, senioridade, descrição, data e a faixa salarial
original (`salaryMin`, `salaryMax`, moeda e período), sem converter moeda nem
anualizar valores. Datas opcionais inválidas geram warning e não eliminam a
oportunidade.

O endpoint público é `https://jobicy.com/api/v2/remote-jobs`, não exige API key
e limita cada resposta a no máximo 100 vagas.

### Consulta manual ampla

O comando padrão usa `geo=latam`, `industry=seller`, `count=100` e nenhum tag:

```bash
PYTHONPATH=src python -m daniel_job_agent.jobicy_demo
```

Os filtros podem ser alterados explicitamente:

```bash
PYTHONPATH=src python -m daniel_job_agent.jobicy_demo --geo americas --industry seller --count 50 --tag "account executive"
```

A consulta real não faz parte dos testes. Respeite o fair use publicado pelo
Jobicy: não consulte a API mais de uma vez por hora. Os dados publicados têm
atraso intencional de seis horas. A integração não agenda consultas, não percorre
páginas automaticamente e não envia candidaturas.

## Remotive pública

A Remotive é a segunda fonte ampla do projeto. Greenhouse e Lever consultam uma
empresa específica; Jobicy e Remotive consultam job boards com vagas de várias
empresas. A integração usa somente o endpoint público
`https://remotive.com/api/remote-jobs`, sem API key.

```text
Remotive Public API
→ RemotiveJobSource
→ RemotiveJobAdapter
→ deterministic enrichment
→ pipeline
→ ranking
```

`RemotiveJobSource` faz exatamente um GET e aceita os filtros `category`,
`company_name`, `search` e `limit`. Quando fornecido, `limit` precisa ser um
inteiro positivo; o projeto não inventa um máximo que a documentação não
especifica. Uma lista `jobs` vazia é um resultado válido com zero vagas.

O adapter preserva ID, URL original da Remotive, título, empresa, categoria,
tipo, data, restrição geográfica, descrição e o salário livre. O texto salarial
fica em `salary_text`, sem extração de faixa, conversão de moeda ou anualização.
Como o endpoint é de vagas remotas, `remote=True`; elegibilidade para o Brasil
permanece `None` quando a restrição geográfica não a confirma.

### Consulta manual de Sales

```bash
PYTHONPATH=src python -m daniel_job_agent.remotive_demo --category sales
```

Também é possível limitar ou refinar uma única consulta:

```bash
PYTHONPATH=src python -m daniel_job_agent.remotive_demo --category sales --search "account executive" --limit 100
```

A Remotive recomenda baixa frequência, aproximadamente no máximo quatro
consultas por dia, e as vagas exibidas pela API têm atraso aproximado de 24
horas. Não há polling, retries agressivos nem múltiplas buscas automáticas.
Qualquer saída futura deve manter a URL original e identificar `Remotive` como
fonte, conforme os termos de atribuição. A consulta real não faz parte dos testes.

## Discovery multi-source

`MultiSourceDiscovery` executa uma consulta Jobicy e uma consulta Remotive,
converte cada resposta com seu próprio adapter e reúne as oportunidades válidas
antes do enrichment e do pipeline global.

```text
Jobicy  ─┐
         ├→ MultiSourceDiscovery → global dedup → pipeline → ranking
Remotive ┘
```

As configurações padrão ficam em estruturas pequenas e alteráveis:

- Jobicy: `geo=latam`, `industry=seller`, `count=100`, sem `tag`;
- Remotive: `category=sales`, sem `search`, empresa ou limite.

Cada fonte é consultada exatamente uma vez. Uma falha da Jobicy não interrompe
a Remotive, e uma falha da Remotive não interrompe a Jobicy. O resultado mantém
separadamente status, mensagem de falha, recebidas, convertidas, warnings e erros
de ingestão por fonte. Essas são as métricas source-level.

Depois, todas as vagas convertidas passam uma vez pelo enrichment existente. O
pipeline aplica a deduplicação global, inclusive entre fontes, e produz uma
única contagem de oportunidades únicas, decisões e ranking. Essas são as
métricas globais. Não há merge: a primeira vaga equivalente mantém seus dados e
sua source, enquanto a duplicata fica registrada. URLs e atribuição da Remotive
continuam preservadas.

### Demo multi-source

```bash
PYTHONPATH=src python -m daniel_job_agent.discovery_demo
```

O demo mostra o resumo de cada fonte, tolerância a falhas, contagens globais e
as 15 primeiras oportunidades do ranking consolidado. Ele faz no máximo uma
consulta por fonte e não adiciona tags ou searches automáticos.

## Estratégia multi-query controlada

`SearchStrategy` centraliza o nome e todas as queries Jobicy e Remotive. O
objetivo não é maximizar requests, mas combinar uma consulta ampla com poucas
consultas direcionadas que possam encontrar vagas fora da taxonomia principal.

```text
Broad queries ─────┐
Targeted queries ──┼→ global dedup → pipeline → ranking
Multiple sources ──┘
```

A estratégia padrão foi calibrada após uma execução full com 70,4% de duplicação
e nenhum ganho incremental. Agora o modo padrão/broad usa somente duas queries:

- Jobicy broad: `geo=latam`, `industry=seller`, sem tag;
- Remotive broad: `category=sales`.

O modo full preserva toda a infraestrutura anterior, com quatro queries por
fonte e no máximo oito requests:

| Fonte | Query | Tipo |
|---|---|---|
| Jobicy | `geo=latam`, `industry=seller`, sem tag | broad |
| Jobicy | `tag=account executive` | targeted |
| Jobicy | `tag=business development` | targeted |
| Jobicy | `tag=sales development` | targeted |
| Remotive | `category=sales` | broad |
| Remotive | `search=account executive` | targeted |
| Remotive | `search=business development` | targeted |
| Remotive | `search=sales development` | targeted |

Os termos cobrem Closing Sales, Business Development e o grupo SDR/BDR sem uma
query para cada sinônimo. Limites menores podem ser configurados entre zero e
quatro por fonte; a broad permanece primeira quando alguma query é selecionada.
Uma falha fica isolada à query e não interrompe as demais.

Cada resultado registra source, nome da query, recebidas, convertidas, warnings,
erros e eventual falha. A provenance associa a vaga principal a chaves como
`jobicy:broad_latam_sales` e `jobicy:account_executive`. Ela serve para cobertura
e debug: aparecer em várias queries não adiciona pontos ao Match Score.

Todas as oportunidades convergem para a deduplicação existente. Duplicatas em
queries da mesma fonte são intra-source; Jobicy versus Remotive são cross-source.
Não há merge, e o primeiro registro equivalente continua sendo o principal.

A baseline broad usa localmente os resultados broad da mesma execução, sem
requests extras. O ganho incremental é `unique global - unique broad` e `KEEP
global - KEEP broad`. Também são reportados resultados brutos, taxa de
duplicação, KEEP rate, cobertura por fonte e vagas achadas por múltiplas queries.

### Query efficiency e recomendação

`QueryEfficiency` mede se uma query encontrou algo novo, separadamente do Match
Score, que mede a aderência de uma vaga ao perfil. A avaliação é marginal e
respeita a ordem da estratégia: cada query é comparada somente com as que vieram
antes. Volume bruto não torna uma query útil.

Por padrão, uma query é `useful` quando adiciona pelo menos uma vaga única ou um
KEEP. Uma query com 50 resultados totalmente duplicados é `wasted`. O critério é
configurável e o relatório também mostra contribuição de KEEP, REVIEW e REJECT,
duplicatas, duplication rate, requests por vaga única e requests por KEEP.

`recommend_search_strategy()` sempre mantém broad e sugere remover targeted com
zero ganho incremental de unique e KEEP naquela execução. A recomendação cria um
novo objeto em memória: não altera a estratégia executada e não salva histórico.
Uma query inútil hoje pode ser útil em outra data; somente persistência futura
poderá avaliar comportamento histórico.

### Demo multi-query

Modo conservador padrão:

```bash
PYTHONPATH=src python -m daniel_job_agent.multi_query_demo --mode broad
```

Modo completo para nova medição controlada:

```bash
PYTHONPATH=src python -m daniel_job_agent.multi_query_demo --mode full
```

O demo mostra estratégia, resumo por query, métricas, cobertura e top 20. A
execução é manual, sequencial e não agenda novas consultas.

## Enriquecimento determinístico

`enrich_job()` recebe uma `JobOpportunity` e cria uma cópia com poucos sinais
estruturados encontrados de maneira explícita na descrição. Ele não calcula
score, não decide retenção e não modifica `ApplicationTracking`.

As regras atuais reconhecem somente:

- anos em formatos simples como `4+ years`, `5 years of experience` e
  `6-8 years`; em ranges, o mínimo informado é usado;
- `entire sales process`, `full sales cycle`, `complete sales cycle`,
  `end-to-end sales cycle` e `qualification to closing`;
- `outbound`, `direct prospecting`, `cold outreach` e `prospecting`;
- menção explícita a `inbound`;
- termos explícitos `B2B` e `SaaS`.

O título também pode fornecer um sinal geográfico objetivo. `LATAM`,
`Latin America` e `Brazil` contam como elegibilidade positiva; `USA`,
`United States` e `US-only` contam como incompatibilidade. Ausência desses termos
continua sendo `UNKNOWN`.

As regras são deliberadamente conservadoras. Elas não tentam interpretar
senioridade, salário, ferramentas, indústria, elegibilidade ou remoto a partir
de frases ambíguas. Ausência de informação não vira `False`, gap ou rejeição.

## Role Family, Seniority e Career Fit

A avaliação com `CandidateProfile` agora separa três conceitos antes de calcular
o Match Score:

```text
Role
→ Role Family
→ Seniority
→ Candidate Career Fit
→ Match Score
```

`RoleFamily` agrupa títulos em famílias expansíveis, como `CLOSING_SALES`,
`SALES_DEVELOPMENT`, `ACCOUNT_MANAGEMENT`, `SALES_LEADERSHIP`, `PRE_SALES`,
`CUSTOMER_SUCCESS`, `PARTNERSHIPS`, Marketing, Engineering, Product, Operations,
Writing/Content, Finance, Legal e HR/Recruiting. A precedência protege títulos
compostos: `Sales Engineer` e `Technical Sales Specialist` são Pre-Sales, não
Engineering; `Technical Account Manager` é Account Management; `Product
Marketing Manager` é Marketing. `Writer`, `Freelance Writer` e `Copywriter` são
Writing/Content.

`Seniority` usa somente sinais explícitos do título: Entry, Individual
Contributor, Senior IC, Manager, Director, VP/Executive ou Unknown. Descrição,
salário e frases sobre liderar equipes não participam dessa classificação.
`Account Manager`, `Technical Account Manager` e `Customer Success Manager` são
tratados como títulos IC, pois `Manager` nesses casos normalmente nomeia a
função, não confirma gestão de pessoas.

O perfil configura suas famílias principais, relevantes, stretch e fora do
foco. Para o perfil atual, Closing Sales é a prioridade principal; Account
Management, Sales Development, Customer Success e Partnerships são relevantes;
Sales Leadership e Pre-Sales são stretch. As demais famílias explicitamente
configuradas ficam fora do foco.

Role Family é um sinal forte: os pesos padrão são `+65` para a família principal,
`+45` para relevante, `+25` para stretch, `+5` para desconhecida e `-70` para
fora do foco. Esse bloco substitui os antigos pontos de keyword no cálculo com
perfil, evitando double counting. O cálculo legado sem perfil permanece igual.

Senioridade é sempre um soft signal. IC e Senior IC geram explicações positivas
sem pontos extras; Entry recebe `-15`, Manager `-3`, Director `-10` e
VP/Executive `-15`. Unknown não perde pontos e aparece em `unknowns`. Entry,
Director ou VP nunca causam `REJECT` isoladamente. Director/VP em Sales
Leadership normalmente ficam em `REVIEW`; uma família explicitamente fora do
foco pode gerar `REJECT` mesmo que a descrição mencione customers ou sales.

Exemplos conceituais:

- Account Executive: Closing Sales + IC, forte candidato a `KEEP`;
- Graduate SDR: Sales Development + Entry, válido mas abaixo de um AE comparável;
- Regional Sales Director: Sales Leadership + Director, stretch e `REVIEW`;
- Sales Engineer: Pre-Sales, stretch sem rejeição automática;
- Freelance Copywriter: Writing/Content, fora do foco e `REJECT`.

## Pipeline local

O pipeline recebe várias `JobOpportunity` e um `CandidateProfile`, aplica as
mesmas etapas a cada item e devolve um `PipelineResult` estruturado:

```text
JobOpportunity[]
→ normalization
→ deduplication
→ match evaluation
→ retention
→ ranking
→ processed results
```

Cada `ProcessedOpportunity` contém a vaga original, uma cópia normalizada usada
no processamento, score, razões positivas, gaps, unknowns, decisão e posição no
ranking. A vaga original e seu `ApplicationTracking` não são modificados.

O resultado agregado informa totais recebidos, oportunidades únicas, duplicatas
e quantidades de `KEEP`, `REVIEW` e `REJECT`. As propriedades `keep`, `review` e
`reject` permitem inspecionar separadamente cada grupo.

### Deduplicação

O pipeline reutiliza as regras existentes: duas vagas são duplicadas quando têm
a mesma URL normalizada ou a mesma empresa e cargo normalizados. O primeiro item
recebido é preservado como principal e a duplicata é registrada em
`duplicate_records`.

Não existe merge de dados nesta etapa. Portanto, se a duplicata trouxer mais
detalhes, esses dados não são incorporados automaticamente ao registro principal.

### Ranking

Todas as oportunidades únicas são ordenadas por:

1. Match Score, do maior para o menor;
2. decisão, na ordem `KEEP`, `REVIEW`, `REJECT`;
3. empresa, cargo e URL normalizados, para desempate estável.

Vagas `REJECT` continuam armazenadas e aparecem no ranking. Isso mantém o
processamento auditável: é possível conferir o motivo da rejeição e ajustar as
regras futuramente sem perder o registro original.

## Demonstração local

O projeto inclui 12 registros brutos fictícios em três formatos, sem informações
de empresas reais e com uma duplicata entre duas fontes. Para executar ingestão
e pipeline juntos:

```bash
PYTHONPATH=src python -m daniel_job_agent.demo
```

A demonstração imprime falhas de conversão, totais, decisões e um ranking curto.
No dataset atual, são recebidos 12 registros: dez são convertidos, um gera warning
de salário e dois falham por campos obrigatórios. O pipeline encontra nove
oportunidades únicas, uma duplicata, seis `KEEP`, uma `REVIEW` e duas `REJECT`.

## Acompanhamento manual do CRM

Cada `JobOpportunity` possui um campo `tracking`. Ele guarda o status da
candidatura, data de aplicação, contato do recrutador, próximo passo e notas.
Esses dados ficam agrupados em `ApplicationTracking` para que futuras
atualizações automáticas do anúncio não os sobrescrevam.

Os status disponíveis começam em `NOT_APPLIED` e incluem as etapas de aplicação,
entrevistas, oferta, rejeição e desistência.

## Histórico local com SQLite

SQLite é um banco de dados leve incluído na biblioteca padrão do Python. Ele
guarda todo o histórico em um único arquivo local, sem servidor e sem pacote
externo. O fluxo agora pode terminar em:

```text
Discovery
→ Pipeline
→ SQLite Repository
→ History
```

`JobRepository` centraliza todo o SQL e cria a tabela `opportunities`
automaticamente com `CREATE TABLE IF NOT EXISTS`. O caminho padrão é
`data/job_agent.db`, mas testes e demonstrações podem usar `:memory:` ou um
arquivo temporário. Arquivos `*.db`, `*.sqlite` e `*.sqlite3` são ignorados pelo
Git e nunca devem armazenar secrets, credenciais, tokens ou conteúdo de `.env`.

A tabela preserva identificação, conteúdo da vaga, remuneração, datas,
avaliação do pipeline, estado da vaga e CRM manual. Listas e explicações são
JSON text simples. Booleanos mantêm três estados no SQLite: `1` para `True`, `0`
para `False` e `NULL` para desconhecido. Timestamps são gravados em UTC com
offset explícito.

Cada sincronização classifica a oportunidade como:

- `NEW`: ainda não existe; recebe `first_seen_at` e `last_seen_at`;
- `EXISTING`: existe e não mudou; atualiza `last_seen_at` e `last_checked`;
- `UPDATED`: existe e algum dado automático mudou; atualiza os dados
  automáticos e os timestamps.

`first_seen_at` registra quando a vaga entrou no histórico e não muda.
`last_seen_at` registra a execução mais recente em que ela apareceu. Ausência em
uma execução não fecha a vaga e não existe inferência automática de reabertura.

A identidade segue a mesma base da deduplicação existente, nesta ordem: URL
normalizada; `external_id` junto da fonte; e, como fallback, empresa e cargo
normalizados. A sincronização nunca sobrescreve status de candidatura, datas de
aplicação, recrutador, próximo passo ou notas. Esses campos só mudam por uma
operação manual explícita, como `update_tracking`.

Para executar a demonstração offline com duas sincronizações consecutivas:

```bash
PYTHONPATH=src python3 -m daniel_job_agent.persistence_demo
```

Ela usa um banco temporário, mostra `NEW`, `EXISTING` e `UPDATED`, e confirma que
o CRM manual permanece após uma atualização automática. A função
`sync_opportunities` aceita diretamente um `PipelineResult` ou uma coleção de
`ProcessedOpportunity`; ela não executa discovery.

## Execução end-to-end real

O comando principal executa explicitamente o primeiro fluxo real completo:

```text
Jobicy broad + Remotive broad
→ MultiSourceDiscovery
→ enrichment
→ pipeline e ranking
→ SQLite
→ NEW / EXISTING / UPDATED
```

A estratégia operacional padrão é a broad já centralizada em
`create_default_search_strategy`: Jobicy usa `geo=latam`, `industry=seller` e
`count=100`; Remotive usa `category=sales`. O orquestrador apenas converte essa
configuração para `MultiSourceDiscovery`: não replica adapters, enriquecimento,
score, deduplicação nem SQL.

Para fazer a primeira execução real manualmente:

```bash
PYTHONPATH=src python3 -m daniel_job_agent.run_agent --db data/job_agent.db
```

`--mode broad` também pode ser informado explicitamente. Para experimentar com
outro banco, use por exemplo `--db /tmp/test-job-agent.db`. O relatório mostra
contagens de discovery e persistência, fontes com falha e até dez oportunidades
NEW, priorizando `KEEP` e depois `REVIEW`. Vagas `REJECT` também são persistidas
para histórico e auditoria, mas não aparecem nessa lista curta.

Na primeira execução, vagas ainda desconhecidas são `NEW`. Nas seguintes, vagas
iguais são `EXISTING` e mudanças automáticas relevantes geram `UPDATED`. Todo o
CRM manual continua preservado. Se uma fonte falhar, a outra ainda é processada;
se ambas falharem, a execução retorna um resumo vazio e o banco existente não é
alterado. O lifecycle descrito abaixo só conta ausência para fontes concluídas
sem falha de consulta, ingestão ou persistência.

### Apagar o banco somente em desenvolvimento

Não existe comando automático para reset. Se for realmente necessário começar
um ambiente de desenvolvimento do zero, encerre qualquer execução e apague
manualmente somente o arquivo escolhido, por exemplo `data/job_agent.db`.

**Atenção:** essa ação apaga permanentemente todo o histórico e os campos
manuais do CRM daquele banco. Confirme cuidadosamente o caminho e mantenha uma
cópia quando os dados forem importantes. Nunca apague bancos por rotina.

## CRM local

O CRM local é uma camada segura de leitura e edição sobre o `JobRepository`.
SQLite continua sendo a fonte principal dos dados; o CRM não mantém uma segunda
cópia e não contém SQL. O fluxo preparado para evoluções futuras é:

```text
Discovery
→ Pipeline
→ SQLite
→ CRM Layer
→ future Google Sheets
```

Cada linha é representada por um `CRMRecord`. Os campos automáticos — empresa,
cargo, URL, fonte, localização, score, decisão, família, senioridade, salários,
datas de discovery, estado e explicações — são controlados pelo agente. Os únicos
campos manuais são:

- `application_status`;
- `applied_date`;
- `recruiter_name`;
- `recruiter_email`;
- `next_step`;
- `next_step_date`;
- `notes`.

`LocalCRM.update_manual_fields` rejeita explicitamente qualquer tentativa de
alterar campos automáticos. Atualizações parciais não apagam outros dados
manuais, e sincronizações posteriores do agente preservam todo o CRM. As
operações usam o `internal_id` estável do SQLite, nunca a posição no ranking.

Para listar o resumo do banco:

```bash
PYTHONPATH=src python3 -m daniel_job_agent.crm_cli list --db data/job_agent.db
```

Filtros opcionais incluem `--status`, `--decision`, `--source`,
`--still-open`, `--minimum-score` e `--order newest`.

Para registrar uma candidatura e uma nota:

```bash
PYTHONPATH=src python3 -m daniel_job_agent.crm_cli update 12 \
  --db data/job_agent.db \
  --status APPLIED \
  --applied-date 2026-08-15 \
  --notes "Applied via company website"
```

Datas manuais usam obrigatoriamente `YYYY-MM-DD`. Uma data inválida produz uma
mensagem amigável antes de qualquer alteração no registro.

Para visualizar o contrato tabular sem gerar CSV nem acessar Google Sheets:

```bash
PYTHONPATH=src python3 -m daniel_job_agent.crm_cli export-preview \
  --db data/job_agent.db --limit 5
```

A ordem estável das colunas é definida em `CRM_COLUMNS`: ID, empresa, cargo,
score, decisão, localização, fonte, URL, datas da vaga, estado, CRM manual,
explicações, família, senioridade, remuneração e timestamps do histórico. Listas
são exibidas de modo determinístico, separadas por ` | `, e a URL permanece
texto puro.

### Contrato com Google Sheets

O agente escreve as colunas automáticas definidas em `AUTOMATIC_FIELDS`. O
usuário pode editar as colunas de `MANUAL_FIELDS`, e somente essas mudanças
podem voltar ao SQLite. Google Sheets é uma interface para o CRM, não o banco
principal nem a fonte de verdade.

## Google Sheets como interface visual

O Google Sheets pode receber uma cópia visual do CRM, mas o SQLite continua
sendo a fonte de verdade:

```text
SQLite → push → Google Sheets → edição humana → pull → SQLite
```

`push` e `pull` são comandos explícitos e independentes. O push reescreve a tab
com KEEP, REVIEW e REJECT na ordenação padrão, mas antes lê a tab e preserva os
sete campos manuais pelo `Internal ID`. Assim, uma edição humana ainda não
importada não é silenciosamente destruída. Se os headers ou IDs existentes não
forem seguros para essa reconciliação, o push falha antes de limpar a tab.

O pull lê os headers, encontra `Internal ID` e as sete colunas manuais pelos
nomes amigáveis e ignora completamente qualquer alteração em campo automático.
Headers ausentes ou duplicados abortam todo o pull antes de updates. Depois da
validação estrutural, um erro em uma linha é registrado sem impedir as demais.
Célula vazia limpa campos manuais opcionais; `Application Status` não pode ficar
vazio porque o domínio exige um dos status existentes.

### Dependências e OAuth desktop

A integração usa diretamente as bibliotecas oficiais
`google-api-python-client`, `google-auth-httplib2` e `google-auth-oauthlib`. Não
usa `gspread` nem service account. Instale as dependências com:

```bash
python3 -m pip install -r requirements.txt
```

O único scope solicitado é:

```text
https://www.googleapis.com/auth/spreadsheets
```

Ele permite ler e escrever spreadsheets, sem solicitar Gmail, Calendar ou
acesso completo ao Google Drive.

Configuração manual no Google Cloud:

1. Crie ou selecione um projeto no Google Cloud Console.
2. Ative a Google Sheets API.
3. Configure a tela de consentimento OAuth e adicione sua conta como usuário de
   teste, se o aplicativo ainda estiver em modo de teste.
4. Crie um OAuth Client ID do tipo **Desktop app**.
5. Baixe o JSON do cliente e salve-o localmente como `credentials.json` na raiz
   do projeto, ou informe outro caminho com `--credentials`.
6. Crie manualmente uma spreadsheet no Google Sheets.
7. Copie o spreadsheet ID da URL: é o texto entre `/d/` e `/edit`.

`credentials.json`, `token.json` e padrões equivalentes estão no `.gitignore`.
Eles nunca devem ser commitados, copiados para `.env.example` nem armazenados no
SQLite.

No primeiro push ou pull, o navegador será aberto para login e autorização. Após o
consentimento, o token fica no caminho local configurado, com permissão restrita
ao usuário. Execuções seguintes reutilizam esse token e fazem refresh quando
necessário. Client secret, access token e refresh token não são impressos.

### Executar o push

Crie a spreadsheet manualmente e execute:

```bash
PYTHONPATH=src python3 -m daniel_job_agent.google_sheets_cli push \
  --db data/job_agent.db \
  --spreadsheet-id SHEET_ID \
  --sheet-name "Job CRM" \
  --credentials credentials.json \
  --token token.json
```

Se a tab não existir, ela é criada na spreadsheet fornecida. A integração não
cria uma spreadsheet nova. A linha de headers fica congelada e em negrito; a
região recebe filtro e ajuste de colunas; Notes, Reasons, Gaps e Unknowns usam
quebra de texto. A URL é enviada como texto puro.

O Match Score recebe cinco faixas visuais: verde forte para 90–100, verde suave
para 75–89, amarelo para 60–74, laranja para 40–59 e vermelho claro para 0–39.
Decision usa verde para KEEP, amarelo para REVIEW e vermelho claro para REJECT.
Application Status possui dropdown com exatamente os valores de
`ApplicationStatus` e cores distintas para não aplicado, aplicado, etapas em
andamento, oferta, rejeição e desistência. As sete colunas manuais recebem um
fundo sutil, sem esconder a formatação condicional do status.

### Executar o pull

Depois de editar status, datas, recrutador, próximo passo ou notas no Sheets:

```bash
PYTHONPATH=src python3 -m daniel_job_agent.google_sheets_cli pull \
  --db data/job_agent.db \
  --spreadsheet-id SHEET_ID \
  --sheet-name "Job CRM" \
  --credentials credentials.json \
  --token token.json
```

O resumo informa linhas lidas, válidas, atualizadas, inalteradas, ignoradas e
com erro. Nenhum valor de credencial aparece nesse relatório.

Fluxo cotidiano recomendado:

1. Execute discovery e persistência com `run_agent`.
2. Faça `push` para atualizar os dados automáticos e o visual do CRM.
3. Revise as vagas no Sheets.
4. Edite somente status, datas manuais, recrutador, próximo passo e notas.
5. Faça `pull`.
6. O SQLite recebe somente os campos manuais validados.

A ordem visual possui 33 colunas: Company, Role, Match Score, Decision,
Application Status, Next Step, Next Step Date, Notes, Location, Source, Job URL,
Applied Date, Recruiter Name, Recruiter Email, Date Found, Date Posted, Still
Open, Lifecycle Status, Closed At, Positive Reasons, Potential Gaps, Unknowns,
Role Family, Seniority, Salary Min, Salary Max, Salary Currency, Salary Period,
Salary Text, First Seen, Last Seen, Last Checked e Internal ID. Lifecycle e
Closed At são automáticos; o ID fica no final.

## Ciclo de vida das vagas

`ApplicationStatus` descreve a candidatura do Daniel. `JobLifecycleStatus`
descreve o anúncio e possui `OPEN`, `POSSIBLY_CLOSED`, `CLOSED` e `UNKNOWN`.
Esses estados são independentes: uma candidatura pode continuar `INTERVIEW`
mesmo que o anúncio passe a `CLOSED`.

O fluxo real agora é:

```text
Discovery
→ Sync found jobs
→ Source success check
→ Missing reconciliation
→ Lifecycle update
→ SQLite
→ CRM / Google Sheets
```

A ausência em uma execução nunca fecha uma vaga. A política padrão é:

- zero misses: `OPEN`;
- um miss: continua `OPEN` (ou `UNKNOWN` em um registro antigo ainda não visto);
- dois misses consecutivos: `POSSIBLY_CLOSED`;
- três misses consecutivos: `CLOSED`.

Os limites ficam em `LifecyclePolicy`, portanto testes ou usos futuros podem
configurá-los sem números mágicos. Um miss só é contado quando a fonte daquela
vaga foi executada com sucesso e sem erros de ingestão. Se Jobicy falhar, vagas
Jobicy não mudam; sucesso com zero resultados pode contar ausência. Remotive
segue a mesma regra. Greenhouse e Lever não são reconciliadas em uma rodada que
executou apenas as fontes broad.

Quando uma vaga `POSSIBLY_CLOSED` ou `CLOSED` reaparece, ela volta a `OPEN`,
zera os misses, preserva `first_seen_at` e o CRM manual e recebe `reopened_at`.
`still_open` é uma projeção compatível: `OPEN=True`, `CLOSED=False` e
`POSSIBLY_CLOSED`/`UNKNOWN=None`. `closed_at` é preenchido no fechamento e limpo
na reabertura, enquanto `reopened_at` preserva a transição mais recente.

A arquitetura também aceita `VerificationStatus` explícito no futuro, mas não
interpreta 404 como fechamento e não consulta individualmente URLs nesta etapa.

O banco usa `PRAGMA user_version = 3`. Ao abrir um banco anterior, o repository
consulta `PRAGMA table_info` e executa `ALTER TABLE ADD COLUMN` somente para
colunas lifecycle ausentes. A migração é idempotente, não usa `DROP TABLE` e
preserva vagas e CRM existentes. Não é necessário apagar `data/job_agent.db`.

No Google Sheets, `Lifecycle Status` recebe verde sutil para `OPEN`,
amarelo/laranja para `POSSIBLY_CLOSED`, vermelho/cinza para `CLOSED` e cinza para
`UNKNOWN`. `Lifecycle Status` e `Closed At` são automáticos e nunca retornam ao
SQLite pelo pull.

Para ver a sequência completa sem rede e usando banco temporário:

```bash
PYTHONPATH=src python3 -m daniel_job_agent.lifecycle_demo
```

## Weekly Automation on macOS

O macOS possui um scheduler nativo chamado `launchd`. Um **LaunchAgent** é uma
tarefa pertencente ao usuário: não usa `sudo`, não precisa deixar o Terminal
aberto e volta a ficar disponível quando o usuário entra novamente no Mac. Esta
etapa gera automaticamente `~/Library/LaunchAgents/com.daniel.job-agent.plist`;
não é necessário editar XML.

O horário padrão é **toda segunda-feira às 08:00**, no horário local do Mac. O
plist chama diretamente:

```text
/Users/danielparreiras/job-search-agent/.venv/bin/python
```

Portanto, a execução não depende de `source .venv/bin/activate`. O working
directory também é fixado no diretório do projeto. O fluxo semanal reutiliza o
mesmo `DanielJobAgent`: broad discovery, enrichment, ranking, SQLite sync e
lifecycle. Se Sheets estiver configurado, o push acontece depois da
persistência; uma falha de Sheets não desfaz vagas salvas e produz
`PARTIAL_FAILURE` (exit code 2). Sucesso usa exit code 0 e falha significativa
usa exit code 1.

### Configuração local

Copie `.env.example` para `.env` e ajuste somente o arquivo local, ignorado pelo
Git:

```dotenv
JOB_AGENT_DB=data/job_agent.db
JOB_AGENT_WEEKDAY=Monday
JOB_AGENT_HOUR=8
JOB_AGENT_MINUTE=0
GOOGLE_SPREADSHEET_ID=
GOOGLE_SHEET_NAME=Job CRM
GOOGLE_CREDENTIALS_PATH=credentials.json
GOOGLE_TOKEN_PATH=token.json
```

Deixe `GOOGLE_SPREADSHEET_ID` vazio para não sincronizar Sheets. Quando ele
estiver preenchido, `credentials.json`, `token.json` e o ID precisam estar
disponíveis antes da instalação. A execução agendada **nunca abre OAuth**: faça
ao menos um push/pull manual antes para criar `token.json`. O plist contém
somente caminhos e horário; não contém ID da planilha, tokens ou credentials.

Para alterar o horário, edite `JOB_AGENT_WEEKDAY`, `JOB_AGENT_HOUR` e
`JOB_AGENT_MINUTE` e execute `uninstall` seguido de `install` para regenerar o
plist. Os nomes de weekday são em inglês (`Monday`, `Tuesday`, etc.).

### Mini manual

Execute os comandos na raiz do projeto:

INSTALL:

```bash
PYTHONPATH=src python3 -m daniel_job_agent.scheduler_cli install
```

CHECK:

```bash
PYTHONPATH=src python3 -m daniel_job_agent.scheduler_cli status
```

PAUSE:

```bash
PYTHONPATH=src python3 -m daniel_job_agent.scheduler_cli stop
```

RESUME:

```bash
PYTHONPATH=src python3 -m daniel_job_agent.scheduler_cli start
```

RUN NOW:

```bash
PYTHONPATH=src python3 -m daniel_job_agent.scheduler_cli run-now
```

REMOVE:

```bash
PYTHONPATH=src python3 -m daniel_job_agent.scheduler_cli uninstall
```

`stop` desabilita e descarrega a tarefa, mas mantém o plist. Ela pode ficar
parada por tempo indefinido; `start` habilita e carrega o mesmo LaunchAgent
novamente. Nenhuma dessas ações apaga SQLite, CRM, histórico, token, credentials,
planilha ou logs. `uninstall` descarrega a tarefa e remove apenas o plist gerado;
também não apaga esses dados. Após `install` ou `start`, a configuração persiste
sem Terminal aberto e volta após reiniciar o Mac e fazer login. Se foi executado
`stop`, o estado desabilitado persiste até `start`.

`run-now` chama exatamente o workflow semanal sem alterar Monday 08:00. Um lock
em `data/weekly_run.lock` impede duas execuções simultâneas. Se o PID do lock
estiver ativo, a segunda execução termina com mensagem segura; um lock cujo PID
não existe é removido, e o lock é limpo após sucesso ou erro normal.

### Logs e histórico

O LaunchAgent grava saída e erros separadamente:

```text
logs/job_agent.out.log
logs/job_agent.err.log
```

`logs/` é ignorado pelo Git. Antes de cada workflow, arquivos maiores que 5 MiB
são reduzidos ao 1 MiB mais recente. O resumo informa discovery, persistência,
lifecycle, Sheets e a etapa que falhou, sem imprimir secrets.

O schema SQLite versionado em `PRAGMA user_version = 3` inclui `agent_runs` com
horários, status, fontes, contagens, transições lifecycle, resultado de Sheets e
um resumo curto de erro. Payloads, tokens e credentials não são armazenados. O
comando `status` mostra a instalação, se está carregada, horário, caminhos e a
execução mais recente. A migração é idempotente e preserva todas as vagas e os
campos manuais do CRM.

### Limitações da execução local

- Mac ligado, usuário logado: o LaunchAgent pode executar no horário.
- Mac dormindo: `launchd` pode executar ao acordar, mas não há garantia de
  execução exatamente às 08:00.
- Mac desligado: nada executa; não existe servidor remoto para recuperar aquele
  horário.
- Usuário sem login: um LaunchAgent de usuário não está ativo; ele volta a ficar
  disponível no próximo login.

Esta etapa não configura wake timers nem altera opções de energia.

## Weekly Reports

Cada `weekly_run` gera um snapshot executivo da rodada depois de discovery,
persistência, lifecycle e Sheets. O relatório serve para entender o resultado
em poucos segundos e inclui metadata da execução, saúde das fontes, contagens de
discovery e SQLite, eventos lifecycle, snapshot do CRM por `ApplicationStatus`,
até dez novas vagas relevantes e até dez vagas atualizadas. Vagas `KEEP` vêm
antes de `REVIEW`; `REJECT` nunca aparece em **Best new opportunities**.

Os arquivos ficam em `reports/`, que é ignorado pelo Git:

```text
reports/2026-08-17_080000_42.md  # snapshot histórico e imutável da run 42
reports/latest.md                # cópia do relatório mais recente
```

`latest.md` é substituído somente quando um novo relatório termina de ser
salvo. Os arquivos identificados por timestamp e `run_id` não são apagados nesta
etapa. Como o CRM é contado durante a geração, editar uma candidatura depois não
altera retroativamente um Markdown antigo.

Para consultar o relatório mais recente:

```bash
PYTHONPATH=src python3 -m daniel_job_agent.report_cli latest
```

Para consultar metadata das dez últimas execuções diretamente de `agent_runs`,
sem reconstruir histórico lendo Markdown:

```bash
PYTHONPATH=src python3 -m daniel_job_agent.report_cli history --limit 10
```

Para abrir uma rodada específica:

```bash
PYTHONPATH=src python3 -m daniel_job_agent.report_cli show 42
```

Uma rodada sem vagas novas continua sendo sucesso e diz claramente que não há
novos `KEEP` ou `REVIEW`. Se uma fonte ou Sheets falhar, o relatório mostra
`PARTIAL_FAILURE` e uma causa curta; se discovery falhar completamente, ainda é
tentado um relatório `FAILURE`. Uma falha ao gerar o próprio Markdown não
reverte discovery, SQLite ou lifecycle: ela é registrada separadamente em
`agent_runs` e no log.

Logs e reports têm papéis diferentes. `logs/job_agent.*.log` preserva mensagens
técnicas para diagnóstico; o Markdown é um resumo humano. O scheduler não mudou:
`run-now` e a execução de segunda-feira usam o mesmo lock e o relatório é criado
dentro desse workflow protegido. Não há email, Slack, PDF, dashboard ou nova tab
no Google Sheets.

Para ver um exemplo fictício sem rede, banco real ou Sheets:

```bash
PYTHONPATH=src python3 -m daniel_job_agent.report_demo
```

## Como funciona o fluxo de decisão

Para cada vaga fornecida localmente ao Python:

1. Empresa, cargo e localização podem ter espaços corrigidos sem alterar
   agressivamente os nomes.
2. O cargo recebe prioridade `HIGH`, `MEDIUM` ou `IRRELEVANT`.
3. A localização recebe elegibilidade `ELIGIBLE`, `NOT_ELIGIBLE` ou `UNKNOWN`.
4. Quando um perfil é fornecido, a vaga também é comparada aos cargos desejados,
   anos de experiência, ferramentas e indústrias conhecidas.
5. O Match Score soma pesos documentados para os sinais disponíveis. O resultado
   sempre fica entre 0 e 100.
6. A avaliação apresenta razões positivas, possíveis gaps e informações
   desconhecidas.
7. A decisão final é:
   - `KEEP`: cargo relevante, localização elegível e bom score;
   - `REVIEW`: faltam informações ou o título ainda não é reconhecido;
   - `REJECT`: cargo explicitamente irrelevante ou localização incompatível.

A deduplicação considera duas vagas iguais quando a URL normalizada coincide ou
quando empresa e cargo normalizados coincidem. Parâmetros de rastreamento da URL
não criam uma vaga nova.

Os pesos do score ficam em `ScoreWeights`, portanto podem ser ajustados sem
alterar o restante do fluxo. As funções de regra apenas leem a vaga: elas não
mudam o anúncio nem o acompanhamento manual.

## CandidateProfile

`CandidateProfile` é uma representação estruturada das informações profissionais
usadas na comparação. Ele contém cargos principais e secundários, experiência,
preferências de mercado e trabalho, ferramentas, indústrias e preferências de
compensação quando conhecidas.

`create_daniel_profile()` cria o perfil padrão do projeto. Salários permanecem
desconhecidos porque ainda não existe uma representação completa de moeda e
período. Nenhuma informação pessoal desnecessária é armazenada.

## Match Score e explicabilidade

`evaluate_match(job, profile)` retorna um `MatchEvaluation` com:

- `score`: número determinístico entre 0 e 100;
- `positive_reasons`: sinais de boa aderência encontrados;
- `potential_gaps`: diferenças que merecem atenção, mas não eliminam a vaga;
- `unknowns`: informações que a vaga ou o perfil não fornecem.

Informação ausente não reduz o score. Por exemplo, uma vaga que não informa as
ferramentas utilizadas recebe um `unknown`, não uma penalização por ferramentas.
As explicações são produzidas por regras locais, sem IA.

O uso anterior continua válido: `calculate_match_score(job)` preserva o cálculo
da etapa anterior. Para comparar com o perfil, use
`calculate_match_score(job, profile=profile)` ou `evaluate_match(job, profile)`.

## Hard filters e soft signals

Hard filters representam incompatibilidades objetivas. Nesta etapa são poucos:
localização explicitamente incompatível com Brasil/LATAM e cargo explicitamente
fora do objetivo comercial. Eles podem resultar em `REJECT`.

Soft signals ajudam a priorizar sem eliminar automaticamente. Cargo secundário,
anos de experiência, ferramentas, indústria e experiências comerciais
específicas alteram o score ou aparecem como `potential_gaps`. Um score baixo por
falta de dados continua sendo motivo para `REVIEW`, não para rejeição automática.

Anos de experiência são tratados apenas como um sinal suave:

- requisito igual ou menor gera aderência normal;
- diferença de um ou dois anos gera uma pequena redução e um gap explicável;
- diferenças maiores reduzem mais o score;
- nenhuma diferença de anos, isoladamente, produz `REJECT`;
- ausência do requisito gera um `unknown` e nenhuma penalização.

## Limitações atuais

### Source expansion research

A Etapa 13A documentou a auditoria para escalar além de Jobicy e Remotive. A
Etapa 13B implementa a base genérica, mantendo somente essas duas fontes reais
habilitadas:

- [Source research catalog](docs/SOURCE_RESEARCH.md): evidências oficiais,
  incertezas, restrições e matriz P0/P1/P2/DEFER.
- [Source architecture plan](docs/SOURCE_ARCHITECTURE_PLAN.md): riscos atuais,
  registry, capabilities, company tenants, provenance, lifecycle authority,
  budgets e roadmap proposto.

O fluxo agora é `SourceRegistry -> SourceDefinition -> JobSource + adapter ->
ingestion -> pipeline`. Cada vaga carrega `source_id`, `source_family` e
`source_instance`; discovery, falhas e contribuição funcionam para N definições
registradas, e lifecycle usa a identidade estruturada exata. Uma nova fonte
futura deve entrar por uma definição validada e testes offline, sem novos ramos
no orquestrador. Registry persistente, company registry e provenance com várias
observações continuam explicitamente fora desta etapa.

- A lista de cargos reconhecidos é intencionalmente pequena. Famílias claramente
  técnicas ou não comerciais, como engenharia, produto, jurídico, RH e pesquisa,
  podem ser rejeitadas por padrões simples no título.
- `Sales Engineer`, `Solutions Engineer` e `Technical Account Manager` possuem
  proteção explícita contra falsos positivos das famílias técnicas.
- Os adapters aceitam apenas os três formatos fictícios documentados.
- O registry operacional desta etapa contém somente Jobicy e Remotive; os
  componentes isolados de Greenhouse e Lever não fazem parte do discovery
  semanal genérico.
- O nome da empresa precisa ser informado junto com o token ou slug porque as
  respostas de listagem não o fornecem de forma confiável.
- Lever suporta apenas as bases global e EU documentadas; não há seleção
  automática de região.
- Não há retries, paginação adicional, descoberta de boards ou consultas em lote.
- O discovery multi-source usa somente uma consulta padrão por fonte, em ordem
  sequencial, sem paralelismo ou estratégia multi-query.
- A estratégia multi-query é uma camada separada, sequencial e limitada a quatro
  queries por fonte; não há retries, concorrência ou ajuste automático de termos.
- Eficiência e recomendação existem somente em memória e refletem uma execução;
  o histórico SQLite ainda não agrega métricas de queries para concluir que uma
  consulta será sempre inútil.
- Não há framework completo de migrations; existe apenas a migração idempotente
  e versionada necessária para lifecycle e histórico leve de execuções.
- Fechamento por misses é conservador, mas ainda depende da cobertura dos
  resultados retornados pelas fontes broad.
- Não há verificação individual de URL nem inferência automática baseada em 404.
- O scheduler é local: não oferece execução 24/7, notificações nem servidor
  remoto.
- O CRM é apenas terminal e estrutura tabular; não há interface gráfica nem
  interface gráfica.
- Push e pull não são executados automaticamente; conflitos simultâneos entre
  dois editores humanos ainda não possuem histórico ou resolução avançada.
- Role Family e Seniority usam somente uma lista inicial de sinais explícitos do
  título; títulos ambíguos permanecem `OTHER`/`UNKNOWN`.
- Customer Success e Partnerships são tratados como famílias relevantes pelo
  título; a presença de responsabilidade comercial ainda não é interpretada da
  descrição.
- Booleanos aceitam somente valores reais ou os textos `"true"` e `"false"`.
- Campos salariais estruturados aceitam somente números simples; textos livres
  da Remotive são preservados separadamente em `salary_text`.
- O parser de descrição reconhece somente a pequena lista de expressões acima;
  variações de linguagem fora desses padrões permanecem desconhecidas.
- Negação e contexto linguístico complexo não são analisados. Existe apenas uma
  proteção simples para expressões negativas diretas relacionadas a outbound.
- A regra de `Account Manager` ainda considera apenas o título.
- A elegibilidade reconhece somente expressões geográficas simples e explícitas.
- A deduplicação não usa identificadores de plataformas nem similaridade de texto.
- Duplicatas não são combinadas; o primeiro registro é mantido como principal.
- A ordem de entrada define qual duplicata será preservada como principal.
- Ferramentas e indústrias precisam ser fornecidas nos campos estruturados para
  participarem do score.
- A avaliação ainda não representa tamanho de contrato, complexidade do ciclo de
  vendas, senioridade estruturada ou requisitos obrigatórios versus desejáveis.
- O Match Score não lê a descrição diretamente; ele usa somente os campos
  estruturados pelo enriquecimento determinístico e não usa IA.
- `brazil_eligible` foi mantido por compatibilidade, mas a nova regra geográfica
  usa o texto de `location`; a unificação desses dois dados fica para uma etapa
  futura.

## Próxima pequena etapa sugerida

Executar primeiro um pull manual controlado e conferir o resumo antes de pensar
em histórico de sincronizações ou resolução avançada de edição concorrente.
