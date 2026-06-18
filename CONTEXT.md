# YTS Render Context

Este contexto define a linguagem de dominio usada para gerar, revisar e preparar Shorts no projeto.

## Language

**Job de Video**:
Uma unidade de trabalho que cobre a criacao de um Short desde o pedido editorial ate um resultado revisavel.
_Avoid_: video, render, tarefa

**Origem do Job**:
A classificacao visivel de qual caminho editorial criou um **Job de Video**.
_Avoid_: tag solta, status, provider, origem tecnica

**Origem Desconhecida do Job**:
A leitura usada quando nao ha evidencia confiavel para classificar a **Origem do Job** de um **Job de Video** historico.
_Avoid_: chute, inferencia fraca, erro de origem

**Via de Criacao do Job**:
A classificacao visivel de qual caminho operacional criou um **Job de Video**.
_Avoid_: origem editorial, provider, status, etapa do pipeline

**Arquivo de Video Final**:
O arquivo de midia produzido por um **Job de Video** para revisao humana.
_Avoid_: video, output, render

**Acabamento Editorial Premium**:
A camada de composicao final do **Arquivo de Video Final** que adiciona ritmo visual, movimento, transicoes, tipografia, enfase de legenda e identidade visual sem alterar roteiro, narracao ou fatos.
_Avoid_: trocar roteiro, gerar nova pauta, mudar fatos, estetica generica

**Prova Comparativa de Acabamento**:
A avaliacao humana lado a lado de versoes do mesmo **Job de Video** para decidir se uma abordagem de **Acabamento Editorial Premium** deve virar padrao.
_Avoid_: opiniao isolada, comparar jobs diferentes, aprovar sem gates, decisao por ferramenta

**Decisao Comparativa de Acabamento**:
A escolha humana feita durante uma **Prova Comparativa de Acabamento** sobre qual versao do mesmo **Job de Video** tem melhor acabamento, sem aprovar publicacao por si so.
_Avoid_: aprovacao de publicacao, revisao humana final, score automatico, troca invisivel de arquivo

**Versao Premium Paralela**:
Um **Arquivo de Video Final** alternativo criado para **Prova Comparativa de Acabamento**, sem substituir o arquivo usado pelo fluxo normal de revisao e publicacao.
_Avoid_: substituir final.mp4 durante prova, publicacao acidental, versao invisivel, artefato solto

**Gate de Acabamento Premium**:
A validacao automatica minima de uma **Versao Premium Paralela** antes de ela participar de uma **Prova Comparativa de Acabamento**.
_Avoid_: comparar arquivo quebrado, julgamento estetico sem sanidade tecnica, aprovar efeito que viola narrativa

**Acao de Prova Premium**:
O comando humano no **Hub de Revisao** que gera uma **Versao Premium Paralela** para avaliar **Acabamento Editorial Premium** sem mudar o fluxo normal do **Job de Video**.
_Avoid_: etapa obrigatoria do pipeline, publicacao automatica, aprovacao invisivel, experimento global

**Ajuste de Timing Visual**:
A mudanca de ritmo de elementos visuais dentro de cenas ja aprovadas, sem reordenar cenas, cortar narracao, alterar legenda ou antecipar payoff.
_Avoid_: mudar timing editorial, reescrever roteiro, cortar audio, revelar payoff cedo

**Pacote de Acabamento Premium Inicial**:
O conjunto inicial de recursos de **Acabamento Editorial Premium** para comparar captions animadas, transicoes semanticas, enquadramento estavel de cena, overlays editoriais pontuais e identidade visual consistente.
_Avoid_: efeitos livres, template barato, excesso de zoom, variacao visual caotica

**Plano de Acabamento Editorial**:
O contrato de composicao final que transforma o conteudo aprovado de um **Job de Video** em decisoes de captions, transicoes, enquadramento, overlays e identidade visual para o **Arquivo de Video Final**.
_Avoid_: plano de cenas, roteiro novo, configuracao tecnica do renderizador, efeito solto

**Plano de Acabamento Deterministico**:
Um **Plano de Acabamento Editorial** criado por regras previsiveis a partir dos papeis narrativos, intencoes visuais, duracao de cenas, legendas e contrato visual aprovados.
_Avoid_: escolha livre por LLM, efeitos imprevisiveis, variacao sem baseline, decisao estetica opaca

**Pauta Viral Estruturada**:
O contrato editorial de entrada usado para transformar um tema ou titulo em roteiro de Short, organizado em Titulo, Hook, Loop, Beats, Payoff, Fechamento e Hashtags.
_Avoid_: prompt solto, instrucoes livres, formato opcional

**Legenda de Uma Linha**:
A apresentacao de legenda em que cada bloco visivel no **Arquivo de Video Final** ocupa uma unica linha visual sem perder o alinhamento com a narracao.
_Avoid_: legenda quebrada, legenda em duas linhas, texto comprimido sem sincronizacao

**Sincronia Temporal da Legenda**:
A relacao entre o momento em que a legenda aparece no **Arquivo de Video Final** e o trecho correspondente da narracao.
_Avoid_: corte legivel, estetica da legenda, cobertura textual

**Corte Semantico da Legenda**:
A divisao da legenda em blocos que preservam unidades legiveis de fala, evitando fragmentos soltos que prejudicam a compreensao.
_Avoid_: drift temporal, quebra puramente por caractere, legenda tecnicamente alinhada mas ruim de ler

**Revisao Humana**:
A avaliacao feita por uma pessoa antes de aprovar, rejeitar, agendar ou publicar um **Job de Video**.
_Avoid_: aprovado, publicavel, upload pronto

**Hub de Revisao**:
A superficie operacional onde uma pessoa acompanha, assiste e decide sobre **Jobs de Video**.
_Avoid_: servidor, porta, painel

**Console Operacional**:
Uma apresentacao do **Hub de Revisao** orientada a fila, estado e proxima acao sobre **Jobs de Video**.
_Avoid_: formulario administrativo, landing page, dashboard decorativo

**Centro de Crescimento do Canal**:
A superficie do **Hub de Revisao** dedicada a estatisticas, aprendizado editorial e recomendacoes para melhorar proximos **Jobs de Video**.
_Avoid_: centro de publicacao, configuracao, agenda operacional, dashboard generico, tutor solto

**Secao Operacional de Publicacao**:
A superficie operacional que mostra conexao, agenda, aprovados sem agenda e publicacoes recentes fora do **Centro de Crescimento do Canal**.
_Avoid_: misturar configuracao com crescimento, agenda dentro do centro de crescimento, publicacao sem contexto operacional

**Relatorio Automatizado de Performance**:
Uma leitura recorrente dos resultados de **Jobs de Video** publicados para identificar o que funcionou, o que caiu e o que deve orientar proximos conteudos.
_Avoid_: print do YouTube Studio, metricas soltas, relatorio manual

**Pacote Editorial do Job**:
O conjunto de tema, titulo, hook, loop, beats, payoff, duracao, metadados e sinais de qualidade usado para explicar a performance de um **Job de Video**.
_Avoid_: olhar so views, analisar video sem roteiro, diagnostico sem contexto editorial

**Snapshot Diario de Performance**:
Uma coleta diaria de metricas dos **Jobs de Video** publicados, usada para atualizar rankings sem gerar interpretacao editorial pesada.
_Avoid_: relatorio completo diario, consulta em tempo real na tela, decisao por dado stale invisivel

**Coleta de Performance Ativa**:
A permissao operacional para executar **Snapshot Diario de Performance** recorrente independentemente da pausa de criacao ou publicacao automatizada.
_Avoid_: automacao de criacao, upload automatico, pausar aprendizado junto com geracao

**Janela Ativa de Performance**:
O periodo recente em que **Jobs de Video** publicados continuam elegiveis para **Snapshot Diario de Performance** recorrente.
_Avoid_: sincronizar todo historico todo dia, tratar video antigo como prioridade diaria, coleta sem limite

**Relatorio Semanal de Crescimento**:
Uma sintese interpretativa do **Assistente de Crescimento do Canal** que transforma snapshots recentes em diagnostico, **Linhas Editoriais Vencedoras** e **Propostas de Crescimento**.
_Avoid_: alerta solto, dashboard de numero, opiniao sem periodo definido

**Execucao de Relatorio de Crescimento**:
Uma geracao persistida de **Relatorio Semanal de Crescimento**, iniciada por agenda automatica ou acao humana sem bloquear a navegacao no **Hub de Revisao**.
_Avoid_: request longo na pagina, relatorio efemero, botao que trava a tela

**Lote Semanal de Roteiros Sugeridos**:
Um conjunto pequeno de **Roteiros Sugeridos por Crescimento** produzido junto ao **Relatorio Semanal de Crescimento** para tornar o diagnostico acionavel.
_Avoid_: backlog massivo, sugestoes ilimitadas, ideias fora do formato de roteiro

**Linha Editorial Vencedora**:
Um padrao de tema, hook, ritmo, promessa, payoff ou formato que performou acima do restante e pode inspirar novos **Jobs de Video** sem virar copia.
_Avoid_: copiar video, tema repetido, template fixo, viral por chute

**Linha Editorial Sustentavel**:
Uma subdivisao do nicho de curiosidades que consegue gerar **Jobs de Video** recorrentes com retencao, evidencias disponiveis e variedade suficiente.
_Avoid_: tendencia unica, tema amplo demais, formato impossivel de repetir

**Linha de Curiosidade Cotidiana**:
Uma **Linha Editorial Sustentavel** baseada em objetos, habitos, casa, cozinha, clima, celular e situacoes familiares.
_Avoid_: curiosidade abstrata, noticia, tema sem identificacao imediata

**Linha de Percepcao e Corpo Leve**:
Uma **Linha Editorial Sustentavel** baseada em sensacoes, memoria, sono, visao e comportamento cotidiano sem promessa medica forte.
_Avoid_: conselho medico, diagnostico, promessa de saude

**Linha de Ciencia Visual Simples**:
Uma **Linha Editorial Sustentavel** baseada em fenomenos verificaveis com imagem mental forte e explicacao curta.
_Avoid_: aula enciclopedica, tema abstrato sem visual, afirmacao sem evidencia

**Linha de Tecnologia Popular**:
Uma **Linha Editorial Sustentavel** baseada em celular, internet, IA e tecnologia comum sem depender de noticia efemera.
_Avoid_: cobertura de lançamento, rumor, tutorial tecnico

**Linha de Natureza com Payoff Visual**:
Uma **Linha Editorial Sustentavel** baseada em animais, plantas ou ambientes naturais quando o payoff pode ser visual e memoravel.
_Avoid_: ficha enciclopedica, curiosidade de animal sem virada, ranking generico

**Canal de Referencia Competitiva**:
Um canal externo usado para comparar padrões editoriais e descobrir aprendizados aplicaveis aos proximos **Jobs de Video** sem copiar identidade ou roteiro.
_Avoid_: concorrente generico, canal para copiar, benchmark sem nicho

**Canal Candidato de Referencia**:
Um canal externo descoberto pelo **Scout Competitivo de Shorts** que ainda precisa de validacao humana antes de virar **Canal de Referencia Competitiva**.
_Avoid_: referencia aprovada, canal usado sem revisao, concorrente presumido

**Maturidade de Referencia Viral**:
O tempo minimo apos publicacao antes de tratar um short externo como candidato forte para aprendizado editorial.
_Avoid_: decidir por pico inicial, tratar video novo como vencedor, comparar sem tempo de teste

**Scout Competitivo de Shorts**:
Uma leitura automatizada de **Shorts de Referencia Viral** que identifica padroes editoriais aplicaveis como aprendizado, sem alterar a producao sem aprovacao humana.
_Avoid_: scraper para copiar, ajuste automatico invisivel de prompt, gerador direto de jobs

**Rodada de Scout Competitivo**:
Uma execucao do **Scout Competitivo de Shorts** para coletar, classificar e sintetizar referencias sem bloquear criacao, revisao ou publicacao.
_Avoid_: etapa obrigatoria do job, rotina que trava publicacao, analise sem artefato

**Short de Referencia Viral**:
Um video curto externo com desempenho forte o bastante para servir como amostra de aprendizado editorial.
_Avoid_: qualquer video popular, copiar roteiro, evidencia sem metricas

**Short Vencedor do Canal**:
Um **Job de Video** publicado no canal com retencao alta, volume confiavel e sinais suficientes para orientar aprendizado editorial interno.
_Avoid_: video externo, views isoladas, amostra pequena

**Arquitetura de Retencao do Roteiro**:
A organizacao de hook, loop, escalada, payoff e fechamento que explica por que um roteiro sustenta atencao ate o fim.
_Avoid_: transcricao completa, resumo do tema, estilo visual isolado

**Leitura Textual de Referencia**:
A analise de titulo, descricao, transcricao disponivel e estrutura narrativa de um **Short de Referencia Viral** ou **Short Vencedor do Canal** para extrair aprendizado editorial.
_Avoid_: analise visual profunda, copiar roteiro, inferir retencao externa

**Transcricao Autorizada de Referencia**:
Uma transcricao usada na **Leitura Textual de Referencia** quando vem de recurso oficial, conteudo proprio, permissao explicita ou envio humano.
_Avoid_: download automatico de video externo sem autorizacao, transcricao inventada, burlar ausencia de captions

**Leitura Visual de Referencia**:
A analise limitada de sinais visuais de um **Short de Referencia Viral** ou **Short Vencedor do Canal**, usada apenas depois da **Leitura Textual de Referencia** provar valor.
_Avoid_: baixar video externo sem criterio, copiar identidade visual, usar visual como fonte factual

**Perfil de Retencao Aprendido**:
Um aprendizado editorial versionado derivado de **Shorts Vencedores do Canal** e **Shorts de Referencia Viral**, usado para orientar proximos roteiros sem editar diretamente a **Configuracao Global de Prompt Viral**.
_Avoid_: prompt drift, copiar exemplos, ajuste invisivel de producao

**Esqueleto de Retencao Vencedor**:
Um padrao abstrato e reaplicavel de movimentos narrativos derivado de varias amostras vencedoras, mesmo quando desafia o formato atual de roteiro, sem reutilizar palavras, fatos ou narrativa especifica de um unico video.
_Avoid_: copiar roteiro, encaixar tudo no formato atual, trocar apenas substantivos, depender de uma unica referencia

**Aposta Agressiva de Retencao**:
Um **Esqueleto de Retencao Vencedor** criado com amostra menor para acelerar aprendizado, podendo virar experimento rapido sem promocao direta.
_Avoid_: padrao definitivo, prova estatistica, mudanca global imediata

**Experimento de Retencao Aprendida**:
A aplicacao limitada de um **Perfil de Retencao Aprendido** a poucos **Jobs de Video** para medir efeito antes de virar padrao.
_Avoid_: promocao direta, teste sem limite, alterar todos os jobs

**Conflito Editorial Experimental**:
Um conflito entre uma **Aposta Agressiva de Retencao** e um gate editorial existente, tratado como diagnostico revisavel quando nao afeta factualidade, direitos, duracao, idioma ou integridade tecnica.
_Avoid_: ignorar gate critico, publicar inseguro, esconder conflito

**Sucesso Forte de Retencao Aprendida**:
O resultado de um **Experimento de Retencao Aprendida** quando pelo menos um **Job de Video** vira **Short Vencedor do Canal**.
_Avoid_: views sem retencao, melhora subjetiva, promocao sem volume confiavel

**Sucesso Parcial de Retencao Aprendida**:
O resultado de um **Experimento de Retencao Aprendida** quando o lote melhora claramente a linha editorial, mas ainda nao produz **Short Vencedor do Canal**.
_Avoid_: tratar como padrao, ignorar aprendizado, concluir sem baseline

**Promocao de Perfil de Retencao**:
A decisao humana de tornar um **Perfil de Retencao Aprendido** padrao depois de evidencia propria suficiente.
_Avoid_: promover por concorrente, promover por gosto, mudar prompt global sem medicao

**Sinal Primario de Performance**:
A metrica que mais pesa para identificar uma **Linha Editorial Vencedora**, priorizando retencao em vez de alcance bruto.
_Avoid_: views como criterio unico, likes isolados, impressao subjetiva

**Score de Crescimento**:
Uma pontuacao comparativa de performance que prioriza retencao, usa volume como confianca e usa compartilhamentos e inscritos ganhos como desempate.
_Avoid_: ranking por views, nota de vaidade, score de monetizacao

**Objetivo Primario de Crescimento**:
A meta editorial do **Assistente de Crescimento do Canal**, priorizando retencao e replay em Shorts antes de alcance bruto ou monetizacao.
_Avoid_: crescer por views isoladas, perseguir RPM primeiro, otimizar para vaidade

**Volume Minimo de Confianca**:
O patamar minimo de visualizacoes usado antes de tratar um resultado de performance como evidência confiavel.
_Avoid_: premiar video com amostra pequena, ignorar volume, confiar em poucos views

**Base Minima de Crescimento**:
O conjunto minimo de snapshots e **Jobs de Video** com volume confiavel necessario antes de gerar um **Relatorio Semanal de Crescimento** por IA.
_Avoid_: relatorio com amostra fraca, diagnostico por poucos videos, IA opinando sem dados

**Assistente de Crescimento do Canal**:
A orientacao por IA baseada em metricas reais, historico editorial e objetivos do canal para recomendar melhorias acionaveis nos proximos **Jobs de Video**.
_Avoid_: chatbot generico, opiniao sem dados, tutorial solto de YouTube

**Proposta de Crescimento**:
Uma sugestao acionavel do **Assistente de Crescimento do Canal** para criar ou melhorar um **Job de Video**, exigindo confirmacao humana antes de virar trabalho.
_Avoid_: job automatico, ideia solta, recomendacao sem acao, geracao cega

**Recomendacao Rapida de Crescimento**:
Uma orientacao deterministica e imediata do **Centro de Crescimento do Canal** baseada em metricas recentes, sem interpretacao generativa por IA.
_Avoid_: relatorio por IA, opiniao editorial pesada, conselho recalculado por LLM a cada refresh

**Roteiro Sugerido por Crescimento**:
Um **Roteiro Pronto** rascunhado por uma **Proposta de Crescimento**, aguardando revisao humana antes de entrar no **Banco de Roteiros Prontos** ou virar **Job de Video**.
_Avoid_: job criado direto, roteiro aprovado automaticamente, sugestao sem formato editorial

**Variacao de Linha Editorial**:
Um novo **Job de Video** inspirado em uma **Linha Editorial Vencedora**, preservando padroes de performance sem copiar tema, texto, hook ou payoff.
_Avoid_: republicacao, duplicata narrativa, reciclagem literal

**Video Externo de Referencia**:
Um video publicado no canal sem origem em **Job de Video**, usado apenas como referencia comparativa quando importado explicitamente.
_Avoid_: job historico presumido, dado invisivel do canal, publicacao sem vinculo

**Configuracao de Ambiente**:
Um valor necessario para iniciar ou conectar o sistema, como caminho de dados, URL publica, segredo ou credencial de provedor.
_Avoid_: ajuste diario, preferencia de operacao, controle de rotina

**Configuracao Operacional do Hub**:
Um ajuste nao secreto que uma pessoa muda no **Hub de Revisao** para controlar providers, musica, automacao ou publicacao sem editar a **Configuracao de Ambiente**.
_Avoid_: segredo, variavel obrigatoria de boot, tuning interno

**Sobreposicao Operacional**:
O valor persistido pelo **Hub de Revisao** que prevalece sobre o default da **Configuracao de Ambiente** para uma **Configuracao Operacional do Hub**.
_Avoid_: duplicidade de env, patch manual, estado invisivel

**Barra Lateral Global do Hub**:
A area persistente do **Console Operacional** que aparece em todas as telas e concentra identidade, navegacao principal, conexao e configuracoes operacionais recorrentes.
_Avoid_: sidebar do workbench, painel de criacao, bloco de publicacao

**Barra de Navegacao Mobile do Hub**:
A apresentacao compacta da navegacao principal do **Console Operacional** em telas pequenas, preservando a fila como foco inicial e movendo controles recorrentes para acionadores leves.
_Avoid_: sidebar empilhada, menu completo acima da fila, formulario inline no topo

**Busca Recolhida do Hub**:
A apresentacao compacta da busca do **Hub de Revisao** quando a tela pequena precisa preservar o foco na fila; a busca aparece como acionador e expande apenas quando uma pessoa vai filtrar **Jobs de Video**.
_Avoid_: campo de busca sempre aberto no mobile, formulario de filtros ocupando a primeira dobra

**Acao Global de Criacao de Job**:
O acionador persistente para iniciar um **Job de Video** a partir do **Hub de Revisao**, apresentado como comando leve e abrindo uma superficie focada de criacao.
_Avoid_: formulario inline permanente, painel escondido no fim da fila, criacao misturada com filtros

**Filtro Rapido da Fila**:
Um recorte recorrente e visivel da fila do **Hub de Revisao** usado para alternar rapidamente entre estados comuns de **Jobs de Video**.
_Avoid_: filtro avancado, ordenacao, formulario completo de busca

**Filtro de Agenda Ativa**:
Um **Filtro Rapido da Fila** que mostra apenas **Jobs de Video** com **Horario de Publicacao** ativo ou tentativa de publicacao associada, incluindo estados programado, publicando e falha de upload.
_Avoid_: aprovado sem agenda, pronto para aprovar, qualquer job aprovado

**Filtro de Aprovados Sem Agenda**:
Um **Filtro Rapido da Fila** que mostra **Jobs de Video** aprovados para publicar, mas ainda sem **Horario de Publicacao** ativo.
_Avoid_: agendado, publicado, publicando

**Filtro Avancado da Fila**:
A superficie recolhida para refinar busca, status, fallback, revisao e ordenacao da fila quando os **Filtros Rapidos da Fila** nao bastam.
_Avoid_: chips principais, navegacao global, painel sempre aberto

**Fluxo de Decisao**:
A ordem de tela que prioriza a proxima acao humana sobre diagnosticos e configuracoes.
_Avoid_: dashboard generico, tela de dados, painel tecnico

**Tema Automatico**:
Um tema escolhido pelo sistema quando o pedido nao traz um assunto explicito.
_Avoid_: tema aleatorio, fallback local, sugestao solta

**Curiosidade do Cotidiano**:
Um recorte de Short baseado em situacoes comuns, habitos, objetos, consumo, tecnologia popular ou pequenas descobertas do dia a dia para gerar conexao ampla com o publico.
_Avoid_: ciencia estrita por padrao, paper obrigatorio para todo tema, curiosidade abstrata sem identificacao

**Perfil de Evidencia**:
A classificacao editorial que define qual tipo de fonte um **Job de Video** precisa para sustentar suas afirmacoes factuais.
_Avoid_: fact pack unico para todo tema, paper obrigatorio, checagem solta por LLM

**Cascata de Evidencia**:
A ordem de tipos de fonte consultados conforme o **Perfil de Evidencia** de um **Job de Video**.
_Avoid_: buscar sempre em papers, usar uma unica fonte global, escolher fonte por conveniencia do provider

**Camada de Evidencia**:
A parte do fluxo editorial que transforma fontes confiaveis em **Cartoes de Evidencia** antes da geracao do roteiro.
_Avoid_: deixar a LLM pesquisar sozinha, tratar busca como roteiro, validar fato apenas no fim

**Verificador de Evidencia**:
A validacao que decide se uma fonte cobre o escopo necessario para virar **Fonte de Evidencia** ou apenas **Fonte de Contexto**.
_Avoid_: julgamento livre da LLM, correspondencia por palavra-chave, promover fonte tangencial

**Fonte de Contexto**:
Uma fonte que ajuda a entender o tema de um **Job de Video**, mas nao sustenta sozinha uma afirmacao factual especifica.
_Avoid_: tratar como prova, citar como lastro de claim, promover para evidência sem escopo

**Fonte de Evidencia**:
Uma fonte cujo escopo cobre diretamente a afirmacao factual que ela sustenta em um **Job de Video**.
_Avoid_: fonte tangencial, fonte sobre outro mecanismo, fonte relacionada apenas por palavra-chave

**Cartao de Evidencia**:
Uma unidade editorial que liga uma afirmacao permitida a uma **Fonte de Evidencia**, seus limites e a linguagem segura para uso no roteiro.
_Avoid_: fato solto, resumo de fonte, claim inventada pela LLM

**Embalagem Viral Permitida**:
A forma de transformar um **Cartao de Evidencia** em hook, loop, imagem mental, payoff ou fechamento de alta retencao sem ampliar a afirmacao factual sustentada.
_Avoid_: exagero factual, clickbait falso, tornar o cartao burocratico ou academico

**Hook Agressivo Conservador**:
Uma abertura de alta tensao e potencial viral que usa contraste, surpresa ou consequencia cotidiana sem exagerar a afirmacao factual permitida.
_Avoid_: promessa falsa, causalidade inventada, numero sem fonte, universalizacao

**Afirmacao Observacional**:
Uma afirmacao de baixa exigencia factual baseada em experiencia comum, linguagem subjetiva ou enquadramento editorial, sem declarar causalidade tecnica, numero, regra atual ou fato historico especifico.
_Avoid_: causalidade tecnica disfarçada, fato universal, claim sem evidência apresentada como certeza

**Torneio de LLMs**:
A comparacao controlada de modelos usando os mesmos **Jobs de Video**, **Perfis de Evidencia** e **Cartoes de Evidencia** para medir custo, velocidade, obediencia factual e qualidade editorial.
_Avoid_: teste isolado impressionista, comparar modelos com entradas diferentes, escolher apenas por velocidade

**Candidato de Torneio**:
Um modelo/provider configurado para participar do **Torneio de LLMs** sem alterar o provider operacional padrao do pipeline.
_Avoid_: trocar provider global manualmente, teste sem alias estavel, misturar configuracao do hub com benchmark

**Conjunto de Benchmark Editorial**:
Um grupo fixo de temas representativos usado para comparar modelos e providers no **Torneio de LLMs**.
_Avoid_: testar um tema isolado, mudar entradas entre modelos, benchmark sem nichos cotidianos

**Caso de Benchmark Editorial**:
Uma entrada fixa e barata do **Conjunto de Benchmark Editorial** usada para comparar modelos em uma etapa editorial especifica sem executar um **Job de Video** completo.
_Avoid_: job completo, smoke test de provider, tema solto, pipeline multimidia

**Rodada Inicial do Torneio**:
A primeira comparacao do **Torneio de LLMs**, limitada a geracao de roteiro, reparo de roteiro e auditoria textual sobre **Casos de Benchmark Editorial**.
_Avoid_: plano de cenas inicial, render completo, comparacao por pipeline multimidia

**Rodada Textual Completa do Torneio**:
A comparacao do **Torneio de LLMs** que executa roteiro, reparo de roteiro e auditoria textual antes do **Comite de Decisao Pos-Torneio**.
_Avoid_: chamar pipeline multimidia de torneio completo, incluir cena ou render antes da decisao textual, comparar etapa que ainda nao tem artefato padronizado

**Triagem Textual do Torneio**:
A passagem curta do **Torneio de LLMs** que elimina candidatos indisponiveis, lentos, incompativeis ou instaveis antes da rodada textual completa.
_Avoid_: rodar benchmark completo em provider quebrado, decidir qualidade final por smoke test, esconder eliminacao operacional

**Medicao Separada por Etapa**:
A avaliacao do **Torneio de LLMs** que mede geracao inicial, reparo e auditoria como capacidades distintas.
_Avoid_: reparo escondendo roteiro inicial ruim, media unica por modelo, misturar capacidades de etapas diferentes

**Pacote Fixo de Auditoria**:
Um conjunto igual de roteiros e artefatos usado para comparar candidatos na etapa de auditoria do **Torneio de LLMs**.
_Avoid_: modelo auditando apenas a propria resposta, auditoria sem casos negativos, comparar auditores com entradas diferentes

**Pacote de Artefatos do Torneio**:
O conjunto de respostas, vetos, custos, latencias, falhas e rastros editoriais produzido pelos candidatos para o **Comite de Decisao Pos-Torneio**.
_Avoid_: julgamento sem artefato, ler apenas ranking agregado, pedir avaliacao profunda para todos os candidatos

**Benchmark Editorial Inicial**:
A primeira versao do **Benchmark Editorial Versionado**, composta por 12 **Casos de Benchmark Editorial** de curiosidade cotidiana, saude leve, tecnologia popular e percepcao/comportamento.
_Avoid_: benchmark grande antes do primeiro ranking, amostra pequena demais, conjunto sem variedade de risco factual

**Caso Adversarial Publicavel**:
Um **Caso de Benchmark Editorial** feito para expor exagero, invencao ou desobediencia factual sem deixar de ser um tema plausivel para canal.
_Avoid_: pegadinha artificial, tema impossivel de publicar, caso sem valor editorial

**Cartao de Evidencia Congelado**:
Um **Cartao de Evidencia** versionado dentro de um **Caso de Benchmark Editorial** para manter o **Torneio de LLMs** comparavel entre execucoes.
_Avoid_: buscar fonte durante o torneio, mudar evidencia entre candidatos, comparar modelos com fatos diferentes

**Benchmark Editorial Versionado**:
Uma versao persistida do **Conjunto de Benchmark Editorial** que torna resultados de **Torneio de LLMs** comparaveis ao longo do tempo.
_Avoid_: benchmark ad hoc, trocar tema durante comparacao, resultado sem versao de entrada

**Roteamento Editorial por Etapa**:
A escolha de modelos ou providers diferentes conforme a etapa editorial e o **Perfil de Evidencia** de um **Job de Video**.
_Avoid_: um modelo global para tudo, fallback opaco, trocar provider sem medir etapa

**Ranking por Etapa do Torneio**:
A classificacao principal do **Torneio de LLMs** que escolhe vencedores separados para roteiro, reparo e auditoria textual.
_Avoid_: vencedor unico global, media que esconde fraqueza por funcao, escolha por impressao geral

**Recomendacao de Roteamento do Torneio**:
Uma sugestao de modelos por etapa produzida pelo **Torneio de LLMs** sem alterar automaticamente o provider operacional dos **Jobs de Video**.
_Avoid_: promocao automatica de provider, alterar producao por benchmark isolado, roteamento invisivel

**Escolha de Custo-Beneficio do Projeto**:
A sintese do **Comite de Decisao Pos-Torneio** que recomenda o melhor roteamento por etapa e, separadamente, o melhor modelo unico quando simplicidade operacional for mais importante.
_Avoid_: vencedor unico como fonte principal, custo menor sem qualidade minima, esconder diferencas entre roteiro, reparo e auditoria

**Finalista do Torneio**:
Um candidato que passou pelos vetos objetivos e entrou na avaliacao seletiva do **Comite de Decisao Pos-Torneio** em pelo menos uma etapa.
_Avoid_: avaliar todos os candidatos por Codex, promover candidato instavel, esconder o piso de viabilidade

**Eliminado na Triagem do Torneio**:
Um candidato retirado da comparacao competitiva por falha objetiva na **Triagem Textual do Torneio**.
_Avoid_: misturar indisponivel com perdedor, repetir teste caro sem corrigir acesso, esconder motivo de eliminacao

**Candidato Nao Comparavel do Torneio**:
Um candidato sem artefatos ou metricas suficientes para entrar no ranking competitivo do **Torneio de LLMs**.
_Avoid_: ranquear medicao incompleta, tratar ausencia de custo como custo zero, promover candidato sem etapa suportada

**Comite de Decisao Pos-Torneio**:
Uma avaliacao assistida por Codex que interpreta artefatos completos do **Torneio de LLMs** para recomendar custo-beneficio e roteamento sem substituir os rankings objetivos por etapa.
_Avoid_: juiz por caso, prompt de avaliacao token-intensivo, vencedor global que apaga fraquezas por etapa

**Relatorio de Decisao do Torneio**:
O artefato final do **Comite de Decisao Pos-Torneio** que resume vencedores por etapa, custo-beneficio, riscos, eliminacoes e recomendacao operacional.
_Avoid_: conclusao sem evidencia, decisao apenas em chat, relatorio que substitui artefatos brutos

**Veto Duro do Torneio**:
Uma falha que elimina uma resposta do **Ranking por Etapa do Torneio** mesmo quando ela parece editorialmente forte.
_Avoid_: penalidade leve, preferencia subjetiva, aceitar invencao factual por boa escrita

**Orcamento de Falha do Torneio**:
O limite de falhas operacionais aceitas para um candidato continuar competindo em uma etapa do **Torneio de LLMs**.
_Avoid_: esperar timeouts repetidos, gastar quota com candidato instavel, tratar veto editorial como indisponibilidade operacional

**Nota de Roteiro do Torneio**:
A avaliacao de uma resposta de roteiro no **Torneio de LLMs**, priorizando obediencia factual, hook, loop, replay, escalada, payoff, clareza em pt-BR, custo e latencia nessa ordem.
_Avoid_: nota por beleza textual, custo antes de qualidade minima, ranking sem retencao

**Avaliador Hibrido do Torneio**:
A combinacao de vetos objetivos e julgamento editorial por IA usada para pontuar respostas em **Casos de Benchmark Editorial**.
_Avoid_: juiz unico sem gates, regra deterministica fingindo medir replay, opiniao humana ad hoc

**Juiz Editorial Versionado**:
Um modelo e prompt fixos usados fora da competicao principal para avaliar qualidade editorial no **Torneio de LLMs**.
_Avoid_: juiz variavel por rodada, candidato julgando a si mesmo sem registro, prompt de avaliacao sem versao

**Juiz Editorial Inicial**:
O primeiro **Juiz Editorial Versionado** do **Torneio de LLMs**, usando um modelo premium fixo para avaliar qualidade editorial dos candidatos.
_Avoid_: juiz barato por padrao, troca silenciosa de avaliador, avaliacao sem conflito registrado

**Modo de Escala**:
A configuracao operacional que prioriza baixo custo medio por **Job de Video** mantendo a qualidade minima de publicacao.
_Avoid_: qualidade maxima em toda tentativa, gastar modelo premium por padrao, publicar sem gates

**Modo Premium**:
A configuracao operacional que permite maior custo por **Job de Video** quando potencial, risco ou falha repetida justificam uma geracao mais forte.
_Avoid_: gastar caro sempre, aprovar sem revisao, tratar todo job como premium

**Custo por Job Publicavel**:
O custo total de geracao e revisao automatizada necessario para um **Job de Video** passar pelos gates e chegar a revisao ou publicacao.
_Avoid_: custo por token isolado, preco nominal do modelo, ignorar retries e fallbacks

**Custo Operacional Observado do Torneio**:
A medida de custo do **Torneio de LLMs** baseada em tokens reportados, latencia, falhas, retries, timeouts e taxa de sucesso sem converter para dinheiro.
_Avoid_: preco chutado, comparar so tokens, ignorar falha operacional barata

**Custo Estimado Versionado**:
A estimativa de custo em dinheiro usada no **Torneio de LLMs** somente quando baseada em uma tabela de precos versionada.
_Avoid_: chutar preco, comparar custo sem fonte, usar preco atual invisivel em resultado historico

**Roteiro Pronto**:
Um roteiro fornecido por uma pessoa como fonte de verdade editorial validada para um **Job de Video**.
_Avoid_: prompt, tema, titulo completo

**Banco de Roteiros Prontos**:
Um estoque de **Roteiros Prontos** validados por uma pessoa para a automacao transformar em **Jobs de Video** sem gerar nova pauta ou novo roteiro por LLM.
_Avoid_: fila de prompts, temas soltos, backlog gerado pelo app

**Pagina de Biblioteca de Roteiros**:
A superficie dedicada do **Hub de Revisao** para importar, consultar e acompanhar o **Banco de Roteiros Prontos** fora de modais globais.
_Avoid_: modal como destino principal, textarea escondido na sidebar, painel principal de publicacao, configuracao escondida

**Configuracao Global de Prompt Viral**:
A configuracao recorrente do **Hub de Revisao** que orienta copywriting e retencao sem substituir o formato interno dos **Jobs de Video**.
_Avoid_: acao da fila, roteiro pronto, instrucao por job

**Roteiro Viral Estruturado**:
Um roteiro gerado pelo sistema que deve seguir a estrutura editorial canonica de Titulo, Hook, Loop, Beats, Payoff, Fechamento e Hashtags, com hook forte, loop mental, escalada, payoff tardio e fechamento de replay.
_Avoid_: texto livre, lista plana de fatos, aula curta, resumo enciclopedico

**Contrato Visual do Roteiro**:
A leitura semantica visual de um **Roteiro Viral Estruturado** ou **Roteiro Pronto**, usada para preservar promessa de hook, tensao de loop, escalada de beats, payoff tardio e fechamento de replay nas cenas.
_Avoid_: prompt de imagem solto, regra deterministica por palavra, estilo visual generico

**Janela Alvo de Duracao do Short**:
A duracao desejada do **Arquivo de Video Final** para Shorts gerados automaticamente, entre 35 e 55 segundos.
_Avoid_: duracao fora de 35-55 segundos, duracao minima tecnica sem contexto editorial, video curto demais para validar retencao

**Status Compacto da Automacao**:
O resumo da **Pausa Global da Automacao** e do estoque do **Banco de Roteiros Prontos** na **Barra Lateral Global do Hub**, podendo alternar a pausa sem iniciar ciclos.
_Avoid_: botao de rodar ciclo, comando de upload, log completo

**Lote de Roteiros Prontos**:
Um conjunto de **Roteiros Prontos** enviado por arquivo ou copiar/colar para alimentar o **Banco de Roteiros Prontos**.
_Avoid_: upload de videos, lista de temas, texto sem rotulos, CSV inicial, JSON inicial

**Roteiro Pronto Consumido**:
Um item do **Banco de Roteiros Prontos** que ja foi usado para criar um **Job de Video**, mesmo quando esse job falha antes da publicacao.
_Avoid_: tentar o mesmo roteiro todo dia, duplicar job, reciclar sem revisao, voltar automaticamente ao banco

**Selecao Aleatoria de Roteiro**:
A escolha nao sequencial de um item disponivel do **Banco de Roteiros Prontos**, preservando a prioridade do banco mesmo quando houver **Similaridade Narrativa**.
_Avoid_: ordem de importacao obrigatoria, prioridade manual inicial, fallback por similaridade

**Roteiro Pulado por Similaridade**:
Um conceito historico que nao deve impedir um item disponivel do **Banco de Roteiros Prontos** de gerar **Job de Video**.
_Avoid_: criterio ativo de fallback, consumido sem tentativa, rejeitado por similaridade

**Fallback para Tema Automatico**:
A escolha de usar **Tema Automatico** apenas quando o **Banco de Roteiros Prontos** nao tem nenhum item disponivel para tentativa.
_Avoid_: fallback por similaridade, ignorar roteiro pronto disponivel, gerar roteiro antes de consumir o banco

**Texto Rotulado**:
Um texto dividido por rotulos editoriais reconheciveis, como titulo, hook, beats, payoff e fechamento.
_Avoid_: JSON, prompt livre, markdown arbitrario

**Normalizacao de Roteiro Pronto**:
A conversao de variacoes leves de sintaxe em **Texto Rotulado** canonico antes de importar ou criar um **Job de Video**, preservando o texto editorial e removendo apenas formatacao como negrito de Markdown e separadores de lote.
_Avoid_: reescrita de roteiro, fact-check automatico, reparo editorial invisivel

**Loop Editorial**:
A tensao narrativa que sustenta a curiosidade entre o hook e a entrega dos beats em um **Roteiro Pronto**.
_Avoid_: fato declarado, fonte factual, CTA

**Imagem de Hook Visual**:
A primeira imagem de um **Job de Video**, criada para tornar o hook visualmente compreensivel antes do espectador depender do audio.
_Avoid_: thumbnail, capa, poster, imagem generica de abertura

**Plano de Cenas**:
A divisao visual de um roteiro aprovado em cenas ordenadas, cada uma com funcao narrativa, trecho de narracao e orientacao visual.
_Avoid_: prompt de imagem isolado, storyboard livre, roteiro reescrito

**Especificacao Visual da Cena**:
A orientacao visual concreta de uma cena do **Plano de Cenas**, usada pelo **Gerador de Imagens** para produzir um asset coerente com a narracao, a **Intencao Visual** e o **Contrato Visual do Roteiro**.
_Avoid_: prompt solto, descricao estetica generica, copia da narracao, lista longa de proibicoes

**Intencao Visual**:
A funcao editorial que uma cena cumpre visualmente dentro de um **Plano de Cenas**.
_Avoid_: estilo de camera, categoria tecnica solta, descricao estetica

**Movimento Visual de Cena**:
A variacao sutil e perceptivelmente estavel de enquadramento durante uma cena do **Arquivo de Video Final**, usada para reduzir monotonia sem mudar a **Intencao Visual** ou a narracao aprovada.
_Avoid_: efeito gratuito, transicao chamativa, camera como substituta de cena ruim, reescrita visual, tremor visual, pulso de zoom

**Validacao Visual de Asset**:
A avaliacao de uma imagem gerada contra o **Contrato Visual do Roteiro** e a funcao narrativa da cena que ela representa.
_Avoid_: score semantico generico, qualidade estetica isolada, aprovacao por provider

**Fato Declarado**:
Uma afirmacao factual em um **Roteiro Pronto** cuja revisao e assumida por quem enviou o roteiro.
_Avoid_: fato verificado pelo app, fonte automatica, suposicao

**Confirmacao de Factualidade**:
A declaracao de que os **Fatos Declarados** em um **Roteiro Pronto** ja foram revisados antes do envio.
_Avoid_: fact-check automatico, fonte do app, aprovacao de publicacao

**Validacao Humana de Roteiro Pronto**:
A declaracao de que uma pessoa ja aprovou o texto, promessa, retencao, originalidade, metadados editoriais e factualidade assumida de um **Roteiro Pronto**.
_Avoid_: auditoria editorial automatica, score editorial, bloqueio de copy

**Confirmacao Factual por Lote**:
A declaracao de uma pessoa de que assume a factualidade dos **Fatos Declarados** em todos os itens de um **Lote de Roteiros Prontos**.
_Avoid_: IA confirmou, verdade automatica, checagem implicita

**Horario de Publicacao**:
A data, hora e fuso escolhidos para publicar um **Job de Video** aprovado.
_Avoid_: data tecnica, timestamp cru, horario do servidor

**Publicacao Automatizada**:
A decisao do sistema de aprovar, agendar e publicar um **Job de Video** sem **Revisao Humana** previa, usando criterios explicitos de score e bloqueios.
_Avoid_: aprovacao manual, piloto automatico solto, upload sem criterio

**Elegibilidade Automatizada**:
A condicao de um **Job de Video** em `ready_for_upload` que permite **Publicacao Automatizada** depois de passar por scores minimos e checagem de repeticao.
_Avoid_: monetization_review, blocked_for_monetization, publicar qualquer job concluido

**Tema Amplo**:
Uma categoria editorial recorrente, como espacial ou tecnologia, que pode aparecer em varios **Jobs de Video** sem ser considerada repeticao por si so.
_Avoid_: roteiro repetido, historia similar, duplicata semantica

**Similaridade Narrativa**:
A proximidade semantica entre roteiro, historia, hook, virada, payoff ou estrutura de dois **Jobs de Video**.
_Avoid_: mesmo tema amplo, mesma categoria, nicho parecido

**Risco Medio de Repeticao**:
Um sinal de **Similaridade Narrativa** que reduz o score de **Elegibilidade Automatizada**, mas nao bloqueia sozinho a **Publicacao Automatizada**.
_Avoid_: bloqueio automatico, duplicata comprovada, erro grotesco

**Risco Alto de Repeticao**:
Um sinal forte de **Similaridade Narrativa** que bloqueia **Publicacao Automatizada**, salvo quando um **Roteiro Pronto** tiver confirmacao humana de originalidade.
_Avoid_: sugestao leve, tema amplo repetido, penalidade pequena, bloqueio de roteiro revisado manualmente

**Score de Autoaprovacao**:
Uma pontuacao composta que combina monetizacao, factualidade, retencao, metadados, alinhamento semantico de assets e repeticao para decidir **Elegibilidade Automatizada**.
_Avoid_: aprovacao subjetiva, score unico sem criterio, decisao invisivel

**Score Diagnostico de Roteiro Pronto**:
Uma leitura informativa dos sinais editoriais automatizados de um **Job de Video** criado a partir do **Banco de Roteiros Prontos**, sem poder bloquear a **Publicacao Automatizada**.
_Avoid_: veto editorial automatico, substituir validacao humana, score bloqueante do banco

**Narracao Publicavel**:
A voz principal de um **Job de Video** quando ela soa natural para o publico, tem direito comercial confirmado e nao depende de provedor tecnico de baixa qualidade.
_Avoid_: qualquer TTS gerado, voz de teste, voz sintetica tecnica, audio sem direito comercial

**Direcao de Voz**:
A orientacao editorial que define como a **Narracao Publicavel** deve soar, priorizando hook, retencao, payoff e fechamento sem alterar o texto aprovado do roteiro.
_Avoid_: reescrita do roteiro, improviso do TTS, contexto visual solto, efeito de voz sem funcao editorial

**Perfil de Narrador**:
A escolha recorrente de personalidade vocal para uma **Narracao Publicavel**, baseada no tipo de roteiro, como explicativo, tenso, historico, caloroso ou agil.
_Avoid_: voz fixa para todo roteiro, alternancia aleatoria, efeito teatral sem relacao com a retencao

**Tentativa Automatizada Sem Publicacao**:
Um **Job de Video** criado pela automacao que falha, nao chega a `ready_for_upload` ou nao atinge o **Score de Autoaprovacao**, consumindo uma tentativa diaria sem ser descartado automaticamente.
_Avoid_: rejeicao automatica, apagar candidato, loop sem custo

**Recuperacao Dirigida do Job**:
A acao humana de retomar, corrigir ou recriar um **Job de Video** especifico que falhou depois de consumir um **Roteiro Pronto**.
_Avoid_: devolver automaticamente ao banco, repetir no cronjob, consumir outro roteiro para a mesma falha

**Retomada de Publicacao Automatizada**:
A continuacao de uma tentativa que ja gerou um **Job de Video** elegivel, mas ainda nao confirmou o **Agendamento Nativo do YouTube**.
_Avoid_: criar outro job para a mesma falha, duplicar upload, perder candidato aprovado

**Limite de Retomada de Publicacao**:
O maximo de tres tentativas de upload ou agendamento para o mesmo **Job de Video** elegivel antes de deixar a falha para acao manual.
_Avoid_: retry infinito, recriar job sem necessidade, insistir em upload problemático

**Avaliacao Posterior no YouTube Studio**:
A revisao feita por uma pessoa no YouTube Studio depois que um **Job de Video** ja foi publicado por **Publicacao Automatizada**.
_Avoid_: Revisao Humana, aprovacao previa, gate do hub

**Cadencia Diaria de Geracao**:
A regra operacional que cria ate tres **Jobs de Video** por dia para tentar preencher um **Dia Vago de Publicacao** sem sobrecarregar provedores, agenda ou revisao posterior.
_Avoid_: lote grande, geracao ilimitada, backlog automatico, retry aberto

**Primeiro Sucesso Automatizado**:
O primeiro **Job de Video** do dia que atinge **Elegibilidade Automatizada** e preenche um **Dia Vago de Publicacao**, encerrando novas tentativas naquele dia.
_Avoid_: gerar todos os candidatos, continuar apos agendar, publicar multiplos por acidente

**Dia Vago de Publicacao**:
Um dia no fuso de Sao Paulo sem **Horario de Publicacao** ativo na agenda interna.
_Avoid_: dia sem video no YouTube Studio, slot inferido fora do hub, lacuna manual

**Horario Padrao de Publicacao**:
O horario das 11h no fuso de Sao Paulo usado pela automacao para preencher um **Dia Vago de Publicacao**.
_Avoid_: horario aleatorio, proximo horario livre, horario do servidor

**Agendamento Nativo do YouTube**:
A publicacao futura configurada na propria plataforma do YouTube por `publishAt`, depois que o video foi enviado pela automacao.
_Avoid_: publicar na hora do cron, depender do worker as 11h, agenda apenas local

**Confirmacao de Publicacao no YouTube**:
A evidencia posterior de que o YouTube tornou o video publico no horario agendado.
_Avoid_: upload agendado, publishAt configurado, agenda local

**Canal de Publicacao**:
Uma plataforma de destino onde um **Job de Video** pode ser publicado com estado proprio, como YouTube Shorts ou TikTok.
_Avoid_: destino implicito, espelho invisivel, tag geral unica

**Confirmacao de Publicacao por Canal**:
A evidencia de que um **Canal de Publicacao** tornou o **Arquivo de Video Final** publico ou programado conforme a regra daquele canal.
_Avoid_: sucesso em outro canal, presuncao por horario, status global sem origem

**Agendamento por Canal**:
O horario planejado para publicar um **Job de Video** em um **Canal de Publicacao**, podendo ser sincronizado com outro canal sem depender da confirmacao posterior dele.
_Avoid_: copiar status do YouTube, publicar depois da confirmacao de outro canal, horario sem canal

**Retropostagem Controlada**:
A inclusao de **Jobs de Video** ja publicados ou programados em um **Canal de Publicacao** numa fila limitada para publicar em outro canal sem disparar todos de uma vez.
_Avoid_: repostar tudo imediatamente, duplicar tentativa sem registro, ignorar limite diario

**Limite Diario de Retropostagem**:
A quantidade maxima de **Jobs de Video** antigos que a **Retropostagem Controlada** pode enviar para um novo **Canal de Publicacao** em um dia.
_Avoid_: backlog sem limite, lote imediato, consumo invisivel de quota

**Elegibilidade para Publicacao Cruzada**:
A condicao de um **Job de Video** que ja entrou em agendamento ou publicacao em um **Canal de Publicacao** principal e pode ser publicado tambem em outro canal.
_Avoid_: pronto para upload, aprovado sem agenda, candidato ainda sem horario

**Aguardando Confirmacao de Publicacao**:
O estado operacional de um **Job de Video** cujo **Horario de Publicacao** ja venceu, mas ainda nao existe **Confirmacao de Publicacao no YouTube**.
_Avoid_: publicado presumido, falha confirmada, agenda futura

**Estado Operacional de Publicacao**:
A leitura exibida no **Hub de Revisao** que combina a aprovacao do **Job de Video** com sua agenda e confirmacao de publicacao para indicar a proxima acao real, como aprovado sem agenda, programado, publicando, falha de upload ou publicado.
_Avoid_: status bruto do job, status bruto da agenda, tag visual ambigua

**Sincronizacao Posterior de Publicacao**:
A verificacao automatica futura do estado real de publicacao no YouTube depois do horario agendado.
_Avoid_: requisito da primeira versao, marcar publicado por publishAt, avaliacao manual no Studio

**Preflight de YouTube Automatizado**:
A verificacao de que OAuth, modo API, canal e credenciais do YouTube estao prontos antes de iniciar **Publicacao Automatizada**.
_Avoid_: criar job sem poder agendar, consumir roteiro antes do OAuth, marcar agenda sem YouTube

**Ciclo Diario de Automacao**:
A execucao diaria as 02h no fuso de Sao Paulo que tenta gerar, autoaprovar e agendar um **Job de Video** para o primeiro **Dia Vago de Publicacao**.
_Avoid_: rodar sob demanda sem registro, horario do servidor, execucao concorrente

**Lock Diario de Automacao**:
A garantia de que apenas um **Ciclo Diario de Automacao** pode executar para uma data local de Sao Paulo por vez.
_Avoid_: cron concorrente, consumo duplicado de roteiro, agenda duplicada

**Pausa Global da Automacao**:
A chave operacional que impede **Publicacao Automatizada**, consumo de roteiros, criacao de jobs e upload para o YouTube enquanto estiver desligada.
_Avoid_: pausa parcial, bloquear so upload, continuar consumindo banco

**Painel de Automacao**:
A area do **Hub de Revisao** que mostra estado da automacao, ultimo ciclo, tentativas, origem do conteudo, dia vago escolhido, falhas e links de job ou YouTube.
_Avoid_: log escondido, status so no terminal, painel tecnico completo

**Registro de Automacao**:
O historico persistente dos ciclos e tentativas de **Publicacao Automatizada**, usado para lock, auditoria e exibicao no **Painel de Automacao**.
_Avoid_: arquivo solto, log apenas textual, estado so em memoria

**Janela de Preenchimento da Agenda**:
O intervalo de 14 dias futuros em que a automacao procura o primeiro **Dia Vago de Publicacao**, comecando em amanha.
_Avoid_: hoje, backlog infinito, preencher qualquer lacuna historica

**Calendario de Publicacao**:
A visao mensal do **Hub de Revisao** usada para consultar e criar **Horarios de Publicacao** por dia.
_Avoid_: agenda passiva, relatorio mensal, calendario externo

**Progresso do Job**:
A leitura operacional de onde um **Job de Video** esta no pipeline, quais etapas ja terminaram, qual etapa esta em andamento e qual proxima acao resta.
_Avoid_: log bruto, porcentagem decorativa, timeline tecnica

**Limite de Provedor**:
A recusa de um provedor em continuar uma geracao porque a conta, chave ou plano atingiu quota, credito, saldo ou rate limit.
_Avoid_: timeout, erro generico, instabilidade temporaria

**Falha Operacional do Torneio**:
Uma falha de candidato no **Torneio de LLMs** causada por limite, autenticacao, modelo indisponivel, timeout, JSON invalido, veto duro ou falha do juiz.
_Avoid_: retry invisivel, esconder instabilidade, tratar erro operacional como nota editorial

**Chave Esgotada**:
Uma chave de provedor que ja encontrou **Limite de Provedor** durante uma geracao e nao deve ser tentada novamente no mesmo **Job de Video**.
_Avoid_: chave invalida, provider offline, timeout, bloqueio diario global automatico

**Chave Dedicada de Imagem**:
Uma chave MiniMax separada para geracao de imagens, usada quando a chave primaria encontra **Limite de Provedor**.
_Avoid_: provider editorial diferente, fallback local, banco de imagens

**Planejador de Cenas**:
Um provider LLM que transforma o roteiro aprovado em plano textual de cenas, intencao visual e prompts para imagem.
_Avoid_: gerador de imagens, provider de asset visual, renderizador

**Gerador de Imagens**:
O provider que produz ou seleciona os assets visuais a partir dos prompts do **Planejador de Cenas**. Hoje, em execucao real, e MiniMax.
_Avoid_: planejador de cenas, LLM de roteiro, chave dedicada de imagem

**Trilha Aprovada**:
Uma musica de fundo instrumental previamente aceita para uso em **Jobs de Video**, sem letra ou vocal audivel, com origem e licenca conhecidas.
_Avoid_: musica aleatoria, faixa com letra, faixa com vocal, faixa baixada em runtime, trilha sem licenca

**Vocal Audivel em Trilha**:
Qualquer voz, canto, fala, sample vocal, coro ou vocalizacao perceptivel numa musica de fundo, mesmo quando a letra nao e compreensivel.
_Avoid_: apenas letra compreensivel, vocal toleravel, textura vocal

**Trilha Sintetica Local**:
Uma **Trilha Aprovada** criada pelo proprio projeto, sem amostras externas, vocal ou letra.
_Avoid_: musica baixada, faixa de catalogo, mock de teste

**Banco de Trilhas Aprovadas**:
Um estoque curado de **Trilhas Aprovadas** usado para reduzir custo, quota e risco operacional na etapa de musica de fundo.
_Avoid_: API de musica, cache de downloads, playlist sem curadoria

**Populacao Automatizada do Banco de Trilhas**:
A criacao local de **Trilhas Sinteticas Locais** para garantir que o **Banco de Trilhas Aprovadas** tenha um estoque inicial sem depender de API ou download externo.
_Avoid_: baixar catalogo automaticamente, scraping de musica, usar faixas sem revisao

**Trilha Reaproveitada de Provedor**:
Uma **Trilha Aprovada** gerada anteriormente por um provedor externo e importada de artefatos locais depois de passar por qualidade e evidencia de origem.
_Avoid_: baixar novamente do provedor, reaproveitar sem metadados, copiar audio sem licenca

**Revisao Instrumental da Trilha**:
A confirmacao humana de que uma **Trilha Reaproveitada de Provedor** nao contem **Vocal Audivel em Trilha** e pode voltar ao **Banco de Trilhas Aprovadas**.
_Avoid_: metadado inferido, confianca cega no provedor, revisao automatica suficiente

**Fallback de Musica por API**:
O uso excepcional de um provedor externo de musica quando o **Banco de Trilhas Aprovadas** nao atende ao **Job de Video**.
_Avoid_: caminho primario, fallback silencioso, mock em run real

## Relationships

- Um **Job de Video** produz zero ou um **Arquivo de Video Final**.
- Um **Job de Video** tem exatamente uma **Origem do Job**.
- Um **Job de Video** tem exatamente uma **Via de Criacao do Job**.
- A **Origem do Job** distingue criacao por **Banco de Roteiros Prontos**, **Roteiro Pronto** manual, **Tema Automatico**, tema manual e titulo manual.
- A **Via de Criacao do Job** distingue criacao pelo **Hub de Revisao**, **Ciclo Diario de Automacao**, CLI, API e recriacao derivada de outro **Job de Video**.
- Um **Job de Video** historico pode aparecer com **Origem Desconhecida do Job** quando a origem nao puder ser inferida com seguranca.
- Um **Arquivo de Video Final** pertence a exatamente um **Job de Video**.
- O **Acabamento Editorial Premium** melhora a composicao final do **Arquivo de Video Final** sem mudar o conteudo editorial aprovado.
- O **Relatorio de Decisao do Torneio** recomenda mudancas de roteamento, mas nao altera a **Configuracao Operacional do Hub** sem aprovacao humana.
- Um **Scout Competitivo de Shorts** usa **Canais de Referencia Competitiva** curados como fonte inicial antes de recorrer a busca ampla.
- Um **Scout Competitivo de Shorts** pode descobrir **Canais Candidatos de Referencia**, mas so usa esses canais como **Canais de Referencia Competitiva** depois de validacao humana.
- O **Centro de Crescimento do Canal** deve concentrar a validacao de **Canais Candidatos de Referencia** e o acompanhamento de **Canais de Referencia Competitiva**.
- Um **Scout Competitivo de Shorts** pode propor mudancas de aprendizado, mas nao altera a **Configuracao Global de Prompt Viral** sem aprovacao humana.
- Uma **Rodada de Scout Competitivo** roda com prioridade menor que criacao, revisao, publicacao e coleta de performance do canal.
- Uma **Rodada de Scout Competitivo** automatizada pode avançar coleta, sintese, experimento e promocao por thresholds, mas falha de scout nao deve bloquear o ciclo principal de criacao/publicacao.
- Um **Scout Competitivo de Shorts** deve operar dentro do nicho de curiosidades e ajudar a validar **Linhas Editoriais Sustentaveis** antes de estreitar o foco.
- Um **Scout Competitivo de Shorts** pode coletar sinais diariamente, mas deve respeitar **Maturidade de Referencia Viral** antes de tratar um short externo como vencedor.
- As linhas candidatas iniciais do **Scout Competitivo de Shorts** sao **Linha de Curiosidade Cotidiana**, **Linha de Percepcao e Corpo Leve**, **Linha de Ciencia Visual Simples**, **Linha de Tecnologia Popular** e **Linha de Natureza com Payoff Visual**.
- Um **Short Vencedor do Canal** usa retencao real do canal, enquanto um **Short de Referencia Viral** externo usa apenas proxy publico de performance.
- A primeira versao do **Scout Competitivo de Shorts** prioriza **Leitura Textual de Referencia**; **Leitura Visual de Referencia** fica para uma etapa posterior de menor custo.
- **Leitura Textual de Referencia** deve usar **Transcricao Autorizada de Referencia**; ausencia de captions em video externo nao autoriza download automatico do conteudo.
- Um **Perfil de Retencao Aprendido** orienta proximos roteiros como entrada versionada; ele nao substitui nem edita diretamente a **Configuracao Global de Prompt Viral**.
- Um **Perfil de Retencao Aprendido** deve influenciar o **Roteiro Viral Estruturado** como aprendizado estruturado, nao como nota solta de um **Job de Video**.
- Um **Perfil de Retencao Aprendido** pode reaplicar um **Esqueleto de Retencao Vencedor**, mas nao deve depender da narrativa especifica de um unico **Short de Referencia Viral**.
- Um **Esqueleto de Retencao Vencedor** pode desafiar a estrutura atual do **Roteiro Viral Estruturado** quando surge de um lote vencedor, mas deve entrar primeiro como **Aposta Agressiva de Retencao**.
- No MVP, um **Esqueleto de Retencao Vencedor** pode mudar a arquitetura narrativa interna, mas o **Roteiro Viral Estruturado** ainda deve preservar o contrato de saida esperado pelo pipeline.
- Uma **Aposta Agressiva de Retencao** pode iniciar **Experimento de Retencao Aprendida** com amostra menor, mas nao pode virar **Promocao de Perfil de Retencao** sem resultado proprio.
- Um **Conflito Editorial Experimental** pode virar diagnostico revisavel em **Experimento de Retencao Aprendida**, mas gates de factualidade, direitos, duracao, idioma e integridade tecnica continuam bloqueando.
- Um **Perfil de Retencao Aprendido** deve passar por **Experimento de Retencao Aprendida** antes de uma **Promocao de Perfil de Retencao**.
- Uma **Promocao de Perfil de Retencao** exige evidencia propria de **Shorts Vencedores do Canal**, nao apenas proxies de **Shorts de Referencia Viral**.
- Uma **Promocao de Perfil de Retencao** torna o perfil padrao versionado da linha editorial e arquiva perfis promovidos anteriores da mesma linha.
- Um **Experimento de Retencao Aprendida** deve ser avaliado dentro de uma **Linha Editorial**, nao como mudanca global do canal.
- Um **Experimento de Retencao Aprendida** com **Sucesso Forte de Retencao Aprendida** ganha prioridade para nova rodada ou promocao.
- Um **Experimento de Retencao Aprendida** com **Sucesso Parcial de Retencao Aprendida** deve ser ajustado e repetido antes de promocao.
- Views sem retencao suficiente nao caracterizam **Sucesso Forte de Retencao Aprendida**.
- Um **Scout Competitivo de Shorts** pode gerar **Propostas de Crescimento** ou **Roteiros Sugeridos por Crescimento**, mas nao cria **Jobs de Video** diretamente.
- Um **Scout Competitivo de Shorts** deve preservar metadados, metricas publicas e analise derivada de **Shorts de Referencia Viral**, nao midia externa nem roteiros externos completos.
- O **Movimento Visual de Cena** e uma parte possivel do **Acabamento Editorial Premium**, nao o acabamento inteiro.
- Uma **Prova Comparativa de Acabamento** compara versoes do mesmo **Job de Video** antes de promover uma abordagem de acabamento a padrao.
- Uma **Decisao Comparativa de Acabamento** nao substitui a **Revisao Humana** necessaria para publicar um **Job de Video**.
- Uma **Versao Premium Paralela** existe apenas para comparacao ate uma abordagem de **Acabamento Editorial Premium** virar padrao.
- Uma **Versao Premium Paralela** deve passar pelo **Gate de Acabamento Premium** antes da **Prova Comparativa de Acabamento**.
- Uma **Acao de Prova Premium** pode criar uma **Versao Premium Paralela** para um **Job de Video** especifico.
- Um **Ajuste de Timing Visual** pode fazer parte do **Acabamento Editorial Premium** quando preserva o conteudo editorial aprovado.
- O **Pacote de Acabamento Premium Inicial** limita a primeira **Prova Comparativa de Acabamento** a recursos avaliaveis e consistentes.
- Um **Plano de Acabamento Editorial** aplica **Acabamento Editorial Premium** ao conteudo aprovado de exatamente um **Job de Video**.
- Um **Plano de Acabamento Deterministico** e a forma inicial preferida de criar um **Plano de Acabamento Editorial** para manter a comparacao avaliavel.
- O **Hub de Revisao** deve tornar a **Origem do Job** visivel na fila, na revisao do job e em filtros de triagem.
- A **Origem do Job** deve aparecer em portugues no **Hub de Revisao**, sem expor identificadores internos.
- A **Via de Criacao do Job** deve ser exibida separada da **Origem do Job** para distinguir conteudo editorial de caminho operacional.
- Um **Job de Video** pode chegar a **Revisao Humana** sem estar aprovado para publicacao.
- Um **Hub de Revisao** apresenta um ou mais **Jobs de Video** para **Revisao Humana**.
- Um **Hub de Revisao** pode se apresentar como **Console Operacional**.
- Um **Console Operacional** pode conter uma **Barra Lateral Global do Hub**.
- Um **Hub de Revisao** deve organizar a tela como **Fluxo de Decisao**.
- Um **Job de Video** pode comecar a partir de um **Tema Automatico**.
- Um **Job de Video** pode comecar a partir de um **Roteiro Pronto**.
- Um **Job de Video** pode ser criado a partir de um item do **Banco de Roteiros Prontos**.
- Um **Banco de Roteiros Prontos** pode ser apresentado como **Controle Recolhido de Banco de Roteiros** na **Barra Lateral Global do Hub**.
- Uma **Configuracao Global de Prompt Viral** deve ser acessada pela **Barra Lateral Global do Hub**.
- **Roteiro Viral Estruturado** deve tratar a **Configuracao Global de Prompt Viral** como contrato de estrutura e gate, nao apenas como sugestao de estilo.
- Um **Contrato Visual do Roteiro** deriva do roteiro aprovado, nao do tema inicial isolado.
- Um **Contrato Visual do Roteiro** orienta a **Imagem de Hook Visual** sem reescrever o roteiro aprovado.
- O **Planejador de Cenas** deve respeitar o **Contrato Visual do Roteiro** ao produzir o **Plano de Cenas**.
- Um **Plano de Cenas** deve atribuir **Intencao Visual** coerente com o **Contrato Visual do Roteiro**.
- Um **Plano de Cenas** deve passar por validacao antes de orientar o **Gerador de Imagens**.
- Uma **Especificacao Visual da Cena** deve ser concreta o bastante para o **Gerador de Imagens** produzir o objeto certo, nao apenas o clima da cena.
- Um asset visual deve passar por **Validacao Visual de Asset** antes de sustentar a **Elegibilidade Automatizada**.
- A **Imagem de Hook Visual** deve ser avaliada pela **Validacao Visual de Asset** com mais rigor que cenas intermediarias.
- **Janela Alvo de Duracao do Short** deve orientar roteiro, TTS e render de **Jobs de Video** automaticos.
- Um **Perfil de Narrador** deve combinar com a **Direcao de Voz** e com o tipo de roteiro, sem alterar a narracao aprovada.
- Uma **Barra Lateral Global do Hub** pode exibir **Status Compacto da Automacao**.
- **Status Compacto da Automacao** pode alternar a **Pausa Global da Automacao**.
- **Status Compacto da Automacao** nao deve iniciar um **Ciclo Diario de Automacao**.
- **Status Compacto da Automacao** deve limitar-se a estado, estoque de roteiros e horario do ciclo diario.
- **Painel de Automacao** deve manter ultimo ciclo, tentativas, erros e links fora da **Barra Lateral Global do Hub**.
- Acoes auxiliares feitas pela **Barra Lateral Global do Hub** devem preservar a tela atual do **Console Operacional**.
- Um **Lote de Roteiros Prontos** pode alimentar o **Banco de Roteiros Prontos** por arquivo ou por texto colado, usando somente **Texto Rotulado** na versao inicial.
- Um **Lote de Roteiros Prontos** pode ser enviado pela **Barra Lateral Global do Hub**.
- Um item do **Banco de Roteiros Prontos** deve preservar a intencao autoral do **Roteiro Pronto** consumido.
- **Ciclo Diario de Automacao** deve priorizar o **Banco de Roteiros Prontos** antes de usar **Tema Automatico**.
- O **Banco de Roteiros Prontos** deve usar **Selecao Aleatoria de Roteiro** entre itens disponiveis.
- **Similaridade Narrativa** em item do **Banco de Roteiros Prontos** deve virar warning, nao fallback.
- **Fallback para Tema Automatico** deve ocorrer somente quando nao houver **Roteiro Pronto** disponivel no ciclo atual.
- Um item do **Banco de Roteiros Prontos** que gerar uma tentativa deve virar **Roteiro Pronto Consumido**, mesmo quando o **Job de Video** nao for publicado automaticamente.
- Um **Job de Video** criado a partir de **Roteiro Pronto Consumido** que falha em etapa tecnica deve usar **Recuperacao Dirigida do Job**, nao retorno automatico ao banco.
- Um **Roteiro Pronto** deve ser enviado como **Texto Rotulado**.
- Um **Roteiro Pronto** deve conter **Loop Editorial** entre hook e beats.
- Um **Roteiro Pronto** pode conter **Fatos Declarados**.
- **Fatos Declarados** dependem de **Confirmacao de Factualidade**.
- Um item do **Banco de Roteiros Prontos** possui **Validacao Humana de Roteiro Pronto**.
- Um **Lote de Roteiros Prontos** pode entrar em **Publicacao Automatizada** quando houver **Confirmacao Factual por Lote**.
- Um **Lote de Roteiros Prontos** gerado por IA nao tem **Confirmacao Factual por Lote** automaticamente.
- **Loop Editorial** nao e **Fato Declarado** por si so.
- O **Hub de Revisao** oferece **Roteiro Pronto** como modo de entrada distinto de tema e titulo.
- Um **Horario de Publicacao** so deve ser escolhido depois da aprovacao do **Job de Video**.
- **Publicacao Automatizada** pode aprovar, agendar e publicar um **Job de Video** sem **Revisao Humana** previa quando os criterios de score e bloqueio forem satisfeitos.
- **Elegibilidade Automatizada** exige status `ready_for_upload`; **Jobs de Video** em `monetization_review` ou `blocked_for_monetization` nao podem entrar em **Publicacao Automatizada**.
- **Tema Automatico** pode chegar a **Publicacao Automatizada**, mas nao possui **Validacao Humana de Roteiro Pronto** e deve passar pelo caminho rigoroso de factualidade, auditoria textual, metadados, repeticao, visual, direitos, disclosure, duracao, audio, render e YouTube.
- **Validacao Humana de Roteiro Pronto** transforma bloqueios editoriais automatizados em warnings, mas nao dispensa etapas tecnicas, visuais, direitos, disclosure, duracao, audio, render ou YouTube.
- **Tema Amplo** pode se repetir em varios **Jobs de Video** quando a **Similaridade Narrativa** for baixa.
- **Similaridade Narrativa** alta deve bloquear **Publicacao Automatizada** para evitar conteudo massivo ou repetitivo.
- **Risco Medio de Repeticao** deve reduzir o score, mas nao bloquear sozinho a **Publicacao Automatizada**.
- **Risco Alto de Repeticao** deve bloquear **Publicacao Automatizada**.
- **Score de Autoaprovacao** deve exigir monetizacao aprovada, factualidade minima de 0.80 quando existir, retencao minima de 0.75 quando existir, metadados minimos de 0.75 quando existirem, alinhamento semantico medio de assets de 0.80 quando houver assets e pontuacao composta minima de 0.82.
- **Risco Medio de Repeticao** deve aplicar penalidade de 0.10 no **Score de Autoaprovacao**.
- **Score de Autoaprovacao** deve virar **Score Diagnostico de Roteiro Pronto** para **Jobs de Video** criados pelo **Banco de Roteiros Prontos**.
- **Score Diagnostico de Roteiro Pronto** nao deve bloquear **Publicacao Automatizada** quando o job estiver tecnicamente pronto.
- **Tentativa Automatizada Sem Publicacao** consome uma tentativa da **Cadencia Diaria de Geracao** e permanece disponivel no **Hub de Revisao** para avaliacao manual.
- **Retomada de Publicacao Automatizada** deve reutilizar o mesmo **Job de Video** quando ele ja atingiu **Elegibilidade Automatizada** e a falha ocorreu antes da confirmacao do YouTube.
- **Limite de Retomada de Publicacao** deve parar a retomada automatica apos tres falhas de upload ou agendamento do mesmo **Job de Video**.
- **Avaliacao Posterior no YouTube Studio** nao substitui **Revisao Humana**; ela e uma etapa posterior para auditar o que ja foi publicado automaticamente.
- **Cadencia Diaria de Geracao** deve limitar a criacao automatica inicial a ate tres **Jobs de Video** por dia quando tentativas anteriores falham ou nao atingem **Elegibilidade Automatizada**.
- **Primeiro Sucesso Automatizado** encerra a **Cadencia Diaria de Geracao** do dia.
- **Dia Vago de Publicacao** deve ser identificado pela agenda interna, nao pela leitura externa do YouTube Studio.
- **Horario Padrao de Publicacao** ocorre sempre as 11h no fuso de Sao Paulo.
- **Publicacao Automatizada** deve usar **Agendamento Nativo do YouTube** para o **Horario Padrao de Publicacao** do **Dia Vago de Publicacao**.
- **Agendamento Nativo do YouTube** nao deve marcar um **Job de Video** como publicado sem **Confirmacao de Publicacao no YouTube**.
- **Sincronizacao Posterior de Publicacao** fica fora da primeira versao da **Publicacao Automatizada**.
- **Preflight de YouTube Automatizado** deve passar antes de criar **Jobs de Video** ou consumir **Roteiros Prontos** em um ciclo automatico.
- **Ciclo Diario de Automacao** deve rodar as 02h no fuso de Sao Paulo.
- **Lock Diario de Automacao** deve impedir ciclos concorrentes para a mesma data local.
- **Pausa Global da Automacao** deve ser verificada antes de criar **Jobs de Video**, consumir itens do **Banco de Roteiros Prontos** ou chamar o YouTube.
- **Painel de Automacao** deve expor quando o ciclo foi pulado, falhou, esta rodando ou conseguiu agendar uma publicacao.
- O **Banco de Roteiros Prontos** e o **Registro de Automacao** devem ser persistidos no banco do app para suportar selecao, consumo, lock e auditoria.
- **Janela de Preenchimento da Agenda** deve comecar em amanha, cobrir 14 dias e evitar publicacao automatica no mesmo dia.
- Um **Calendario de Publicacao** pode criar um **Horario de Publicacao** para um **Job de Video** aprovado, desde que ele ainda nao esteja publicado nem tenha agenda ativa.
- Um **Hub de Revisao** deve exibir o **Progresso do Job** sem exigir leitura de logs ou artefatos tecnicos.
- **Limite de Provedor** deve ser distinguido de falha transiente antes de trocar a origem da geracao.
- Uma **Chave Esgotada** deve ser evitada pelo restante do **Job de Video** em andamento.
- **Chave Dedicada de Imagem** deve ser usada depois que a chave primaria de imagem vira **Chave Esgotada**.
- Um **Job de Video** pode usar zero ou uma **Trilha Aprovada**.
- Um **Banco de Trilhas Aprovadas** pode conter uma ou mais **Trilhas Aprovadas**.
- Uma **Trilha Aprovada** deve ser instrumental e nao pode conter letra ou vocal audivel.
- **Vocal Audivel em Trilha** invalida uma **Trilha Aprovada**, mesmo quando nao houver letra compreensivel.
- Uma **Trilha Sintetica Local** pode entrar no **Banco de Trilhas Aprovadas** sem licenca externa porque nao usa material de terceiros.
- Uma **Trilha Reaproveitada de Provedor** deve preservar job original, provedor, licenca e evidencia de qualidade.
- Uma **Trilha Reaproveitada de Provedor** exige **Revisao Instrumental da Trilha** antes de ser usada novamente em **Jobs de Video**.
- Uma **Trilha Aprovada** deve ter origem e licenca rastreaveis antes de entrar em um **Job de Video**.
- **Populacao Automatizada do Banco de Trilhas** deve criar trilhas locais, nao baixar musicas de catalogos externos.
- **Fallback de Musica por API** nao deve ocorrer sem configuracao explicita.
- Uma **Proposta de Crescimento** pode produzir um **Roteiro Sugerido por Crescimento**.
- Um **Roteiro Sugerido por Crescimento** exige revisao humana antes de entrar no **Banco de Roteiros Prontos** ou virar **Job de Video**.
- Uma **Proposta de Crescimento** nao deve criar **Job de Video** diretamente.

## Example dialogue

> **Dev:** "Quando voce pede para gerar um video, quer apenas o arquivo de video final?"
> **Domain expert:** "Nao. Quero um Job de Video completo, com arquivo final, estado terminal e sinais suficientes para revisar publicacao."
> **Dev:** "Se o job chegou em revisao, isso significa que ja pode publicar?"
> **Domain expert:** "Nao. Revisao Humana e a fronteira para eu assistir e decidir; publicacao vem depois."
> **Dev:** "Hub significa qualquer servidor aberto localmente?"
> **Domain expert:** "Nao. Hub de Revisao e a superficie unica onde acompanho os jobs; portas duplicadas sao detalhe operacional e devem ser evitadas."
> **Dev:** "A home deve mostrar todos os blocos tecnicos antes das acoes?"
> **Domain expert:** "Nao. Fluxo de Decisao vem primeiro: criar, revisar, aprovar, agendar; diagnosticos ficam depois."
> **Dev:** "Console operacional quer dizer uma tela clara com graficos bonitos?"
> **Domain expert:** "Nao. Console Operacional quer dizer fila, estado e proxima acao em primeiro plano; o modo escuro e o padrao visual escolhido para essa superficie."
> **Dev:** "Quando voce fala sidebar, quer dizer a coluna lateral do formulario de criacao?"
> **Domain expert:** "Nao. Quero a Barra Lateral Global do Hub, onde ficam identidade do console, navegacao e configuracoes recorrentes."
> **Dev:** "Sem tema explicito, posso escolher qualquer assunto do pool local?"
> **Domain expert:** "Nao. Use Tema Automatico, com preferencia por tendencia real e rastreabilidade."
> **Dev:** "Se eu mando titulo, hook, beats, payoff e fechamento, isso e so um prompt?"
> **Domain expert:** "Nao. Isso e um Roteiro Pronto; o sistema deve preservar a intencao editorial e nao tratar como tema bruto."
> **Dev:** "Se houver varios roteiros prontos guardados, a automacao pode escolher um?"
> **Domain expert:** "Sim. O Banco de Roteiros Prontos e uma fonte de entrada para criar Jobs de Video sem regenerar pauta ou roteiro."
> **Dev:** "A automacao deve consumir na ordem em que eu colei?"
> **Domain expert:** "Nao. Use Selecao Aleatoria de Roteiro, mas filtre Similaridade Narrativa para nao repetir historia ou roteiro."
> **Dev:** "Se um roteiro foi pulado por estar parecido com a agenda atual, ele foi consumido?"
> **Domain expert:** "Nao. Ele vira Roteiro Pulado por Similaridade naquela execucao e pode ser usado no futuro."
> **Dev:** "Se todos os roteiros disponiveis estiverem parecidos demais, paro o ciclo?"
> **Domain expert:** "Nao. Use Fallback para Tema Automatico para tentar preencher o dia vago."
> **Dev:** "Como voce vai enviar varios roteiros?"
> **Domain expert:** "Como Lote de Roteiros Prontos, por arquivo ou copiar/colar, mantendo os rotulos Titulo, Hook, Loop, Beats, Payoff, Fechamento e Hashtags, sem CSV ou JSON inicialmente."
> **Dev:** "Se um roteiro pronto falha no score, tento o mesmo roteiro amanha?"
> **Domain expert:** "Nao automaticamente. Ele vira Roteiro Pronto Consumido e fica para revisao."
> **Dev:** "Loop e mais um fato que preciso rastrear?"
> **Domain expert:** "Nao. Loop Editorial e tensao narrativa. Os fatos declarados ficam nos beats e no payoff."
> **Dev:** "O gerador pode trocar a ideia central do roteiro para melhorar retencao?"
> **Domain expert:** "Nao. Roteiro Pronto e fonte de verdade editorial; o texto enviado deve ser preservado."
> **Dev:** "Se o roteiro pronto vier com problema mecanico, o job deve falhar direto?"
> **Domain expert:** "Sim, se o problema impedir o pipeline; nao reescreva automaticamente o roteiro pronto."
> **Dev:** "Posso mandar esse roteiro pronto em JSON?"
> **Domain expert:** "Nao por enquanto. O formato canonico e Texto Rotulado."
> **Dev:** "Se o roteiro pronto traz numeros factuais, o app precisa refazer toda a checagem?"
> **Domain expert:** "Nao. Esses numeros entram como Fatos Declarados quando eu assumo que ja revisei o roteiro antes de enviar."
> **Dev:** "Se o lote foi feito por IA, os fatos ja estao confirmados?"
> **Domain expert:** "Nao automaticamente. A Confirmacao Factual por Lote acontece quando eu assumo explicitamente a factualidade do lote."
> **Dev:** "Essa confirmacao quer dizer que o job ja esta aprovado para publicar?"
> **Domain expert:** "Nao. Confirmacao de Factualidade cobre os fatos declarados; Revisao Humana ainda decide publicacao."
> **Dev:** "Posso colocar roteiro pronto no mesmo campo de tema?"
> **Domain expert:** "Nao. Roteiro Pronto e um modo de entrada proprio no Hub de Revisao."
> **Dev:** "O LLM deve gerar outro roteiro a partir do roteiro pronto?"
> **Domain expert:** "Nao. Roteiro Pronto pula a geracao de roteiro por LLM; o texto enviado e a fonte de verdade."
> **Dev:** "Se o roteiro pronto estiver muito curto ou muito longo, posso completar ou cortar livremente?"
> **Domain expert:** "Nao. Ajuste apenas desvios pequenos; desvios grandes devem bloquear antes da midia."
> **Dev:** "O titulo do roteiro pronto deve ser narrado?"
> **Domain expert:** "Nao. O titulo e metadado; a narracao comeca no hook e segue ate o fechamento."
> **Dev:** "Se o roteiro pronto nao trouxer hashtags, isso bloqueia o job?"
> **Domain expert:** "Nao. Hashtags sao metadados e podem ser completadas automaticamente sem alterar o roteiro."
> **Dev:** "Data e hora no job e um timestamp tecnico?"
> **Domain expert:** "Nao. E o Horario de Publicacao: a escolha humana de quando o Short aprovado deve ir ao YouTube."
> **Dev:** "Se a meta e automacao total, ainda preciso assistir no hub antes de publicar?"
> **Domain expert:** "Nao. Na Publicacao Automatizada, o sistema pode aprovar, agendar e publicar se os scores passarem; minha revisao vem depois no YouTube Studio."
> **Dev:** "Posso publicar automaticamente um job em monetization_review?"
> **Domain expert:** "Nao. Elegibilidade Automatizada exige ready_for_upload; monetization_review e blocked_for_monetization ficam fora da automacao."
> **Dev:** "Se dois jobs forem sobre tecnologia, isso ja e repeticao?"
> **Domain expert:** "Nao. Tema Amplo pode repetir; o bloqueio e Similaridade Narrativa alta entre roteiro, historia, hook, virada ou payoff."
> **Dev:** "Risco medio de repeticao impede publicar?"
> **Domain expert:** "Nao sozinho. Risco Medio de Repeticao reduz o score; Risco Alto de Repeticao bloqueia a Publicacao Automatizada."
> **Dev:** "Se o job passou no gate final, ja publica automaticamente?"
> **Domain expert:** "So se tambem atingir o Score de Autoaprovacao minimo, incluindo factualidade, retencao, metadados, assets e repeticao."
> **Dev:** "Se o job fica ready_for_upload mas nao bate o score, rejeito automaticamente?"
> **Domain expert:** "Nao. Ele vira Tentativa Automatizada Sem Publicacao, consome tentativa diaria e fica no Hub de Revisao."
> **Dev:** "Se o job ja passou no score, mas o upload ou agendamento falhou, gero outro?"
> **Domain expert:** "Nao. Use Retomada de Publicacao Automatizada para tentar publicar o mesmo Job de Video antes de criar outro."
> **Dev:** "E se o mesmo job falhar varias vezes no YouTube?"
> **Domain expert:** "Use Limite de Retomada de Publicacao: tres falhas param a retomada automatica e deixam acao manual no hub."
> **Dev:** "Posso gerar dez jobs de uma vez para encher o calendario?"
> **Domain expert:** "Nao no inicio. Use Cadencia Diaria de Geracao para tentar ate tres jobs por dia quando os anteriores falham ou nao atingem elegibilidade."
> **Dev:** "Se o primeiro job ja preencheu a agenda, continuo gerando os outros dois?"
> **Domain expert:** "Nao. Primeiro Sucesso Automatizado encerra as tentativas do dia."
> **Dev:** "Dia vago deve olhar o YouTube Studio?"
> **Domain expert:** "Nao. Dia Vago de Publicacao e definido pela agenda interna do hub, sempre preenchido as 11h no fuso de Sao Paulo."
> **Dev:** "O cron precisa estar rodando exatamente as 11h para publicar?"
> **Domain expert:** "Nao. A automacao deve usar Agendamento Nativo do YouTube, enviando antes e configurando publishAt para o dia vago as 11h."
> **Dev:** "Depois que o YouTube aceitou publishAt, o job ja esta publicado?"
> **Domain expert:** "Nao. Ele esta agendado; publicado exige Confirmacao de Publicacao no YouTube."
> **Dev:** "A primeira versao precisa consultar depois se o YouTube publicou?"
> **Domain expert:** "Nao. Sincronizacao Posterior de Publicacao fica para depois; nesta versao basta registrar o agendamento nativo e avaliar no YouTube Studio."
> **Dev:** "Se o YouTube OAuth caiu, ainda gero o video para agendar depois?"
> **Domain expert:** "Nao. Preflight de YouTube Automatizado deve passar antes de criar job ou consumir roteiro."
> **Dev:** "Quando a automacao deve gerar os videos?"
> **Domain expert:** "O Ciclo Diario de Automacao roda as 02h no fuso de Sao Paulo."
> **Dev:** "Se o cron disparar duas vezes no mesmo dia?"
> **Domain expert:** "O Lock Diario de Automacao impede execucoes concorrentes e duplicacao de agenda."
> **Dev:** "Se eu desligar a automacao, ela ainda pode consumir roteiro ou gerar job?"
> **Domain expert:** "Nao. Pausa Global da Automacao bloqueia criacao, consumo de roteiro e upload."
> **Dev:** "Se a automacao nao publicou hoje, onde vejo o motivo?"
> **Domain expert:** "No Painel de Automacao do Hub de Revisao, com ultimo ciclo, tentativas, falhas, origem do conteudo e links relevantes."
> **Dev:** "O banco de roteiros e os ciclos podem ficar em arquivo solto?"
> **Domain expert:** "Nao. Banco de Roteiros Prontos e Registro de Automacao ficam no banco do app para lock, auditoria e painel."
> **Dev:** "Se hoje ainda esta antes das 11h, posso preencher hoje?"
> **Domain expert:** "Nao. A Janela de Preenchimento da Agenda comeca em amanha para manter folga operacional."
> **Dev:** "O calendario serve apenas para ver os jobs ja agendados?"
> **Domain expert:** "Nao. O Calendario de Publicacao tambem deve permitir criar Horario de Publicacao no dia escolhido para jobs aprovados e ainda livres para agendar."
> **Dev:** "Progresso quer dizer mostrar todos os logs do worker?"
> **Domain expert:** "Nao. Progresso do Job e uma leitura resumida das etapas reais: concluido, rodando, pendente ou falhou."
> **Dev:** "Timeout da MiniMax conta como limite de uso?"
> **Domain expert:** "Nao. Limite de Provedor e quota, saldo, credito ou rate limit; timeout e falha transiente."
> **Dev:** "Se a chave bateu quota em uma imagem, tento de novo na proxima cena?"
> **Domain expert:** "Nao. Marque como Chave Esgotada para o restante do Job de Video e use a alternativa dedicada."
> **Dev:** "A chave dedicada muda o fornecedor editorial da imagem?"
> **Domain expert:** "Nao. Continua sendo MiniMax; a Chave Dedicada de Imagem so muda a credencial usada depois de limite."
> **Dev:** "Para cada job real, preciso gerar musica nova por API?"
> **Domain expert:** "Nao. Use uma Trilha Aprovada do Banco de Trilhas Aprovadas; API de musica e fallback explicito, nao caminho padrao."
> **Dev:** "Posso popular automaticamente baixando musicas royalty-free da internet?"
> **Domain expert:** "Nao como padrao. A Populacao Automatizada do Banco de Trilhas cria Trilhas Sinteticas Locais; catalogos externos exigem curadoria e evidencia."
> **Dev:** "E as musicas que a MiniMax ja gerou?"
> **Domain expert:** "Podem virar Trilha Reaproveitada de Provedor se o artifact local tiver licenca, job original e quality gate aprovado."

## Flagged ambiguities

- "video" foi usado tanto para o arquivo final quanto para o fluxo completo de criacao; resolvido: em pedidos operacionais, use **Job de Video**.
- "pronto" foi usado tanto para pronto para assistir quanto para pronto para publicar; resolvido: neste fluxo, sucesso significa pronto para **Revisao Humana**.
- "hub" foi usado para falar tanto da superficie de revisao quanto de portas locais; resolvido: use **Hub de Revisao** para a superficie, e mantenha uma unica porta operacional.
- "amigavel" nao significa apenas visual bonito; resolvido: o **Hub de Revisao** deve seguir um **Fluxo de Decisao**.
- "dark mode" nao significa tema alternavel por usuario neste momento; resolvido: e o padrao visual do **Console Operacional**.
- "tema automatico" nao significa escolha aleatoria; resolvido: o sistema deve preferir tendencia real e expor quando caiu em fallback.
- "roteiro pronto" nao significa prompt livre; resolvido: e conteudo editorial estruturado fornecido por uma pessoa e tratado como fonte de verdade.
- "banco de roteiros" nao significa backlog de temas; resolvido: use **Banco de Roteiros Prontos** para armazenar textos autorais prontos para consumo pela automacao.
- "aleatorio" nao significa que o sistema pode ignorar o banco; resolvido: use **Selecao Aleatoria de Roteiro** entre itens disponiveis do **Banco de Roteiros Prontos**.
- "pulado por similaridade" nao deve ser comportamento ativo do banco; resolvido: **Similaridade Narrativa** em roteiro do banco vira warning.
- "banco saturado" nao significa fallback automatico; resolvido: use **Fallback para Tema Automatico** somente quando nao houver item disponivel no banco.
- "colar em lote" nao significa texto livre sem contrato; resolvido: use **Lote de Roteiros Prontos** com os mesmos rotulos canonicos de **Texto Rotulado**.
- "consumir roteiro" nao significa publicar obrigatoriamente; resolvido: um **Roteiro Pronto Consumido** pode virar tentativa sem publicacao e deve ser recuperado pelo **Job de Video**, nao retentado automaticamente pelo banco.
- "loop" em **Roteiro Pronto** nao significa claim factual; resolvido: use **Loop Editorial** como tensao de retencao entre hook e beats.
- "reparar automaticamente" nao se aplica ao texto de **Roteiro Pronto**; resolvido: se o texto pronto tiver problema que bloqueia o pipeline, bloqueie e exponha o motivo em vez de reescrever hook, beats, payoff ou fechamento.
- "texto rotulado" nao significa JSON nem markdown livre; resolvido: o formato canonico inicial usa rotulos editoriais em texto simples.
- "confiar em mim" nao significa que o fato foi verificado automaticamente pelo app; resolvido: fatos do **Roteiro Pronto** entram como **Fatos Declarados** sob responsabilidade de quem enviou.
- "feito por IA" nao significa fato confirmado; resolvido: use **Confirmacao Factual por Lote** quando uma pessoa assume explicitamente a factualidade do lote.
- "confirmacao de factualidade" nao significa aprovacao de publicacao; resolvido: ela cobre a responsabilidade factual do **Roteiro Pronto**.
- "pular geracao por LLM" nao significa pular validacao tecnica; resolvido: **Roteiro Pronto** preserva o texto enviado, sinais editoriais automatizados viram warnings e problemas tecnicos ou visuais ainda podem bloquear.
- "ajustar duracao" nao significa expandir ou cortar livremente; resolvido: desvios pequenos podem ser reparados, desvios grandes bloqueiam antes da midia.
- "titulo" em **Roteiro Pronto** nao significa fala narrada; resolvido: titulo e metadado, enquanto hook, beats, payoff e fechamento formam a narracao.
- "hashtags" em **Roteiro Pronto** nao sao fonte de verdade narrativa; resolvido: podem ser derivadas automaticamente como metadados.
- "data e hora" em agendamento nao significa horario do servidor; resolvido: use **Horario de Publicacao**, com fuso explicito.
- "auto aprovar" nao significa ignorar criterios; resolvido: use **Publicacao Automatizada**, com scores explicitos, bloqueios e auditoria posterior.
- "automacao total" nao significa publicar jobs em revisao; resolvido: use **Elegibilidade Automatizada** restrita a `ready_for_upload`.
- "tema automatico" nao significa caminho leve de publicacao; resolvido: **Tema Automatico** tambem pode autopublicar, mas somente quando passar pelo caminho rigoroso da **Elegibilidade Automatizada**.
- "score baixo" em roteiro do banco nao significa veto; resolvido: use **Score Diagnostico de Roteiro Pronto** como informacao, preservando a **Validacao Humana de Roteiro Pronto**.
- "sem repetir" nao significa banir roteiro validado do banco; resolvido: permita **Banco de Roteiros Prontos** recorrente com warning de **Similaridade Narrativa**.
- "similaridade media" nao significa bloqueio imediato; resolvido: use **Risco Medio de Repeticao** como penalidade e **Risco Alto de Repeticao** como bloqueio.
- "score" nao significa uma nota opaca; resolvido: use **Score de Autoaprovacao** com criterios minimos explicitos e score composto minimo de 0.82.
- "nao passou no score" nao significa rejeicao automatica; resolvido: vira **Tentativa Automatizada Sem Publicacao** e permanece revisavel.
- "falha depois do score" nao significa criar outro job; resolvido: use **Retomada de Publicacao Automatizada** para reutilizar o job elegivel.
- "retomar publicacao" nao significa retry infinito; resolvido: use **Limite de Retomada de Publicacao** de tres falhas por job elegivel.
- "avaliacao humana no YouTube Studio" nao significa **Revisao Humana** previa no hub; resolvido: use **Avaliacao Posterior no YouTube Studio**.
- "cronjob diario" nao significa gerar backlog grande; resolvido: use **Cadencia Diaria de Geracao** com limite inicial de ate tres jobs por dia se as tentativas anteriores falharem.
- "tres videos por dia" nao significa publicar tres se o primeiro funcionar; resolvido: **Primeiro Sucesso Automatizado** para novas tentativas.
- "dia vago" nao significa consultar o YouTube Studio; resolvido: use **Dia Vago de Publicacao** baseado na agenda interna.
- "todo dia as 11h" nao significa horario local do servidor; resolvido: use **Horario Padrao de Publicacao** no fuso de Sao Paulo.
- "publicar as 11h" nao significa depender do worker nesse horario; resolvido: use **Agendamento Nativo do YouTube**.
- "agendado no YouTube" nao significa publicado; resolvido: use **Confirmacao de Publicacao no YouTube** antes de marcar `published`.
- "confirmar publicacao no YouTube" nao e requisito inicial; resolvido: **Sincronizacao Posterior de Publicacao** fica fora da primeira versao.
- "falha no YouTube" nao significa criar backlog automatico; resolvido: **Preflight de YouTube Automatizado** falha cedo antes de criar job ou consumir roteiro.
- "cron diario" nao significa horario UTC nem execucao concorrente livre; resolvido: use **Ciclo Diario de Automacao** as 02h no fuso de Sao Paulo.
- "cron duplicado" nao significa duas tentativas independentes; resolvido: use **Lock Diario de Automacao** por data local de Sao Paulo.
- "pausar automacao" nao significa apenas parar upload; resolvido: **Pausa Global da Automacao** bloqueia criacao, consumo de roteiro e chamadas ao YouTube.
- "status da automacao" nao deve ficar apenas em log ou terminal; resolvido: use **Painel de Automacao** no **Hub de Revisao**.
- "historico da automacao" nao deve ser arquivo solto; resolvido: use **Registro de Automacao** persistido no banco do app.
- "preencher dia vago" nao significa publicar hoje se ainda houver tempo; resolvido: use **Janela de Preenchimento da Agenda** com inicio em amanha.
- "calendario" nao significa visualizacao passiva; resolvido: o **Calendario de Publicacao** tambem e ponto de entrada para agendar jobs aprovados por dia.
- "progresso" nao significa percentual inventado nem log bruto; resolvido: derive o **Progresso do Job** das etapas reais, execucoes persistidas e estado atual do job.
- "limite" de provedor nao significa qualquer falha de API; resolvido: use **Limite de Provedor** apenas para quota, saldo, credito ou rate limit.
- "esgotada" nao significa que a chave foi revogada nem que todo job futuro deve bloquear a chave; resolvido: **Chave Esgotada** vale para evitar novas tentativas no job atual apos quota ou rate limit.
- "fallback de imagem" nao significa provider editorial diferente neste caso; resolvido: use **Chave Dedicada de Imagem** para a credencial MiniMax alternativa.
- "musica de fundo" nao significa gerar faixa nova por API em todo job; resolvido: use **Banco de Trilhas Aprovadas** como caminho primario.
- "royalty-free" nao significa seguro sem evidencia; resolvido: uma **Trilha Aprovada** precisa de origem e licenca rastreaveis.
- "popular automaticamente" nao significa baixar musicas da internet; resolvido: use **Populacao Automatizada do Banco de Trilhas** com **Trilhas Sinteticas Locais**.
- "reaproveitar MiniMax" nao significa chamar MiniMax de novo nem guardar URL assinada; resolvido: importe o audio local como **Trilha Reaproveitada de Provedor** com evidencia.
- "fallback de musica" nao significa voltar silenciosamente para MiniMax; resolvido: **Fallback de Musica por API** exige configuracao explicita.
