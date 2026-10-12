# Formato do plano.json

Salve em `<pasta>/Editados_IA/plano.json`. Os caminhos dos vídeos são
relativos à pasta raiz (ou absolutos). Os tempos podem ser escritos em
segundos (`41.5`) ou como `"mm:ss"`, `"mm:ss.s"` ou `"h:mm:ss"`.

```json
{
  "pasta": "C:/Users/Iran/Videos/Instagram",
  "cortes": [
    {
      "nome": "01_tucuna_explode_na_isca",
      "formato": "vertical",
      "plataformas": ["shorts", "reels", "tiktok"],
      "titulo": "Tucunaré explodiu na isca de superfície!",
      "descricao": "Olha a batida desse tucunaré no rio Araguaia 🎣",
      "hashtags": ["#pesca", "#tucunare", "#pescaesportiva"],
      "justificativa": "Abre com o pulo (clímax) e depois mostra a briga; grito no pico de áudio em 00:58.",
      "legenda": true,
      "clipes": [
        {"arquivo": "instagram-mukissaa-2026-09-10-AbCd/GOPR0001.MP4",
         "inicio": "00:57.5", "fim": "00:59.5", "velocidade": 0.5,
         "centro_x": 0.35, "texto_tela": "OLHA ESSA BATIDA"},
        {"arquivo": "instagram-mukissaa-2026-09-10-AbCd/GOPR0001.MP4",
         "inicio": "00:41", "fim": "01:05", "centro_x": 0.35},
        {"arquivo": "instagram-mukissaa-2026-09-10-AbCd/GP010001.MP4",
         "inicio": 0, "fim": 12, "enquadramento": "desfoque"}
      ]
    }
  ]
}
```

## Campos do corte

| campo | padrão | o que faz |
|---|---|---|
| `nome` | `corte_NN` | nome do arquivo de saída. Use prefixo numérico + descrição curta, sem acento |
| `formato` | `vertical` | `vertical` (1080x1920) ou `horizontal` (1920x1080) |
| `plataformas` | `[]` | `shorts`, `reels`, `tiktok`, `youtube`. O script avisa se passar do limite de duração |
| `titulo`, `descricao`, `hashtags` | vazio | vão para o `<nome>.txt` |
| `justificativa` | vazio | uma frase explicando a escolha. Vai para o `.txt` e para o `relatorio.md` |
| `legenda` | `true` | `true` usa `"palavras"` no vertical e `"frases"` no horizontal. `"palavras"`: blocos de até 3 palavras, com a palavra falada em amarelo, no estilo Reels (precisa do `.palavras.json`; sem ele, cai em frases). `"frases"`: a frase inteira do `.srt`. `false`: sem legenda |
| `ajustar_fala` | `true` | se o início ou o fim cair no meio de uma palavra, estende o trecho até a palavra inteira. O `--validar` mostra cada ajuste |
| `clipes` | obrigatório | trechos em ordem. Podem vir de vídeos diferentes |

## Campos do clipe

| campo | padrão | o que faz |
|---|---|---|
| `arquivo` | obrigatório | vídeo de origem |
| `inicio`, `fim` | 0, fim do vídeo | trecho no vídeo de origem |
| `enquadramento` | `corte` | `corte` preenche a tela cortando as laterais. `desfoque` mostra o quadro inteiro sobre um fundo desfocado |
| `centro_x` | 0.5 | só no `corte`: posição horizontal da ação, de 0 (esquerda) a 1 (direita) |
| `velocidade` | 1 | de 0.5 a 2. Use 0.5 para câmera lenta no instante-chave. O áudio acompanha |
| `texto_tela` | vazio | texto amarelo no topo durante todo o clipe |

## Observações

- O áudio de cada clipe é normalizado para cerca de -14 LUFS, o volume usual
  das redes, e ganha uma pequena transição de entrada e saída para não estalar
  no corte.
- Os vídeos sem áudio recebem silêncio.
- Sempre rode `--validar` antes de renderizar. Ele aponta arquivo inexistente,
  trecho invertido e limite de plataforma estourado.
