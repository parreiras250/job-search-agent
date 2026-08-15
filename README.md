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
Greenhouse e Lever podem ser consultados manualmente por seus endpoints públicos.
Ainda **não** há descoberta automática de empresas, scraping, inteligência
artificial, conexão com Google Sheets ou automação semanal.

## Estrutura

```text
daniel-job-agent/
├── data/                     # Dados locais gerados durante o desenvolvimento
├── prompts/                  # Prompts que poderão ser usados em uma etapa futura
├── src/
│   └── daniel_job_agent/
│       ├── __init__.py       # Define o pacote Python
│       ├── demo.py           # Demonstração executável no terminal
│       ├── demo_data.py      # Registros brutos e vagas fictícias
│       ├── enrichment.py     # Extração determinística de sinais explícitos
│       ├── greenhouse_demo.py # Consulta manual de um board público
│       ├── ingestion.py      # Adapters e ingestão local em lote
│       ├── lever_demo.py     # Consulta manual de postings públicos Lever
│       ├── models.py         # Vaga e acompanhamento manual do CRM
│       ├── pipeline.py       # Processamento em lote e ranking
│       ├── profiles.py       # Perfil profissional padrão do Daniel
│       ├── reporting.py      # Contagens compartilhadas dos demos reais
│       ├── rules.py          # Regras locais de classificação e decisão
│       └── sources.py        # Leitura HTTP de fontes externas
├── tests/
│   ├── test_candidate_profile.py
│   ├── test_enrichment.py
│   ├── test_greenhouse_source.py
│   ├── test_ingestion.py
│   ├── test_job_opportunity.py
│   ├── test_lever_source.py
│   ├── test_pipeline.py
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

- A lista de cargos reconhecidos é intencionalmente pequena. Famílias claramente
  técnicas ou não comerciais, como engenharia, produto, jurídico, RH e pesquisa,
  podem ser rejeitadas por padrões simples no título.
- `Sales Engineer`, `Solutions Engineer` e `Technical Account Manager` possuem
  proteção explícita contra falsos positivos das famílias técnicas.
- Os adapters aceitam apenas os três formatos fictícios documentados.
- As fontes reais suportadas são Greenhouse e Lever, sempre com um board/site
  informado explicitamente.
- O nome da empresa precisa ser informado junto com o token ou slug porque as
  respostas de listagem não o fornecem de forma confiável.
- Lever suporta apenas as bases global e EU documentadas; não há seleção
  automática de região.
- Não há retries, paginação adicional, descoberta de boards ou consultas em lote.
- Booleanos aceitam somente valores reais ou os textos `"true"` e `"false"`.
- Salários aceitam somente números simples; moedas formatadas como `"USD 80k"`
  geram warning e permanecem como `None`.
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

Executar uma única validação manual em um site Lever escolhido pelo usuário e,
se o payload revelar variações legítimas, representá-las primeiro como fixtures
locais antes de ampliar qualquer regra.
