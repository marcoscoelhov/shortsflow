# Contrato de runtime remoto do ShortsFlow

## Objetivo

Usar computadores locais apenas para edição e verificações rápidas. Jobs reais,
providers, mídia, renderização e validações E2E pesadas executam na VPS. GitHub é
a fonte oficial do código e a VPS é o runtime oficial.

## Ambientes

| Ambiente | Branch | Estado | Carga |
| --- | --- | --- | --- |
| Local | branch de trabalho | sem secrets ou mídia persistente | lint e testes rápidos |
| Staging | `staging` | SQLite e artifacts isolados | providers reais, jobs explícitos |
| Produção | `main` | estado operacional existente | jobs reais e automações |

Staging e produção devem informar ambiente, revisão implantada, drenagem e
capacidade pelo health check. Os dois usam uma única instância de visão local e
um único slot global para jobs pesados. Produção tem prioridade para o próximo
slot disponível; um job de staging já iniciado nunca é interrompido.

## Interface do operador

- `shortsflow job`: cria um job na produção remota.
- `shortsflow validate`: exige que a revisão local esteja implantada no staging,
  cria um job real nesse ambiente e pode aguardar o resultado.
- `shortsflow resume`: retoma uma branch publicada em um checkout limpo.
- `scripts/bootstrap_remote_client.sh`: instala a CLI e valida GitHub, Tailscale
  e os dois ambientes.

Nenhum comando pode usar CPU local como fallback. Indisponibilidade deve produzir
erro acionável e preservar o estado remoto.

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

O único fluxo de promoção suportado é:

`feature -> staging -> validação real/humana -> fast-forward do mesmo SHA para main`

Uma feature nunca segue diretamente para `main`. Depois que o SHA exato estiver
alcançável por `origin/staging`, implantado em staging, validado com providers
reais e aprovado visualmente pelo operador, o workflow manual **Promote
validated staging revision** recebe esse SHA completo. Um job sem acesso ao
environment de produção verifica que o commit pertence ao histórico de staging
e que avança `main` por fast-forward. Somente então o job protegido pelo
environment `production` executa `git push <SHA>:refs/heads/main`, sem rebuild,
squash, merge commit novo ou force-push. Se `main` mudar entre a verificação e o
push, o próprio fast-forward é recusado e a promoção precisa ser reavaliada.

Pushes e pull requests para `main` passam pelo mesmo controle antes de qualquer
job associado ao environment `production`. O deploy de produção continua
exigindo aprovação humana e prepara o release imutável diretamente do SHA já
validado; aprovação de workflow não autoriza agentes a aprovar produção.

O repositório deve manter um reviewer humano obrigatório no environment
`production` e permitir que a identidade do workflow de promoção faça somente o
fast-forward protegido de `main`. Se a regra de branch não autorizar essa
identidade, ou durante a primeira reconciliação antes de o workflow existir no
default branch, o operador executa o mesmo protocolo sem automação:

```bash
git fetch --no-tags origin \
  refs/heads/main:refs/remotes/origin/main \
  refs/heads/staging:refs/remotes/origin/staging
python scripts/check_staging_promotion.py <SHA-VALIDADO>
git push origin <SHA-VALIDADO>:refs/heads/main
```

Esse bootstrap continua sujeito à proteção de `main`; ele não usa force-push e
o servidor rejeita qualquer corrida que deixe a atualização não fast-forward.

GitHub Actions entra na tailnet com identidade efêmera e aciona um usuário
`deploy` sem acesso geral de root. O deploy:

1. serializa implantações;
2. ativa drenagem e aguarda o job atual;
3. cria backup consistente;
4. prepara um release imutável;
5. troca o link `current` atomicamente;
6. reinicia o ambiente;
7. verifica health check e revisão;
8. reverte para o release anterior se a verificação falhar;
9. preserva o release ativo e três anteriores.

Produção exige aprovação humana. Agentes podem implantar e validar staging, mas
não aprovam produção.

## Segurança e continuidade

- Provider secrets permanecem exclusivamente em arquivos protegidos na VPS.
- Backups SQLite mantêm sete diários, quatro semanais e três predeploy; secrets
  possuem recuperação cifrada separada.
- SQLite, models e artifacts nunca entram no GitHub.
- Tailscale SSH substitui chaves privadas copiadas entre computadores.
- Staging e produção são acessíveis somente pela tailnet.
- Branches protegidas bloqueiam force-push e exigem verificações.
- Falhas de GitHub ou Tailscale não interrompem a versão já implantada.
- Falta de capacidade mantém trabalho na fila remota e nunca usa PCs locais.

## Gates da primeira promoção

- snapshots local e remoto verificados;
- reconciliação revisada;
- suíte completa remota verde;
- health check do staging na revisão esperada;
- um job E2E com providers reais concluído;
- vídeo revisado pelo operador;
- backup e rollback exercitados antes da conversão de produção.
