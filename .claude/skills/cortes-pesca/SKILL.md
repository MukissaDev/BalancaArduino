---
name: cortes-pesca
description: Transforma uma pasta de vídeos brutos de pesca em cortes editados prontos para postar (YouTube, Shorts, Reels, TikTok). Transcreve tudo com legenda (.srt), "assiste" aos vídeos por quadros + fala + volume + sons identificados (carretilha, splash, grito), escolhe os melhores momentos, decide se junta vários vídeos ou divide um em vários cortes, renderiza com ffmpeg numa subpasta Editados_IA e aprende com o feedback. Use sempre que o usuário pedir para legendar/transcrever vídeos de pesca, achar os melhores momentos, fazer cortes ou shorts/reels/tiktoks, editar vídeos de pescaria em lote, ou ajustar/refazer cortes já gerados, mesmo sem usar as palavras "habilidade" ou "cortes".
---

# Cortes de pesca

Você vai pegar uma pasta com vídeos brutos de pescaria e entregar, dentro dela, a
pasta `Editados_IA/` com vídeos editados que valem a pena postar. Cada vídeo sai
acompanhado de um `.txt` com título, descrição e hashtags. O usuário vai avaliar
o resultado e a habilidade melhora com o retorno dele. Por isso, registre o
aprendizado em `preferencias.md` (veja a etapa 6).

Os scripts estão em `scripts/` dentro da pasta desta habilidade. Nos comandos
abaixo, `$H` é essa pasta e `$PY` é o Python do ambiente (etapa 0). O ambiente
normal é o Windows com o Git Bash do Claude Code, então use `/` nos caminhos e
coloque aspas em tudo que tiver espaço.

## Etapa 0: preparar

1. Leia `$H/preferencias.md` antes de tudo. Ali está o que o usuário já
   aprovou ou reprovou em rodadas anteriores, e isso vale mais do que os
   padrões descritos aqui.
2. Confirme com o usuário a pasta e as subpastas que devem ser ignoradas. A
   pasta `Editados_IA` é sempre ignorada.
3. Verifique o ambiente e crie o que faltar:
   ```bash
   ffmpeg -version | head -1
   ffmpeg -hide_banner -filters | grep -w ass   # precisa aparecer, porque é o filtro que queima a legenda
   PY=~/.cortes-pesca/venv/Scripts/python.exe   # no Linux/Mac: ~/.cortes-pesca/venv/bin/python
   [ -x "$PY" ] || { py -3.12 -m venv ~/.cortes-pesca/venv && "$PY" -m pip install -U pip; }
   "$PY" -m pip install --only-binary=:all: faster-whisper pillow torch transformers
   ```
   `--only-binary=:all:` impede o pip de compilar algo (o usuário não tem
   Visual C++). Se o `av` der problema, veja
   `references/instalacao_transcricao.md`: os scripts funcionam sem ele.
   Se o filtro `ass` não aparecer, o ffmpeg instalado é uma versão reduzida.
   Peça ao usuário para instalar a versão completa (`winget install Gyan.FFmpeg`)
   ou use `"legenda": false` nos cortes.

   Rode tudo **no computador do usuário**, nunca numa sessão na nuvem: os vídeos
   estão lá, e os modelos (Whisper e o de sons) são baixados do HuggingFace na
   primeira vez. No Windows, o `torch` do PyPI já vem na versão só para CPU.

## Etapa 1: transcrever

```bash
"$PY" "$H/scripts/transcrever_videos.py" "<pasta>" --excluir <pastas a ignorar> --teste
```
Na primeira vez, rode com `--teste` e mostre ao usuário a qualidade e o tempo
gasto ("X min de áudio em Y min"). Depois rode sem `--teste` **em segundo plano**,
porque com dezenas de vídeos leva horas. O padrão é `--modelo small`; se o
português sair ruim, use `--modelo medium`. Vídeos que já têm `.srt` são pulados,
então dá para retomar o lote. Junto do `.srt`, o script grava o
`<video>.palavras.json` com o tempo de cada palavra. O renderizador usa esse
arquivo para não cortar no meio de uma palavra e para a legenda palavra a palavra.

## Etapa 2: preparar a análise

```bash
"$PY" "$H/scripts/analisar_videos.py" "<pasta>" --excluir <pastas a ignorar>
```
O script gera `Editados_IA/_analise/indice.md` e, para cada vídeo, as folhas
`folha_NN.jpg` (quadros com o tempo impresso) e um `resumo.md` com:
- **Momentos de áudio alto:** volume acima do normal daquele vídeo, já com o
  som provável entre colchetes (`+22 dB [carretilha]`).
- **Sons identificados:** trechos de carretilha, splash, grito, risada,
  comemoração ou música, reconhecidos pelo modelo CLAP, mais o som de fundo
  predominante (motor, vento, fala calma).
- **Fala:** cada frase com o horário e o volume dela. A marca ★ indica que a
  frase parece uma reação espontânea: uma exclamação curta, uma palavra repetida
  ("vai vai vai"), uma expressão de reação dita alto ou uma fala bem mais alta
  que o normal.

Na primeira vez ele baixa o modelo de sons (~600 MB). Se o torch não estiver
instalado, o resumo avisa que os sons não foram analisados e o resto continua
funcionando. O script só refaz um vídeo quando o `.srt`, o `.palavras.json` ou
o `sons.json` da habilidade mudarem.

## Etapa 3: assistir

Você não ouve o áudio e não vê o vídeo corrido. "Assistir" aqui é cruzar as
fontes que substituem a audição e a visão:
- as **folhas de quadros** (abra com Read);
- a **fala**, com volume e a marca ★;
- os **sons identificados**;
- os **picos de volume**.

Os momentos mais fortes costumam ter várias delas ao mesmo tempo. Exemplo: um
pico com `[carretilha]`, seguido de `[splash]`, de uma fala ★ "pegou! pegou!" e
de um quadro com a vara envergada.

Use cada fonte pelo que ela vale:
- O classificador de sons erra às vezes. Confirme com os quadros e com a fala
  antes de basear um corte só nele.
- Não invente o que nenhuma fonte mostra.
- Se um som de pesca aparecer sempre com o rótulo errado, ajuste o `prompt` dele
  em `$H/sons.json` (veja a etapa 6).

Com muitos vídeos, trabalhe **pasta por pasta** e anote enquanto avança em
`Editados_IA/_analise/notas.md`, para não depender da memória:

```
## <pasta>/<arquivo> (duração)
- 00:41–01:05 ★★★ fisgada + briga, grito "pegou!", peixe pula em 00:58. Ação à esquerda (centro_x≈0.35)
- 02:10–02:30 ★★ foto com tucunaré, explica a isca
- resto: câmera parada na água, sem fala
```

Quando um trecho parecer bom, refine os pontos de corte com uma folha mais densa:
```bash
"$PY" "$H/scripts/analisar_videos.py" detalhe "<video>" 38 70 --passo 0.5 --saida "<pasta>/Editados_IA/_analise/<video>"
```

### O que costuma render bem em vídeo de pesca
- **Ação:** fisgada (a "batida"), briga com a vara envergada, carretilha
  cantando, o peixe saindo da água ou pulando, o embarque.
- **Recompensa:** o peixe na mão, a foto, o tamanho, a soltura.
- **Reação:** grito, risada, susto, a frase espontânea. Isso aparece nos picos
  de áudio e nas falas.
- **Valor:** dica de isca, de técnica, de lugar ou de equipamento, dita de
  forma clara.
- **Tensão e erro:** o peixe que escapa na hora H costuma engajar muito.
- **Respiro:** paisagem bonita, nascer do sol, água espelhada. Use como abertura
  ou transição curta, nunca como o corte principal.

Descarte trechos longos sem nada acontecendo, câmera apontada para o chão ou
para o céu, partes muito tremidas e momentos que se repetem. Se houver vários
iguais, fique só com o melhor.

## Etapa 4: decidir os cortes

Você decide a estrutura. Pense no que faria **alguém que não conhece o
pescador** parar de rolar a tela e assistir até o fim.

- **Um vídeo vira vários cortes** quando há momentos independentes e fortes no
  mesmo arquivo, por exemplo duas fisgadas separadas.
- **Vários vídeos viram um corte** quando:
  - o momento foi dividido em arquivos (a GoPro divide em `GOPR0001`, `GP010001`...);
  - a sequência conta uma história (chegada, tentativas, fisgada, peixe, soltura);
  - existe um tema de compilação ("3 tucunarés em uma manhã", "os escapes do dia").
- **Vertical (Shorts, Reels, TikTok):** de 15 a 60 s funciona melhor. O máximo
  é 180 s no Shorts e no Reels e mais no TikTok. Os **2 primeiros segundos** já
  precisam mostrar ação ou a promessa dela; vale abrir com o clímax (o peixe
  saindo da água) e depois voltar ao contexto. Termine logo depois do pico, sem
  enrolação. A legenda queimada é importante porque muita gente assiste sem som.
- **YouTube (horizontal):** a história da pescaria em 3 a 12 min, com os
  melhores trechos de cada pasta em ordem, ou uma compilação temática.
- **Enquadramento** em vídeo horizontal que vira vertical:
  - `corte` com `centro_x` apontando onde está a ação (olhe as folhas);
  - `desfoque` quando a ação ocupa a largura toda ou quando cortar perderia o peixe.
- `velocidade` 0.5 só no instante mais forte (o pulo, a batida), por 1 a 3 s.
- `texto_tela` é um gancho curto, de até 5 palavras, como "OLHA O TAMANHO
  DESSE". Evite emoji: ele aparece sem cor.

Escreva `Editados_IA/plano.json` no formato descrito em `references/plano.md`
(leia antes de escrever). Em `justificativa`, explique a escolha em uma frase.
É com ela que o usuário vai te dar retorno. Valide e renderize:
```bash
"$PY" "$H/scripts/renderizar.py" "<pasta>/Editados_IA/plano.json" --validar
"$PY" "$H/scripts/renderizar.py" "<pasta>/Editados_IA/plano.json"
```
Renderizar também demora, então rode em segundo plano quando houver muitos
cortes. Cortes que já existem são pulados. Para refazer só alguns, use
`--so nome1 nome2 --refazer`.

## Etapa 5: conferir antes de entregar

Para cada corte, extraia 3 quadros (início, meio e fim) e olhe se o
enquadramento pegou a ação e se a legenda está legível:
```bash
"$PY" "$H/scripts/analisar_videos.py" detalhe "<pasta>/Editados_IA/<nome>.mp4" 0 <duração> --passo <duração/3> --saida "<pasta>/Editados_IA/_analise/conferencia"
```
Corrija o plano e renderize de novo o que estiver errado. Depois entregue um
resumo curto: quantos cortes, para quais plataformas, os 3 que você mais
recomenda e por quê. Indique o `relatorio.md`.

## Etapa 6: aprender com o retorno

Quando o usuário comentar os resultados ("o 03 ficou longo", "gostei de
começar pelo pulo", "não precisa de legenda no YouTube"):
1. Ajuste o `plano.json` e renderize de novo só o que for afetado.
2. Registre o aprendizado em `$H/preferencias.md`, na seção "Aprendizados",
   com a data. Escreva como regra geral e com o motivo. Por exemplo: "Cortes
   verticais: no máximo 40 s, porque o usuário acha que acima
   disso perde a atenção." Uma nota como "o corte 03 ficou longo" não serve para a próxima
   pasta. Se um aprendizado novo contradizer um antigo, substitua o antigo.

3. Se o erro for do classificador de sons (por exemplo, "aquilo não era
   carretilha, era o motor"), ajuste o `prompt` do rótulo em `$H/sons.json`.
   As descrições são em inglês, porque o modelo CLAP foi treinado assim. Também
   dá para criar um rótulo novo, como "peixe batendo no barco". Depois rode a
   análise de novo: só os vídeos afetados são refeitos.

O `preferencias.md` é a memória da habilidade entre uma pasta e outra. Mantenha
o arquivo curto e atualizado.
