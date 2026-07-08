from scripts.process_cron_video_ideas import parse_ideas, select_best_ids, viral_score


SAMPLE = """
### ID: SF-20260707-5
- **Título viral provisório:** A aurora vista de dentro de uma nave parece um dragão verde
- **Hook de 1 linha em pt-BR:** Astronautas viram luzes verdes serpenteando abaixo deles enquanto estavam em órbita.
- **Loop/pergunta que segura até o fim:** Como uma tempestade solar vira esse monstro luminoso em volta da Terra?
- **Promessa visual:** aurora verde serpenteando / nave Dragon no espaço / Terra escura com luzes abaixo
- **Ângulo emocional:** maravilha
- **Risco de chatice:** baixo
- **Score viral inicial:** 8.5/10

### ID: SF-20260707-6
- **Título viral provisório:** O mês em que o céu tem fogos naturais melhores que os da Terra
- **Hook de 1 linha em pt-BR:** Enquanto a gente solta fogos, o espaço acende auroras, cometas e a Via Láctea.
- **Loop/pergunta que segura até o fim:** Qual desses espetáculos você conseguiria ver sem sair do planeta?
- **Promessa visual:** fogos humanos / aurora gigante / Via Láctea atravessando o céu
- **Ângulo emocional:** maravilha
- **Risco de chatice:** médio
- **Score viral inicial:** 7.5/10

### ID: SF-20260707-7
- **Título viral provisório:** A Lua fotografada por humanos de novo parece cenário de outro planeta
- **Hook de 1 linha em pt-BR:** Novas imagens da missão Artemis fazem a Lua parecer mais viva — e mais assustadora — do que nos livros.
- **Loop/pergunta que segura até o fim:** Por que a Lua vista de perto parece tão diferente da Lua do nosso quintal?
- **Promessa visual:** superfície lunar em close / Terra aparecendo atrás / câmera de astronauta tremendo
- **Ângulo emocional:** descoberta
- **Risco de chatice:** baixo
- **Score viral inicial:** 8/10
"""


def test_select_best_cron_video_ideas_by_score_and_risk():
    ideas = parse_ideas(SAMPLE)

    assert viral_score("8.5/10") == 8.5
    assert select_best_ids(ideas, top=2, min_score=8.0, max_risk="médio") == ["SF-20260707-5", "SF-20260707-7"]
