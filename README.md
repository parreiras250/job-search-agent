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
│       ├── demo.py           # Demonstração executável no terminal
│       ├── demo_data.py      # Registros brutos e vagas fictícias
│       ├── ingestion.py      # Adapters e ingestão local em lote
│       ├── models.py         # Vaga e acompanhamento manual do CRM
│       ├── pipeline.py       # Processamento em lote e ranking
│       ├── profiles.py       # Perfil profissional padrão do Daniel
│       └── rules.py          # Regras locais de classificação e decisão
├── tests/
│   ├── test_candidate_profile.py
│   ├── test_ingestion.py
│   ├── test_job_opportunity.py
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

- A lista de cargos reconhecidos é intencionalmente pequena.
- Os adapters aceitam apenas os três formatos fictícios documentados.
- Booleanos aceitam somente valores reais ou os textos `"true"` e `"false"`.
- Salários aceitam somente números simples; moedas formatadas como `"USD 80k"`
  geram warning e permanecem como `None`.
- Textos livres de descrição, requisitos e responsabilidades são armazenados,
  mas ainda não são interpretados automaticamente.
- A regra de `Account Manager` ainda considera apenas o título.
- A elegibilidade reconhece somente expressões geográficas simples e explícitas.
- A deduplicação não usa identificadores de plataformas nem similaridade de texto.
- Duplicatas não são combinadas; o primeiro registro é mantido como principal.
- A ordem de entrada define qual duplicata será preservada como principal.
- Ferramentas e indústrias precisam ser fornecidas nos campos estruturados para
  participarem do score.
- A avaliação ainda não representa tamanho de contrato, complexidade do ciclo de
  vendas, senioridade estruturada ou requisitos obrigatórios versus desejáveis.
- O Match Score não interpreta descrições e não usa IA.
- `brazil_eligible` foi mantido por compatibilidade, mas a nova regra geográfica
  usa o texto de `location`; a unificação desses dois dados fica para uma etapa
  futura.

## Próxima pequena etapa sugerida

Adicionar suporte local a arquivos JSON contendo os mesmos registros brutos,
reutilizando os adapters e mantendo a leitura de arquivo separada da conversão.
