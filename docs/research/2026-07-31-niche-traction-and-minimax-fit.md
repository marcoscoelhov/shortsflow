# Tração de nicho e compatibilidade com MiniMax para chegar a 10 mil views

**Data da coleta:** 31/07/2026  
**Decisão estudada:** manter astronomia, mudar de nicho ou adotar um formato híbrido; e testar pt-BR versus inglês.  
**Meta operacional:** ao menos um Short atingir 10.000 views orgânicas em até 7 dias.

## Resposta executiva

**Astronomia tem público e teto muito acima de 10 mil views em português.** Na amostra de descoberta, o canal `oipedrodaher` tinha Shorts/curtas de astronomia entre 238 mil e 1,0 milhão de views, e `SolarBalls - Brasil` tinha exemplos entre 182 mil e 470 mil. Portanto, a falta de um breakout no ShortsFlow não prova falta de demanda pelo nicho.

O problema é a combinação entre **formato atual e confiabilidade visual**. Nos dados próprios, nenhum dos 79 vídeos chegou a 1.000 views; o máximo foi 882. Entre os 39 com pelo menos 100 views, a retenção mediana foi 73,12%, mas apenas 43,64% das views ponderadas foram `engagedViews`; shares e comentários ficaram em 0,045% e 0,011%. Quem permanece tende a assistir e curtir, mas a maioria não passa do contato inicial e quase ninguém compartilha.

**MiniMax `image-01` não é confiável sozinho para imagens factuais exatas.** A documentação oficial oferece texto-para-imagem, 9:16 e referência de um único sujeito, mas a referência suportada é de `character`/retrato, não de planeta, mapa, espécie, artefato ou mecanismo. No acervo local, imagens de Urano e Vênus/Mercúrio passaram por score heurístico apesar de erros visuais científicos visíveis. Já um job ficcional de biblioteca, chave e livro produziu uma sequência manualmente coerente.

**Recomendação:** não fazer um pivot definitivo ainda. Rodar um piloto pt-BR de 18 vídeos em três braços: astronomia visualmente ancorada, dilemas/mistérios ficcionais e um híbrido de ficção especulativa com ciência claramente rotulada. A aposta principal é o **híbrido**, porque preserva parte da identidade cósmica, cria conflito e decisão compartilhável e desloca o MiniMax para o que ele faz melhor: cenas imaginadas, não provas científicas. Inglês deve ser um segundo experimento, depois de validar o formato em pt-BR.

## Método e limites

Foram usadas quatro camadas de evidência:

1. **Dados first-party do canal**, lendo o snapshot mais recente de cada um dos 79 IDs em `data/shortsflow_render.db` e os artefatos locais dos jobs. As métricas seguem as definições do [YouTube Analytics](https://support.google.com/youtube/answer/12220281): `engagedViews` conta quem permaneceu apó os segundos iniciais, sem loops; duração e porcentagem média são calculadas entre essas views engajadas.
2. **Amostra de descoberta no YouTube**, coletada com `yt-dlp`/Agent Reach. Foram feitas buscas em português por astronomia, animais, física, geografia, história e ficção, e buscas dirigidas a canais encontrados. Views são contagens públicas observadas em 31/07/2026. A busca é ranqueada, não aleatória: serve para provar existência de público e teto, **não** para estimar a view mediana de um nicho. Buscas genéricas apresentaram falsos positivos, por isso o ranking não usa suas medianas como demanda.
3. **Documentação oficial** do YouTube, Google Trends e MiniMax.
4. **Spot check visual local** de três jobs. É evidência diagnóstica, não benchmark completo do modelo.

Não foi possível produzir uma comparação numérica reproduzível de Google Trends: a [API oficial do Google Trends](https://developers.google.com/search/blog/2025/07/trends-api) continuava em alpha com acesso limitado. O Trends seria útil para interesse em busca, mas ainda assim não mediria diretamente distribuição no feed de Shorts.

## O que os dados próprios dizem

| Indicador local | Resultado |
|---|---:|
| Vídeos com snapshot | 79 |
| Vídeos com 100+ views | 39 |
| Maior resultado | 882 views |
| Mediana entre os 39 ativos | 396 views |
| Retenção mediana entre os 39 | 73,12% |
| `engagedViews / views`, ponderado | 43,64% |
| Likes / views, ponderado | 7,58% |
| Shares / views, ponderado | 0,045% |
| Comentários / views, ponderado | 0,011% |
| Experimentos de retenção registrados | 0 |

O melhor vídeo, sobre o eixo inclinado de Urano, fez 882 views e 76,79% de `averageViewPercentage`; Saturno chegou a 163,45% em um caso, indicando replay, mas ficou em 692 views. A inferência mais forte é que retenção de quem ficou **não basta**: o primeiro quadro/promessa e a motivação para compartilhar continuam fracos. Os dados estão no banco local e em exemplos como [performance_metrics.json](../../data/artifacts/07482214-35fd-4176-94cf-cf9f05f0c210/performance_metrics.json).

## Astronomia: existe tração em pt-BR

Exemplos encontrados na superfície pública do YouTube:

| Canal / exemplo | Views observadas |
|---|---:|
| `oipedrodaher` — [Anéis de Saturno](https://www.youtube.com/watch?v=IkfG3sr8Q6A) | 1.015.275 |
| `oipedrodaher` — [É só uma pedrinha](https://www.youtube.com/watch?v=8Ooyo8NmL3g) | 1.011.198 |
| `oipedrodaher` — [O mundo não acaba, quem acaba é você](https://www.youtube.com/watch?v=nEhdinX0cNc) | 731.011 |
| `SolarBalls - Brasil` — [Substituindo o Sol por um buraco negro](https://www.youtube.com/watch?v=6YucFFzH9jg) | 470.505 |
| `SolarBalls - Brasil` — [Planetas podem compartilhar órbita?](https://www.youtube.com/watch?v=r93B9RP6Nwk) | 339.315 |
| `SolarBalls - Brasil` — [O que acontece quando planetas se chocam?](https://www.youtube.com/watch?v=u1HFqW9r568) | 310.069 |

Esses casos não mostram a probabilidade de um canal novo chegar lá, mas refutam a hipótese de que astronomia em português teria teto abaixo de 10 mil. Também revelam um padrão: os exemplos fortes não são slideshows fotorealistas genéricos; usam animação, personagens, escala, colisão, perigo ou uma frase com consequência humana.

## O que MiniMax consegue sustentar

A [documentação oficial de geração de imagens](https://platform.minimax.io/docs/guides/image-generation) confirma texto-para-imagem e imagem-para-imagem. A [referência da API](https://platform.minimax.io/docs/api-reference/image-generation-i2i) permite `9:16`, sementes reproduzíveis e até nove saídas, mas a referência de sujeito aceita atualmente apenas `character` e recomenda retrato frontal. Logo:

- **Boa adequação:** ambiente, atmosfera, objeto cotidiano, personagem estilizado, ameaça imaginada, dilema visual e continuidade aproximada de personagem.
- **Adequação condicional:** reconstrução histórica, animal e paisagem, desde que a imagem seja rotulada como ilustração e revisada.
- **Baixa confiabilidade sem grounding:** planeta identificável, comparação astronômica, mapa/fronteira, anatomia de espécie, artefato arqueológico e mecanismo físico exato.

Evidência local: o job de Urano `074822...` recebeu `semantic_match=0.95` em todas as cenas, mas `verification_mode=prompt_heuristic` e `vision verifier unavailable`; inspeção humana viu dois planetas com anéis e a inclinação não ficou legível. No job Vênus/Mercúrio `e2166...`, a primeira imagem parecia Júpiter. Portanto, [asset_visual_gate.json](../../data/artifacts/07482214-35fd-4176-94cf-cf9f05f0c210/asset_visual_gate.json) prova apenas que o prompt e metadados passaram pela heurística, não que pixels estavam corretos. Em contraste, o job ficcional `f45921...` representou biblioteca, areia, chave e livro de forma coerente no spot check, embora sua [revisão automática](../../data/artifacts/f45921f7-b66e-4cad-8a2c-67e669403db0/auto_visual_review.json) corretamente ainda marque ausência de evidência visual real.

## Ranking para este pipeline

Pontuação inferencial de 0–100. Pesos: teto/demonstração pública 25%, amplitude 15%, compatibilidade MiniMax 25%, risco de erro factual 15%, profundidade editorial 10% e segurança de política/monetização 10%. `Risco factual` alto significa menor risco.

| Nicho/formato | Teto | Amplitude | MiniMax | Risco factual | Catálogo | Política | Total |
|---|---:|---:|---:|---:|---:|---:|---:|
| Dilemas/mistério ficcional visual | 5,0 | 5,0 | 5,0 | 5,0* | 4,0 | 3,0 | **94** |
| Híbrido: ficção especulativa + ciência rotulada | 4,5 | 5,0 | 4,5 | 3,5 | 5,0 | 4,0 | **88** |
| Astronomia animada/ancorada | 5,0 | 4,0 | 3,0 | 3,0 | 5,0 | 4,5 | **80** |
| Animais e comportamento | 4,0 | 5,0 | 2,5 | 2,5 | 5,0 | 4,0 | **73** |
| Ciência/física visual | 4,0 | 4,5 | 2,5 | 2,5 | 5,0 | 3,5 | **71** |
| Geografia/fenômenos da Terra | 3,5 | 4,5 | 2,5 | 2,5 | 5,0 | 3,5 | **68** |
| História/arqueologia | 3,5 | 4,0 | 3,0 | 2,0 | 5,0 | 3,5 | **68** |

\* Ficção só recebe 5 quando é explicitamente apresentada como ficção. Fingir que uma cena inventada é fato real derruba essa nota.

### Leitura por nicho

- **Animais:** amplo e emocional, mas MiniMax pode inventar anatomia ou comportamento. Material documental real/licenciado seria mais forte que geração para a prova central.
- **Física visual:** ótimo formato narrativo (`previsão → demonstração → explicação`), porém uma imagem plausível pode mostrar o mecanismo errado. Simulação programática ou filmagem real deve ser a prova.
- **Geografia/Terra:** fenômenos têm apelo, mas mapas e desastres exigem precisão, data e fonte; MiniMax funciona melhor como atmosfera do que cartografia.
- **História/arqueologia:** reconstruções são visualmente fortes, mas anacronismos e pseudo-história elevam o custo de revisão.
- **Ficção visual:** maximiza legibilidade, surpresa e comentário (`qual você escolheria?`) sem exigir que cada pixel prove um fato. O risco migra para repetição, violência e conteúdo genérico.

O YouTube exige conteúdo original/autêntico e pode rejeitar conteúdo mass-produced, repetitivo ou feito por template com pouca variação ([política de monetização](https://support.google.com/youtube/answer/1311392)). Violência, choque e atos perigosos podem reduzir monetização ([advertiser-friendly guidelines](https://support.google.com/youtube/answer/6162278)). Dilemas devem privilegiar tensão, escolha e consequência sem gore, crianças em risco, instrução perigosa ou tragédia real.

## Brasil/pt-BR versus global/inglês

Idioma é uma decisão separada do nicho.

| Opção | Vantagem | Custo/risco | Decisão agora |
|---|---|---|---|
| pt-BR | Tração astronômica já demonstrada; roteiro e voz podem soar naturais; feedback local mais comparável | Mercado potencial menor | **Começar aqui** |
| inglês | Teto global maior em termos absolutos; visual ficcional viaja bem | Competição maior; voz, prosódia, idioma e timing precisam parecer nativos | Testar só após um formato vencedor |
| um Short com áudio multilíngue | Mantém analytics e vídeo reunidos | Recurso ainda não está disponível para todos; dublagem deve ser revisada | Usar se a conta tiver acesso |
| canais separados | Experiência e comunicação focadas por idioma | Divide volume e operação | Preferível para um piloto inglês persistente |

O YouTube confirma que faixas de áudio multilíngue funcionam também em Shorts e relata que criadores com o recurso obtiveram mais de 25% do watch time em idiomas não primários; ao mesmo tempo, o acesso ainda é gradual ([YouTube Help](https://support.google.com/youtube/answer/13338784)). A própria plataforma apresenta canais separados como opção para comunicação localizada e menos confusa ([estratégia global](https://support.google.com/youtube/answer/6070467)). Isso sustenta testar internacionalização, mas não prova que inglês vencerá pt-BR.

Para inglês, exigir antes de publicar: revisão humana de naturalidade, voz sem pronúncia robótica, legendas que não sejam tradução literal e adaptação cultural do hook. Não misturar uploads alternados em dois idiomas no feed atual.

## Piloto recomendado: 18 Shorts em pt-BR

Manter constantes: alvo de 40 segundos, voz, ritmo, acabamento, horário, quantidade de cenas e intensidade de CTA. A duração final aceita fica entre 30 e 50 segundos: ela é uma covariável registrada, não motivo para descartar trabalho bom dentro da faixa. Publicar em ordem intercalada para reduzir efeito de dia/horário.

### Braço A — astronomia ancorada (6)

- Usar imagem oficial/licenciada ou visual programático para o objeto factual central.
- MiniMax apenas para atmosfera, escala emocional ou personagem estilizado.
- Exemplos: colisão evitada por pouco; mensagem da Voyager; um minuto final em uma lua alienígena.
- Não repetir Vênus quente, Marte vermelho, anéis de Saturno ou clima de Netuno neste lote.

### Braço B — dilema/mistério ficcional (6)

- Duas escolhas imediatamente visíveis no primeiro quadro.
- Consequência reversa no payoff: a escolha óbvia falha por uma pista mostrada antes.
- Sem alegar `história real`; inserir `cenário fictício` na descrição e, quando necessário, no vídeo.
- CTA orgânica: `qual você escolheria e por quê?`

### Braço C — híbrido especulativo (6)

- Cenário explicitamente hipotético, regra científica verdadeira e escolha humana.
- Exemplo: `você tem 30 segundos numa base lunar: fecha a comporta ou salva o gerador?`
- O fato usado como regra deve vir de NASA, ESA, NOAA, museu, universidade ou paper; o enredo permanece ficcional.
- Evitar imagens que precisem identificar com precisão dois planetas ou mecanismos complexos.

### Gate visual antes de publicar

Nenhum asset pode ser aprovado somente por `prompt_heuristic`. Por decisão operacional posterior registrada no [ADR 0002](../adr/0002-reconcile-2026-07-31-publication-vision-and-llm-policy.md), os 18 assignments deste piloto dispensam revisão humana visual: hook, prova e payoff exigem o Qwen local exato (`local_openai` + `qwen3-vl-2b-instruct-q4-k-m`), sem fallback, aprovando todas as cenas críticas. Critérios: leitura em menos de 1 segundo, objetos corretos, continuidade, ausência de texto falso, anatomia plausível e nenhuma contradição com o roteiro. Para braços factuais, uma imagem bonita mas cientificamente errada reprova. A autoaprovação visual não autoriza agendamento ou publicação.

### Medição e decisão

Coletar em 24h, 72h e 7 dias:

- `Stayed to watch`/viewed-vs-swiped (métrica primária do hook);
- `averageViewPercentage` e curva de retenção;
- shares, comentários e inscritos por 1.000 views;
- views orgânicas e origem `Shorts feed`;
- taxa de aprovação visual e regenerações por cena.

Os thresholds seguintes são **hipóteses operacionais**, não benchmarks oficiais: promover um braço se a mediana de `Stayed to watch` superar 55%, `averageViewPercentage` superar 85%, shares chegarem a 3/1.000 e ao menos 2 de 6 vídeos passarem de 2.000 views ou um chegar a 10.000 em 7 dias. Encerrar um braço se nenhum vídeo passar de 1.000 e ele perder dos demais em hook e compartilhamento.

Depois de um vencedor pt-BR, adaptar seis conceitos vencedores para inglês em canal separado ou áudio multilíngue, comparando **taxas**, não views brutas. Inglês só vira idioma principal se vencer em `Stayed to watch`, retenção e shares por exposição e não elevar reprovação de voz/texto.

## Decisão proposta

1. **Não abandonar astronomia por falta de público:** a hipótese foi refutada pelos exemplos pt-BR.
2. **Parar de usar MiniMax fotorealista como prova científica:** ele continua como gerador de atmosfera e ficção; fatos exatos precisam de visual ancorado e verificação pixel-level.
3. **Testar o híbrido como candidato principal e dilemas ficcionais como challenger.** Eles resolvem melhor o desalinhamento atual entre gerador, hook e compartilhamento.
4. **Validar formato antes de idioma.** Primeiro pt-BR; inglês entra como experimento controlado, não como aposta presumida.

O YouTube recomenda capturar atenção nos primeiros segundos e analisar o desempenho para descobrir o que ressoa ([guia oficial de Shorts](https://blog.youtube/creator-and-artist-stories/your-guide-to-getting-started-with-youtube-shorts/)). O próximo passo, portanto, não é escolher um nicho apenas por intuição: é executar este piloto com feedback loop persistente. A implementação de 2026-07-31 adicionou `retention_experiments` e `retention_experiment_assignments`; o primeiro checkpoint cria três canários intercalados, sem publicar.

## Fontes principais

- YouTube Help, desempenho e definições de Shorts: https://support.google.com/youtube/answer/12220281
- YouTube Help, monetização e conteúdo inautêntico: https://support.google.com/youtube/answer/1311392
- YouTube Help, advertiser-friendly: https://support.google.com/youtube/answer/6162278
- YouTube Help, áudio multilíngue: https://support.google.com/youtube/answer/13338784
- YouTube Help, estratégia global: https://support.google.com/youtube/answer/6070467
- MiniMax, guia de image generation: https://platform.minimax.io/docs/guides/image-generation
- MiniMax, referência image-to-image: https://platform.minimax.io/docs/api-reference/image-generation-i2i
- Google Search Central, Trends API alpha: https://developers.google.com/search/blog/2025/07/trends-api
- Dados locais: `data/shortsflow_render.db` e artefatos citados acima.
