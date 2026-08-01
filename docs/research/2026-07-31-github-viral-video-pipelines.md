# Pipelines públicos de vídeo curto: o que pode ajudar o ShortsFlow a chegar ao Breakout 10k

Pesquisa concluída em 2026-07-31. Foram inspecionados README, código e licença em commits fixos de repositórios públicos encontrados pelo GitHub CLI. O objetivo não foi medir popularidade do repositório, mas localizar mecanismos concretos de seleção de pauta, hook, experimento e aprendizado pós-publicação.

## Resumo executivo

Nenhum repositório inspecionado demonstra, com dados públicos verificáveis, que seu código produz vídeos virais. Estrelas no GitHub medem interesse de desenvolvedores, não views no YouTube. O ShortsFlow já é mais completo em qualidade, rastreabilidade, publicação e coleta oficial de métricas do que a maioria deles.

O melhor achado não é um renderer novo. É fechar o ciclo que o ShortsFlow já começou:

1. rotular cada Job de Vídeo com família de pauta, fórmula de hook, contrato do primeiro frame, idioma e braço experimental;
2. comparar braços somente em janelas equivalentes (72 h e 7 dias), com amostra mínima;
3. usar performance real para influenciar a próxima fila de pautas;
4. premiar crescimento recente e lift relativo, não apenas views acumuladas;
5. impedir que um vencedor inicial faça o canal convergir para uma fórmula repetitiva.

O repositório mais diretamente aproveitável como referência é **poyrazemun/youtube-shorts-generator**. **bigkweks/tiktok-roblox** contém o modelo de aprendizado mais interessante, mas não tem licença declarada e seu domínio é Roblox/carrosséis, portanto só deve inspirar um desenho próprio. **Socheli/socheli** tem contratos úteis de variantes, porém é AGPL e sua implementação chamada de “A/B” não executa, por si só, um A/B causal verdadeiro.

## Situação atual do ShortsFlow

O ShortsFlow já possui:

- pipeline pauta → pesquisa → roteiro → cenas → imagens/TTS → render → upload;
- gates de hook, retenção, intensidade viral, repetição, factualidade e qualidade visual;
- sincronização oficial do YouTube Analytics com views, retenção, likes, comentários, shares, inscritos e engaged views (`app/youtube_api.py`, `app/performance_ops.py`);
- relatório de crescimento e diagnóstico de gaps (`app/growth_metrics.py`);
- histórico de pauta/hook e rejeição por similaridade (`app/pipelines/topic_pipeline.py`);
- um `channel_learning_brief`, já injetado no roteiro, que separa exemplos fortes/fracos;
- experimento especializado de sobrevivência, mas não um ledger editorial genérico para comparar nicho, hook, primeiro frame, idioma e estilo visual.

A lacuna é de **desenho experimental e atribuição**, não de geração de vídeo. O aprendizado atual envia exemplos inteiros ao prompt, mas ainda não transforma cada escolha criativa em uma variável comparável com amostra, janela, confiança e regra de promoção.

## Shortlist inspecionada

| Repositório | Semelhança e mecanismo real | O que vale adaptar | Limite / risco | Licença |
|---|---|---|---|---|
| [poyrazemun/youtube-shorts-generator](https://github.com/poyrazemun/youtube-shorts-generator/tree/8220c63791289c05ece5970f6f0ac52909313657) | Pipeline completo de fatos históricos: fila de pautas, pesquisa, roteiro, imagens, TTS, render, upload e analytics. Agrupa resultados por keyword e `hook_type`, exige ≥2 vídeos e injeta os vencedores na próxima geração ([analytics](https://github.com/poyrazemun/youtube-shorts-generator/blob/8220c63791289c05ece5970f6f0ac52909313657/pipeline/analytics.py#L238-L293), [feedback na fila](https://github.com/poyrazemun/youtube-shorts-generator/blob/8220c63791289c05ece5970f6f0ac52909313657/pipeline/topic_discovery.py#L97-L132)). | Taxonomia explícita de hooks, fila auditável, exclusão de histórias já publicadas e hints com origem persistida. A estrutura Hook → Contexto → Rehook → Twist → Fecho também é clara ([contrato](https://github.com/poyrazemun/youtube-shorts-generator/blob/8220c63791289c05ece5970f6f0ac52909313657/pipeline/script_generator.py#L43-L77)). | Média de views com apenas 2 amostras é frágil; score de “virality” produzido pelo próprio LLM é hipótese, não evidência. Não copiar os limiares. | MIT |
| [bigkweks/tiktok-roblox](https://github.com/bigkweks/tiktok-roblox/tree/9339acb39f25107041212ac63b04ed736e92c4b5) | Descobre temas por velocidade de crescimento, engajamento, novidade e frescor, privilegiando momentum sobre tamanho ([scorer](https://github.com/bigkweks/tiktok-roblox/blob/9339acb39f25107041212ac63b04ed736e92c4b5/src/discovery/viral_scorer.py#L1-L91)). Mantém um “genoma” de componentes e calcula confiança, efetividade, novidade e penalidade de repetição ([ranking](https://github.com/bigkweks/tiktok-roblox/blob/9339acb39f25107041212ac63b04ed736e92c4b5/src/learning/ranking.py#L1-L56)). | View velocity/lift relativo; Wilson lower bound; bias pequeno e limitado; penalidade quando uma fórmula passa de 40% da janela recente. | Repositório novo, 0 stars na inspeção, domínio diferente e sem licença detectável. Tratar somente como referência conceitual; reimplementar do zero. | Não declarada |
| [Socheli/socheli](https://github.com/Socheli/socheli/tree/8cd7cc136bce43fbc95e30dc1bb4c5adfe4067ae) | Pipeline faceless extenso. Seleciona um board de conceitos combinando trends, memória de wins/flops e DNA do canal ([selection](https://github.com/Socheli/socheli/blob/8cd7cc136bce43fbc95e30dc1bb4c5adfe4067ae/packages/engine/src/selection.ts#L8-L38)). Persiste variante de hook + primeiro frame + publicação + resultado ([abtest](https://github.com/Socheli/socheli/blob/8cd7cc136bce43fbc95e30dc1bb4c5adfe4067ae/packages/engine/src/abtest.ts#L9-L72)). | Separar controle e variantes, guardar a variante que realmente foi publicada e exibir todos os candidatos/racionais antes da escolha. | A função `decideWinner` credita o score ao único braço publicado; isso é atribuição, não comparação causal entre braços ([código](https://github.com/Socheli/socheli/blob/8cd7cc136bce43fbc95e30dc1bb4c5adfe4067ae/packages/engine/src/abtest.ts#L232-L299)). Não chamar isso de A/B sem coortes comparáveis. | AGPL-3.0; adaptar ideias, não transplantar código sem revisar obrigações |
| [harry0703/MoneyPrinterTurbo](https://github.com/harry0703/MoneyPrinterTurbo/tree/e5bb283d2f3cec00ac9b32c306b0387fbedfb9cb) | Gerador maduro e muito usado. Gera termos visuais na ordem narrativa e pode casar materiais com a sequência do roteiro ([task](https://github.com/harry0703/MoneyPrinterTurbo/blob/e5bb283d2f3cec00ac9b32c306b0387fbedfb9cb/app/services/task.py#L289-L328)); ao randomizar, prioriza fontes de vídeo únicas antes de repetir ([video](https://github.com/harry0703/MoneyPrinterTurbo/blob/e5bb283d2f3cec00ac9b32c306b0387fbedfb9cb/app/services/video.py#L133-L156)). | Duas métricas de saúde visual: alinhamento temporal cena↔narração e taxa de reutilização de fonte. Útil como benchmark do MiniMax e dos fallbacks. | Não há loop de analytics/experimentos que sustente alegação de viralidade. É referência de montagem e diversidade, não de descoberta editorial. | MIT |
| [RayVentura/ShortGPT](https://github.com/RayVentura/ShortGPT/tree/3df4e0f7a422bf7386565d498bf4521a2544c614) | Framework modular antigo para Shorts/TikTok, com captions temporizadas e assets por trecho ([content engine](https://github.com/RayVentura/ShortGPT/blob/3df4e0f7a422bf7386565d498bf4521a2544c614/shortGPT/engine/content_short_engine.py#L61-L87), [captions](https://github.com/RayVentura/ShortGPT/blob/3df4e0f7a422bf7386565d498bf4521a2544c614/shortGPT/editing_utils/captions.py#L38-L105)). | Benchmark de portabilidade: conteúdo estruturado independente de voz, idioma, assets e edição. | O ShortsFlow já possui equivalentes mais fortes. Não oferece seleção por desempenho nem experimento; baixo impacto direto em 10k. | MIT |
| [SaarD00/AI-Youtube-Shorts-Generator](https://github.com/SaarD00/AI-Youtube-Shorts-Generator/tree/c1b0c84fdd457f74183e4253719597edb580d7ca) | Pipeline faceless simples com duas buscas visuais por frase e troca de imagem no meio da cena ([prompt](https://github.com/SaarD00/AI-Youtube-Shorts-Generator/blob/c1b0c84fdd457f74183e4253719597edb580d7ca/modules/brain.py#L27-L59)). | Um braço experimental barato: uma versus duas mudanças visuais por beat, mantendo todo o resto fixo. | O método chamado `get_trending_topic` apenas pede ao Gemini para inventar um tema “viral”; o próprio comentário admite que não consulta Trends ou rede social ([código](https://github.com/SaarD00/AI-Youtube-Shorts-Generator/blob/c1b0c84fdd457f74183e4253719597edb580d7ca/modules/brain.py#L15-L24)). Não usar como scout. | MIT |
| [darkzOGx/youtube-automation-agent](https://github.com/darkzOGx/youtube-automation-agent/tree/f5b34966409916a2f73f5d557ab62991ba5e10d5) | Tenta consultar Analytics, tráfego, dispositivo e demografia em paralelo ([analytics](https://github.com/darkzOGx/youtube-automation-agent/blob/f5b34966409916a2f73f5d557ab62991ba5e10d5/agents/analytics-optimization-agent.js#L115-L143)). | Somente a decomposição das perguntas: distribuição, retenção, audiência e tráfego devem ser diagnósticos separados. | Anti-padrão crítico: qualquer erro de Analytics retorna números aleatórios e eles seguem pelo pipeline como se fossem dados ([fallback](https://github.com/darkzOGx/youtube-automation-agent/blob/f5b34966409916a2f73f5d557ab62991ba5e10d5/agents/analytics-optimization-agent.js#L623-L639)). Também mistura métricas que podem não ser válidas juntas em uma query. Não reutilizar a implementação. | MIT |

## Matriz de capacidades

Legenda: **sim** = mecanismo implementado no código; **parcial** = existe, mas é heurístico, não está ligado ao loop inteiro ou não prova causalidade; **não** = não encontrado na inspeção.

| Capacidade | ShortsFlow | Poyraz | bigkweks | Socheli | MoneyPrinter | ShortGPT | SaarD00 | darkz |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Geração completa do zero | sim | sim | parcial | sim | sim | sim | sim | sim |
| Scout com sinal externo real | parcial | parcial | sim, no domínio Roblox | parcial | não | não | **não** | parcial |
| Tipos de hook persistidos | parcial | sim | sim | sim | não | não | não | parcial |
| Analytics pós-publicação | sim | sim | sim/manual | sim | não | não | não | sim, mas fallback inseguro |
| Feedback para próxima pauta | parcial | sim | sim | sim | não | não | não | parcial |
| Braços experimentais rastreáveis | especializado | não | parcial | parcial | não | não | não | configuração sem prova |
| Controle estatístico/anti-overfit | não genérico | mínimo (n≥2) | sim | não | não | não | não | não |
| Penalidade explícita de convergência | similaridade de pauta | palavras já usadas | sim | memória/evita | diversidade de asset | não | não | tópicos recentes |
| Verificação visual automatizada | sim | parcial | parcial | sim | técnica | não | não | parcial |

## Cinco aprendizados priorizados para o Marco de Breakout 10k

### 1. Criar um ledger editorial genérico, antes de trocar de nicho

**Maior impacto.** Cada publicação deve carregar dimensões discretas e estáveis: `niche_hypothesis`, `topic_family`, `hook_archetype`, `first_frame_contract`, `visual_grammar`, `language`, `duration_band`, `experiment_id`, `arm_id` e `published_at`. Métricas sem esses rótulos só permitem olhar vídeos individualmente.

Adapte de Poyraz a ligação `hook_type → resultado → próxima fila`, mas use as métricas que o ShortsFlow já coleta e janelas equivalentes. O `channel_learning_brief` atual deve consumir agregados por componente, não apenas listar exemplos fortes/fracos completos.

### 2. Selecionar pauta por slate competitivo, não por uma única resposta do LLM

Gere 10–20 candidatas; pontue cada uma por sinal externo, novidade no canal, clareza do objeto no primeiro segundo, surpresa verificável e viabilidade visual no MiniMax; guarde o board inteiro e escolha a vencedora. É a combinação útil do board do Socheli com a fila auditável do Poyraz.

Para comparar astronomia com um nicho novo, não mude o canal com base em opinião. Rode uma **prova de produção**: prompts representativos por nicho, imagens MiniMax avaliadas pelos gates existentes e pequenos lotes publicados sob braços identificados.

### 3. Medir momentum e lift relativo em 24 h, 72 h e 7 dias

Views acumuladas favorecem vídeos antigos. Adapte a ideia de velocity do bigkweks para YouTube: `views_delta/janela`, engaged-view rate, retenção, share rate e desempenho relativo à mediana contemporânea do canal. Não use os pesos do repositório; calibre-os com o próprio histórico.

Uma promoção de fórmula deve exigir janela madura e amostra mínima. Um vídeo excepcional pode abrir uma investigação, mas não deve sozinho reprogramar a geração.

### 4. Explorar vencedores sem deixar o canal virar cópia de si mesmo

Use confiança por amostra (por exemplo, limite inferior de Wilson para “sucesso”) e um bias pequeno, limitado. Se uma fórmula exceder uma parcela da janela recente, aplique penalidade de dominância. Essa é a contribuição mais valiosa do ranking do bigkweks.

O objetivo não é alternar aleatoriamente; é exploração controlada: maioria em braços promissores, uma fração em desafiantes novos e bloqueio de repetição semântica já existente.

### 5. Tratar imagem como restrição do nicho e variável experimental

Antes de adotar um nicho global em inglês, meça se o MiniMax consegue produzir: sujeito reconhecível no primeiro frame, continuidade de personagem/objeto, diversidade entre beats, baixa taxa de regeneração e alta aderência cena↔narração. MoneyPrinter sugere métricas simples de alinhamento e reutilização; SaarD00 oferece uma hipótese testável de cadência visual (uma versus duas trocas por beat).

Não confundir mais cortes com mais retenção. Publique braços equivalentes e deixe a retenção real decidir.

## O que adaptar e o que não adaptar

### Adaptar

- contrato de `hook_archetype` com vocabulário limitado e persistente;
- board de candidatas com scores e razões auditáveis;
- fila que exclui eventos já cobertos, não só keywords idênticas;
- snapshots 24 h / 72 h / 7 d associados ao braço experimental;
- agregação por componente com amostra, confiança e lift relativo;
- bias limitado + penalidade de dominância;
- auditoria MiniMax por nicho antes da migração editorial;
- falha fechada para métricas: indisponível é `unknown`, nunca zero ou simulação.

### Não adaptar

- “virality score” autorreferente produzido pelo mesmo LLM que inventou a pauta;
- declarar trend sem fonte externa, como faz o método do SaarD00;
- promover fórmula por 1–2 vídeos ou por média bruta sem maturação;
- chamar uma única variante publicada de teste A/B;
- copiar o ranking do bigkweks, que não tem licença e usa sinais específicos de Roblox;
- incorporar código AGPL do Socheli sem decisão consciente sobre compatibilidade;
- usar dados simulados em produção quando Analytics falha;
- trocar para inglês e nicho global ao mesmo tempo: isso mistura duas variáveis e destrói a atribuição.

## Sequência recomendada

1. **Instrumentar**, sem alterar o conteúdo: ledger + rótulos + snapshots por janela.
2. **Backfill** dos vídeos atuais com família de pauta e tipo de hook onde houver evidência suficiente.
3. **Prova de nicho/Minimax** offline: astronomia e 2–3 nichos candidatos, com score visual cego e custo/taxa de regeneração.
4. **Primeiro lote causal**: uma variável por vez, braços balanceados e mesma língua.
5. **Somente depois**, testar pt-BR versus inglês dentro do nicho vencedor.
6. Promover/arquivar fórmulas com regra explícita; gerar a próxima fila usando apenas aprendizados maduros.

Esse caminho usa o que há de melhor nos repositórios sem trocar a arquitetura robusta do ShortsFlow por pipelines mais populares, porém editorialmente menos verificáveis.
