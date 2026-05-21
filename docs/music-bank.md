# Banco de Trilhas Aprovadas

O banco de trilhas aprovadas e a fonte padrao de musica de fundo para jobs reais. Ele evita custo por geracao, limite de provedor e fallback silencioso para API.

Por padrao, quando o banco esta vazio, o app popula automaticamente um estoque inicial de trilhas sinteticas locais. Essas trilhas sao geradas pelo proprio projeto, sem download externo, sem samples, sem vocal e sem API.

Quando existirem trilhas MiniMax antigas com quality gate aprovado, importe-as para o banco. Elas viram trilhas `primary`; as sinteticas locais ficam como fallback operacional.

## Onde colocar

```text
data/music_bank/
  manifest.json
  tracks/
    local-science-calm-01.wav
  licenses/
    local-science-calm-01.txt
```

`data/` e estado local, portanto as musicas e licencas baixadas nao devem ir para o Git.

## Manifest minimo

```json
{
  "tracks": [
    {
      "id": "science-calm-01",
      "path": "tracks/science-calm-01.mp3",
      "title": "Science Calm",
      "artist": "YouTube Audio Library",
      "moods": ["technology", "documentary", "cinematic"],
      "tags": ["ciencia", "curiosidades", "ambiente"],
      "license": "YouTube Audio Library",
      "source_url": "https://youtube.com/audiolibrary",
      "license_file": "licenses/science-calm-01.txt",
      "approved_for_youtube": true,
      "requires_attribution": false,
      "content_id_registered": false,
      "content_id_risk": "low"
    }
  ]
}
```

## Regras de entrada

- A populacao automatica cria trilhas sinteticas locais, nao baixa musicas de catalogos externos.
- Use primeiro faixas da YouTube Audio Library com atribuicao nao obrigatoria.
- Salve a pagina, texto ou comprovante de licenca em `licenses/`.
- Nao aprove faixas marcadas como Content ID registrado.
- Nao use licencas `CC-NC` para canal monetizado.
- Nao baixe musica aleatoria em runtime; o banco deve ser curado antes do job.

## Popular automaticamente

O app popula automaticamente o banco quando `YTS_MUSIC_BANK_AUTO_POPULATE=true` e `manifest.json` ainda nao existe ou nao tem faixas utilizaveis.

Tambem da para rodar manualmente:

```bash
.venv/bin/python scripts/populate_music_bank.py
```

Para recriar as trilhas sinteticas locais:

```bash
.venv/bin/python scripts/populate_music_bank.py --force
```

## Importar trilhas MiniMax antigas

Para reaproveitar trilhas MiniMax ja geradas em jobs anteriores:

```bash
.venv/bin/python scripts/import_minimax_music_artifacts.py
```

O importador:

- varre `data/artifacts/*/background_music.json`
- importa apenas `provider=minimax_music`
- exige `background_music_quality_report.json` com `passed=true`
- copia o WAV local para `data/music_bank/tracks/`
- salva evidencia em `data/music_bank/licenses/`
- evita duplicatas por hash de conteudo
- remove query string de URLs assinadas antes de registrar `source_url`
- marca as trilhas importadas como `quality_tier=primary`

## Configuracao

O Hub de Revisao controla a fonte de musica, autopopulacao do banco local e fallback para API no modal `Configurações`.

Use `Banco local` para manter o fluxo sem custo de API, `MiniMax` para forcar geracao por API, ou `Auto` para tentar banco local e depois MiniMax quando houver chave. `YTS_MUSIC_BANK_DIR` continua sendo configuracao de ambiente porque define onde os arquivos locais vivem.
