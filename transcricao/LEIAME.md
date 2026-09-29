# Transcrição dos vídeos de pesca (Windows)

## Por que o faster-whisper falhava

O `pip` tentou compilar o pacote `av` a partir do código-fonte. Isso acontece
quando ele escolhe uma versão antiga do `av` (a `av==10`, por exemplo, não tem
wheel para Python 3.12) ou quando o próprio pip está desatualizado. Hoje todas
as dependências do faster-whisper têm wheel pronto para Windows + Python 3.12
(`av-19.0.0-cp312-abi3-win_amd64.whl`, `ctranslate2`, `onnxruntime` etc.),
então não é preciso ter o Visual C++.

Além disso, o script extrai o áudio com o **ffmpeg** que você já tem e não
usa o `av` em nenhum momento. Se o `av` não instalar, ele continua funcionando.

## Instalação (uma vez só)

No PowerShell, dentro desta pasta:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
pip install --only-binary=:all: faster-whisper
```

`--only-binary=:all:` proíbe o pip de compilar qualquer coisa. Se mesmo assim
ele reclamar do `av`, instale sem ele:

```powershell
pip install --only-binary=:all: ctranslate2 tokenizers onnxruntime huggingface_hub tqdm numpy
pip install --no-deps faster-whisper
```

(Se o PowerShell bloquear o `Activate.ps1`, rode antes
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.)

## 1) Teste com um vídeo só

```powershell
python transcrever_videos.py "D:\Videos\Pesca" --teste
```

O primeiro vídeo encontrado vira um `.srt` ao lado dele, e o arquivo
`transcricao_teste.csv` é criado na pasta raiz. Na primeira execução o modelo
é baixado (~480 MB para o `small`). Para testar um vídeo específico:

```powershell
python transcrever_videos.py "D:\Videos\Pesca" --arquivo "D:\Videos\Pesca\Araguaia\GOPR0001.MP4"
```

Abra o `.srt` e veja se a qualidade está boa. Se não estiver, repita com
`--modelo medium --refazer`.

## 2) Lote completo

```powershell
python transcrever_videos.py "D:\Videos\Pesca"
```

- Procura vídeos em todas as subpastas (`.mp4 .mov .mkv .avi .m4v .mts .3gp .wmv .webm`).
- Grava um `.srt` ao lado de cada vídeo.
- Grava `transcricoes.csv` na pasta raiz, com as colunas
  `pescaria;arquivo;inicio;fim;fala`. **pescaria** é o nome da pasta onde o
  vídeo está (se o vídeo estiver direto na raiz, usa o nome do arquivo).
  O separador é `;` e a codificação é UTF-8 com BOM, então o arquivo abre
  direto no Excel em português, com acentos.
- **Pode interromper (Ctrl+C) e rodar de novo:** os vídeos que já têm `.srt`
  são pulados, mas as falas deles continuam entrando no CSV. Use `--refazer`
  para transcrever tudo de novo.
- Para pular pastas, use `--excluir` com os nomes delas (vale em qualquer
  nível e não diferencia maiúsculas/minúsculas):
  `--excluir Editados "outra pasta"`
- Se algum vídeo der erro (arquivo corrompido, por exemplo), o lote continua
  e a lista de erros aparece no fim.
- Deixe o `transcricoes.csv` fechado no Excel enquanto o script roda, porque
  ele é gravado no final.

## Modelo e tempo

| modelo            | qualidade em PT | velocidade na CPU |
|-------------------|-----------------|-------------------|
| `small` (padrão)  | boa             | rápida            |
| `medium`          | melhor          | ~2–3× mais lento  |
| `large-v3-turbo`  | ótima           | lento na CPU      |

A velocidade depende muito do processador. Use o `--teste`
para medir: o script mostra quantos minutos de áudio levaram quantos minutos
para transcrever. Com uma placa NVIDIA e as bibliotecas CUDA (cuBLAS/cuDNN)
instaladas, use `--dispositivo cuda --modelo large-v3-turbo`.

O script já liga o filtro de voz (VAD) e desativa o condicionamento no texto
anterior. Isso reduz o texto inventado nos trechos só com vento, motor ou água.
