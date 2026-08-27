# Contrato de runtime remoto do ShortsFlow

## Objetivo

GitHub é a fonte de verdade do código. A VPS guarda secrets, SQLite e mídia.
Computadores locais editam código e rodam testes baratos com mocks. Jobs reais
de render, providers, mídia e E2E pesado executam na VPS. Nunca commitar `.env`,
banco ou artefatos gerados.

Este contrato descreve um operador solo. Staging testa e auto-implanta.
Produção só sobe quando o humano decide, uma vez.

## Ambientes

| Ambiente | Branch | Estado | Carga |
| --- | --- | --- | --- |
| Local | branch de trabalho | sem secrets ou mídia persistente | lint e testes rápidos / mocks |
| Staging | `staging` | SQLite e artifacts isolados | providers reais, jobs explícitos |
| Produção | `main` | estado operacional existente | jobs reais e automações |

Staging e produção devem informar ambiente, revisão implantada, drenagem e
capacidade pelo health check. Os dois usam uma única instância de visão local e
um único slot global para jobs pesados. Produção tem prioridade para o próximo
slot disponível; um job de staging já iniciado nunca é interrompido.

O app escuta só em `127.0.0.1`. Não abrir portas públicas extras. Não bindar o
app fora de loopback. HTTPS via Tailscale Serve quando o Tailscale estiver no
ar; senão, túnel SSH.

## Acesso do operador

O SSH já funciona: `root@69.62.93.146`, hostname `srv769897`, autenticação por
chave. O sshd público já escuta em `0.0.0.0:22`. Não abrir mais portas.

GitHub Actions continua implantando via Tailscale OAuth
(`tailscale ssh deploy@srv769897` / `deploy-staging`). Tailscale é trava extra,
não um gate de negócio fail-closed. Se o Tailscale cair, o operador usa SSH.
Ainda assim, nunca renderizar jobs reais no laptop.

## Interface do operador

- `shortsflow job`: cria um job na produção remota.
- `shortsflow validate`: exige que a revisão local esteja implantada no staging,
  cria um job real nesse ambiente e pode aguardar o resultado.
- `shortsflow resume`: retoma uma branch publicada em um checkout limpo.
- `scripts/bootstrap_remote_client.sh`: instala a CLI e valida GitHub e, quando
  o Tailscale estiver no ar, as identidades remotas.

Jobs reais na VPS; laptops usam mocks. Isso é orientação operacional, não um
check obrigatório do GitHub.

Um único checkout para editar. Atualize com `git pull --ff-only origin/staging`.
O que não está em `origin/staging` não existe.

Jobs novos enviados pelo Hub, por `shortsflow validate` ou pelo smoke real usam
CTA suave por padrão. O roteiro precisa incluir esse CTA na narração e declarar
um arco narrativo fundamentado em trechos reais (`setup`, `tension`, `turn` e
`consequence`). O render final também é reprovado se a análise temporal detectar
vazamento de quadros pretos com duração igual ou superior a 40 ms. Jobs que
pedem explicitamente `cta_style=none` continuam suportados.

## Admissão e retenção

Staging não inicia um job quando:

- a drenagem está ativa;
- existem menos de 15 GiB livres no filesystem de dados;
- existem menos de 2 GiB de memória disponível;
- artifacts de staging ultrapassam 5 GiB antes da limpeza configurada.

Artifacts de staging têm retenção de sete dias. Produção mantém sua política
independente.

## Deploy

Push e pull request para `staging` passam por pytest e typecheck Remotion. O
staging auto-implanta esse SHA.

O único fluxo de promoção para produção é:

`feature -> staging -> vídeo real assistido pelo operador -> fast-forward do mesmo SHA para main + deploy`

Uma feature nunca segue diretamente para `main`. Depois que o SHA exato estiver
alcançável por `origin/staging`, implantado em staging, e o operador tiver
assistido um vídeo real desse staging, o workflow manual **Promote validated
staging revision** roda com o ref `staging` e esse SHA completo. Ele verifica
o histórico, exige que o input seja o próprio SHA do run e confirma pelo health
check privado que staging está saudável nessa revisão exata. Em seguida executa
`git push <SHA>:refs/heads/main` por fast-forward, sem rebuild, squash, merge
commit novo ou force-push. Se `main` mudar entre a verificação e o push, o
próprio fast-forward é recusado e a promoção precisa ser reavaliada.

O push feito pelo `GITHUB_TOKEN` não é usado como gatilho implícito. A promoção
dispara explicitamente **Deploy remote runtime** em `main`, informando o SHA
esperado. Esse workflow rejeita qualquer checkout diferente antes de acessar o
environment `production`, onde um único clique humano autoriza o deploy do
release imutável. Não há segundo environment de auto-aprovação
(`production-promotion`) nem job `authorize-promotion`. A aprovação que importa
é assistir o vídeo de staging; o clique no GitHub só registra essa decisão.

Pushes e pull requests para `main` passam pelo `promotion-guard` (o SHA precisa
ter passado por staging) e pelos testes canônicos antes de qualquer job
associado ao environment `production`. O deploy de produção continua exigindo
aprovação humana e prepara o release imutável diretamente do SHA já validado;
aprovação de workflow não autoriza agentes a aprovar produção.

O repositório deve manter um reviewer humano obrigatório só no environment
`production`. Como este repositório pessoal tem um único colaborador, a
proteção de `staging` não exige uma aprovação impossível do próprio autor; ela
exige os checks `test` e `promotion-guard`, vinculados ao GitHub Actions. A
proteção de `main` deve exigir esses dois checks, não `authorize-promotion`.
Se a proteção de branch ainda listar `authorize-promotion` como check
obrigatório, o operador remove esse required check na UI do GitHub — o YAML
não apaga branch protection. Durante a primeira reconciliação antes de o
workflow existir no default branch, o operador executa o mesmo protocolo sem
automação:

```bash
git fetch --no-tags origin \
  refs/heads/main:refs/remotes/origin/main \
  refs/heads/staging:refs/remotes/origin/staging
python scripts/check_staging_promotion.py <SHA-VALIDADO>
git push origin <SHA-VALIDADO>:refs/heads/main
```

Esse bootstrap continua sujeito à proteção de `main`; ele não usa force-push e
o servidor rejeita qualquer corrida que deixe a atualização não fast-forward.
Como `staging` pode conter commits de reconciliação, a proteção de `main` não
deve exigir histórico linear: essa regra rejeitaria o mesmo SHA já validado. A
linearidade da promoção é garantida pela checagem de ancestralidade e pelo push
fast-forward sem `--force`.

GitHub Actions entra na tailnet com identidade efêmera e aciona um usuário
`deploy` sem acesso geral de root. Se o Tailscale da Action estiver indisponível,
o operador implanta pelo SSH que já funciona; o workflow de CI não precisa ser
reescrito para isso. O deploy:

1. serializa implantações;
2. ativa drenagem e aguarda o job atual;
3. cria backup consistente;
4. prepara um release imutável;
5. troca o link `current` atomicamente;
6. reinicia o ambiente;
7. verifica health check e revisão;
8. reverte para o release anterior se a verificação falhar;
9. preserva o release ativo e três anteriores.

Produção exige aprovação humana (um clique no environment `production`).
Agentes podem implantar e validar staging, mas não aprovam produção.

## Segurança e continuidade

- Provider secrets permanecem exclusivamente em arquivos protegidos na VPS.
- Backups SQLite mantêm sete diários, quatro semanais e três predeploy; secrets
  possuem recuperação cifrada separada.
- SQLite, models e artifacts nunca entram no GitHub.
- Acesso operacional: SSH por chave que já funciona. Tailscale Serve/SSH para
  GitHub Actions e HTTPS privado quando o Tailscale estiver no ar.
- O app permanece em `127.0.0.1`. Sem portas públicas extras além do sshd já
  exposto em `0.0.0.0:22`.
- Branches protegidas bloqueiam force-push e exigem pytest + typecheck Remotion
  em `staging`.
- Falhas de GitHub ou Tailscale não interrompem a versão já implantada. Se o
  Tailscale cair, o operador usa SSH; o app não cai para o laptop.
- Falta de capacidade mantém trabalho na fila remota e nunca usa PCs locais
  para render real.

## Gates da promoção

- SHA em `origin/staging` e implantado no staging;
- pytest + typecheck Remotion verdes nesse SHA;
- um job real de staging concluído;
- vídeo revisado pelo operador;
- um clique no environment `production`.
