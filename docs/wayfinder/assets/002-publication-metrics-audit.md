# Auditoria de cobertura de publicação e métricas — 2026-07-03

Fonte: leitura local de `/root/shortsflow/data/shortsflow_render.db` em `2026-07-03T18:07:11Z`. Sem inferência de performance sem snapshot local/API.

## Resumo

- Schedules totais no DB: `43`.
- Recorte usado para a sprint atual/cosmos-like: `16` schedules com origem `automatic_topic`/`ready_script_bank`, termos cosmos, ou slot >= `2026-07-01`.
- Recorte julho atual: `10` schedules desde `2026-07-01`, todos com `youtube_video_id`.
- Julho com snapshot de Analytics: `4/10`.
- Julho maduro por regra 72h: `0/10`.
- Conclusão: a sprint atual ainda não tem métrica madura; decisão editorial agora seria chute.

## Recorte atual desde 2026-07-01

| job | origem | status | slot local | youtube_video_id | views | retenção | maduro 72h | título |
| --- | --- | --- | --- | --- | ---: | ---: | --- | --- |
| `6d04537b` | automatic_topic | scheduled | 2026-07-05 18:00 | `984QCSFQGFY` | — | — | não | O planeta mais quente não é o mais perto do Sol |
| `e087a575` | ready_script_bank | scheduled | 2026-07-05 11:00 | `SBa1oJ5-o8U` | — | — | não | SATURNO USA UM DISCO FEITO DE DESTROÇOS |
| `eacbf0c0` | automatic_topic | scheduled | 2026-07-04 18:00 | `M39UtxSsPU8` | — | — | não | A sombra que engoliu o Sol e assustou o mundo |
| `b1bb2c65` | automatic_topic | scheduled | 2026-07-04 11:00 | `hcNz3BaAlc4` | — | — | não | Buraco negro não grava som. NASA criou áudio com ondas de pressão |
| `521bbfab` | automatic_topic | scheduled | 2026-07-03 18:00 | `TGVtHXn8gRc` | — | — | não | Por que a Lua parece tão grande no horizonte? |
| `f4c46dcd` | automatic_topic | published | 2026-07-03 11:00 | `I9ddt_ZYAA4` | — | — | não | Gelo que pega fogo no Sol? O segredo do cometa |
| `4370acef` | automatic_topic | published | 2026-07-02 18:00 | `atNgSe0yxQY` | 0 | 0 | não | Por que Marte é vermelho? A ferrugem que cobre o planeta |
| `fdca3e88` | manual_title | published | 2026-07-02 11:00 | `-0fPGcomDpI` | 0 | 0 | não | Planeta rosa de nuvens de sal existe de verdade |
| `6b1b7445` | automatic_topic | published | 2026-07-01 18:00 | `y0K4v0U6VPk` | 0 | 0 | não | Netuno é azul? A culpa é do metano na atmosfera |
| `9a5c8dae` | automatic_topic | published | 2026-07-01 11:00 | `ohgO4yMc458` | 0 | 0 | não | Por que as estrelas piscam? A atmosfera que dança |

## Baseline/mediana

- Últimos snapshots locais em `youtube_analytics_snapshots`: `37` jobs com views; mediana local bruta atual = `182`; máximo = `1199`.
- `docs/CONTROL.md` registra baseline `191.5`; não consegui reproduzir exatamente esse número da fotografia atual, provavelmente por mudança de janela/filtro ou inclusão dos zeros frescos de julho.
- Um filtro “cosmos-like” histórico amplo dá mediana `562.5`, mas inclui falsos positivos como `Buraco azul...` e `Toupeira...`; não usar como baseline oficial sem um filtro editorial explícito.

## Lacunas

1. O recorte de mediana precisa ser codificado/documentado: todos os snapshots, só publicados maduros, só cosmos, excluir zeros <72h, etc.
2. Julho tem IDs/schedules suficientes, mas ainda não tem 72h de maturação.
3. Retenção existe nos snapshots, mas CTR/impressões/origem de tráfego continuam indisponíveis no DB atual.

## Decisão operacional

Esperar maturação dos slots de julho e só então recalcular baseline. Se precisar agir antes, a única ação segura é coletar/sincronizar Analytics pendente; não mudar nicho/prompt ainda.
