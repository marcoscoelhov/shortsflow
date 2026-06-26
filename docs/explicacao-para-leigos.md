# Explicacao para leigos

O ShortsFlow e uma pequena fabrica automatizada de videos curtos para YouTube Shorts.

Em vez de uma pessoa fazer tudo manualmente, o operador entrega uma ideia, um titulo ou um roteiro pronto. O app transforma isso em um video vertical completo, mostra o resultado em uma pagina de revisao e ajuda a agendar ou publicar no canal.

## O que ele faz, em palavras simples

Imagine uma linha de producao:

1. **Recebe uma ideia**: por exemplo, "por que o gelo estala no copo?".
2. **Organiza a pauta**: decide qual e a promessa do video, o angulo e os pontos principais.
3. **Escreve ou preserva o roteiro**: cria um roteiro curto ou usa um roteiro pronto fornecido por uma pessoa.
4. **Checa se o roteiro e seguro**: procura idioma errado, frases quebradas, tom muito didatico, claims factuais arriscados e problemas de monetizacao.
5. **Planeja as imagens**: divide o roteiro em cenas e define como cada cena deve parecer.
6. **Gera ou seleciona imagens**: cria prompts visuais verticais, sem texto na imagem, com foco no primeiro segundo do Short.
7. **Cria a narracao**: gera voz em portugues brasileiro.
8. **Alinha legendas e musica**: prepara legenda, trilha e audio final.
9. **Renderiza o video**: monta o MP4 vertical final, hoje principalmente com Remotion.
10. **Faz uma revisao de publicacao**: junta direitos, factualidade, visual, repeticao, metadados e riscos.
11. **Mostra tudo no Hub**: uma pessoa assiste, aprova, agenda ou publica.

## O que o app nao tenta ser

- Nao e apenas um editor de video.
- Nao e apenas um gerador de roteiro.
- Nao publica automaticamente qualquer coisa sem gates.
- Nao deve inventar fatos para preencher lacunas.
- Nao deve usar Wikipedia como fonte factual confiavel para claims sensiveis.

## Por que existem tantos gates

Shorts virais precisam prender atencao, mas tambem precisam ser seguros para publicar. Por isso o app separa tres perguntas:

- **E interessante?** O hook para o scroll? Existe loop de curiosidade? O payoff compensa?
- **E verdadeiro o suficiente?** Claims especificos, medicos, financeiros, historicos, tecnicos ou perigosos precisam de fonte ou linguagem conservadora.
- **E publicavel?** O video tem direitos, audio aceitavel, imagem coerente, metadados e revisao visual suficientes?

Quando algo fica em duvida, o job vai para revisao humana ou bloqueio, em vez de ser publicado no escuro.

## Como funciona a revisao visual automatica

Alguns jobs chegam quase prontos, mas ainda precisam confirmar se a imagem gerada realmente mostra o que o roteiro promete. O app pode rodar uma revisao visual auxiliar.

Se a unica pendencia era visual, essa revisao pode liberar o job para aprovacao. Se tambem sobra uma pendencia factual ou editorial, o app registra que a parte visual foi resolvida, mas nao publica aquele job automaticamente. Nesse caso, o ciclo diario tenta o proximo job elegivel para nao desperdicancar o slot de publicacao.

## Como funciona o ciclo diario

O ciclo diario tenta preencher a agenda do canal sem depender de alguem clicando manualmente todo dia.

Ele olha para slots futuros, tenta usar primeiro jobs prontos do backlog, pode gerar novos jobs quando precisa e so agenda automaticamente quando os gates tecnicos passam. O slot do Banco de Roteiros Prontos e separado do slot de Tema Automatico, para nao misturar origens editoriais.

## Resultado final

No final, o operador tem:

- um video vertical pronto (`render/final.mp4`),
- titulo, descricao e hashtags,
- relatorios de qualidade,
- historico de etapas,
- estado de revisao,
- agenda de publicacao,
- e, quando conectado, upload via YouTube API.

Em resumo: o app pega uma ideia de Short, transforma em pacote publicavel e coloca uma pessoa no ponto certo da decisao: revisar, aprovar e publicar.
