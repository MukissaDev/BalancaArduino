"""Transcreve vídeos em português com faster-whisper, gerando .srt e um CSV.

- O áudio é extraído pelo ffmpeg do sistema (não depende do pacote `av`).
- Gera um .srt ao lado de cada vídeo.
- Gera um CSV (separador ';', UTF-8 com BOM para abrir direto no Excel) com
  pescaria, arquivo, inicio, fim, fala. "pescaria" é o nome da pasta do vídeo.
- Vídeos que já têm .srt são pulados (dá para interromper e retomar), mas as
  falas deles continuam entrando no CSV.

Uso:
    python transcrever_videos.py "D:\\Videos\\Pesca" --teste      # só 1 vídeo
    python transcrever_videos.py "D:\\Videos\\Pesca"              # todos
"""

import argparse
import csv
import re
import shutil
import subprocess
import sys
import time
import types
from pathlib import Path

import numpy as np

EXTENSOES = {".mp4", ".mov", ".mkv", ".avi", ".m4v", ".mts", ".3gp", ".wmv", ".webm"}
TAXA = 16000

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def importar_faster_whisper():
    """Importa faster-whisper mesmo que o pacote `av` não esteja instalado.

    O faster-whisper só usa `av` para decodificar arquivos; como aqui o áudio
    já chega decodificado pelo ffmpeg, um módulo vazio basta para o import.
    """
    try:
        import av  # noqa: F401
    except ImportError:
        sys.modules["av"] = types.ModuleType("av")
    from faster_whisper import WhisperModel

    return WhisperModel


def ler_audio(caminho: Path) -> np.ndarray:
    cmd = [
        "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
        "-i", str(caminho), "-vn", "-ac", "1", "-ar", str(TAXA),
        "-f", "s16le", "-",
    ]
    proc = subprocess.run(cmd, capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.decode("utf-8", "replace").strip())
    return np.frombuffer(proc.stdout, np.int16).astype(np.float32) / 32768.0


def fmt_srt(seg: float) -> str:
    ms = int(round(seg * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def fmt_csv(seg: float) -> str:
    s = int(seg)
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def escrever_srt(caminho: Path, falas):
    tmp = caminho.with_suffix(".srt.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        for i, (ini, fim, texto) in enumerate(falas, 1):
            f.write(f"{i}\n{fmt_srt(ini)} --> {fmt_srt(fim)}\n{texto}\n\n")
    tmp.replace(caminho)  # só aparece o .srt final se terminou


def ler_srt(caminho: Path):
    """Relê um .srt já existente para incluir no CSV."""
    def seg(t):
        h, m, s = t.replace(",", ".").split(":")
        return int(h) * 3600 + int(m) * 60 + float(s)

    blocos = re.split(r"\n\s*\n", caminho.read_text(encoding="utf-8-sig").strip())
    falas = []
    for b in blocos:
        linhas = b.strip().splitlines()
        if len(linhas) >= 3 and "-->" in linhas[1]:
            ini, fim = (x.strip() for x in linhas[1].split("-->"))
            falas.append((seg(ini), seg(fim), " ".join(linhas[2:]).strip()))
    return falas


def transcrever(modelo, audio, beam):
    segmentos, info = modelo.transcribe(
        audio,
        language="pt",
        beam_size=beam,
        vad_filter=True,  # corta vento/motor/silêncio e evita "alucinações"
        vad_parameters={"min_silence_duration_ms": 700},
        condition_on_previous_text=False,  # evita frases repetidas em loop
    )
    return [(s.start, s.end, s.text.strip()) for s in segmentos if s.text.strip()]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pasta", type=Path, help="pasta raiz com os vídeos (busca em subpastas)")
    ap.add_argument("--teste", action="store_true", help="processa só o primeiro vídeo")
    ap.add_argument("--arquivo", type=Path, help="processa só este vídeo")
    ap.add_argument("--modelo", default="small",
                    help="tiny, base, small, medium, large-v3, large-v3-turbo (padrão: small)")
    ap.add_argument("--dispositivo", default="cpu", choices=["cpu", "cuda"],
                    help="cuda só com placa NVIDIA e bibliotecas cuBLAS/cuDNN instaladas")
    ap.add_argument("--beam", type=int, default=5)
    ap.add_argument("--csv", type=Path, help="caminho do CSV (padrão: <pasta>/transcricoes.csv)")
    ap.add_argument("--refazer", action="store_true", help="transcreve de novo mesmo se já existir .srt")
    args = ap.parse_args()

    if not shutil.which("ffmpeg"):
        sys.exit("ffmpeg não encontrado no PATH.")
    raiz = args.pasta.resolve()
    if args.arquivo:
        videos = [args.arquivo.resolve()]
    else:
        videos = sorted(p for p in raiz.rglob("*") if p.suffix.lower() in EXTENSOES and p.is_file())
        if args.teste:
            videos = videos[:1]
    if not videos:
        sys.exit(f"Nenhum vídeo encontrado em {raiz}")
    csv_path = args.csv or (raiz / ("transcricao_teste.csv" if args.teste or args.arquivo else "transcricoes.csv"))

    print(f"{len(videos)} vídeo(s). Modelo: {args.modelo}. CSV: {csv_path}")
    modelo = None
    linhas_csv, falhas = [], []
    t0 = time.time()

    for n, video in enumerate(videos, 1):
        srt = video.with_suffix(".srt")
        pescaria = video.parent.name if video.parent != raiz else video.stem
        rotulo = f"[{n}/{len(videos)}] {video.relative_to(raiz) if video.is_relative_to(raiz) else video}"
        try:
            if srt.exists() and not args.refazer:
                print(f"{rotulo} — já tem .srt, pulando")
                falas = ler_srt(srt)
            else:
                if modelo is None:
                    WhisperModel = importar_faster_whisper()
                    print(f"Carregando modelo '{args.modelo}' (na 1ª vez baixa da internet)...")
                    modelo = WhisperModel(args.modelo, device=args.dispositivo, compute_type="auto")
                print(f"{rotulo} — transcrevendo...", flush=True)
                ti = time.time()
                audio = ler_audio(video)
                falas = transcrever(modelo, audio, args.beam)
                escrever_srt(srt, falas)
                dur = len(audio) / TAXA
                print(f"    {len(falas)} falas, {dur / 60:.1f} min de áudio em {(time.time() - ti) / 60:.1f} min")
            for ini, fim, texto in falas:
                linhas_csv.append([pescaria, video.name, fmt_csv(ini), fmt_csv(fim), texto])
        except Exception as e:  # um vídeo com problema não derruba o lote
            print(f"    ERRO: {e}")
            falhas.append((video, str(e)))

    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["pescaria", "arquivo", "inicio", "fim", "fala"])
        w.writerows(linhas_csv)

    print(f"\nPronto em {(time.time() - t0) / 60:.1f} min. {len(linhas_csv)} falas no CSV: {csv_path}")
    if falhas:
        print(f"{len(falhas)} vídeo(s) com erro:")
        for v, e in falhas:
            print(f"  {v}: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
