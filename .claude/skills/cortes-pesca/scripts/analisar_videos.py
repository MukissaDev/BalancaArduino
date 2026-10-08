"""Prepara os vídeos para o Claude "assistir": folhas de quadros + picos de áudio + fala.

Para cada vídeo cria, em <raiz>/Editados_IA/_analise/<video>/:
  - folha_01.jpg, folha_02.jpg...  grade de quadros com o tempo de cada um
  - resumo.md                      duração, formato, momentos de áudio alto, falas do .srt
E um índice geral em <raiz>/Editados_IA/_analise/indice.md.

Uso:
    python analisar_videos.py "C:\\Videos\\Instagram" --excluir Editados
    python analisar_videos.py detalhe "C:\\...\\video.mp4" 12.5 20 --passo 0.5
        (folha mais densa de um trecho, para acertar o ponto exato de corte)
"""

import argparse
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).parent))
from transcrever_videos import PASTA_SAIDA, TAXA, ler_audio, ler_srt, listar_videos  # noqa: E402

COLUNAS, LINHAS = 4, 3
LARGURA_QUADRO = 360


def info_video(video: Path) -> dict:
    """Duração e presença de áudio, lidas da saída do `ffmpeg -i` (dispensa ffprobe)."""
    err = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(video)],
                         capture_output=True).stderr.decode("utf-8", "replace")
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", err)
    if not m:
        raise RuntimeError(f"ffmpeg não conseguiu ler o vídeo: {err.strip().splitlines()[-1:]}")
    h, mi, s = m.groups()
    return {"duracao": int(h) * 3600 + int(mi) * 60 + float(s),
            "tem_audio": bool(re.search(r"Stream #.*Audio:", err))}


def extrair_quadros(video: Path, passo: float, ini: float = 0.0, fim: float | None = None):
    """Lista de (tempo_em_segundos, Image) a cada `passo` segundos (com a rotação já aplicada)."""
    with tempfile.TemporaryDirectory() as tmp:
        cmd = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error"]
        if ini:
            cmd += ["-ss", f"{ini:.3f}"]
        if fim is not None:
            cmd += ["-t", f"{fim - ini:.3f}"]
        cmd += ["-i", str(video), "-an", "-vf", f"fps=1/{passo},scale={LARGURA_QUADRO}:-2",
                "-q:v", "4", str(Path(tmp) / "q_%05d.jpg")]
        proc = subprocess.run(cmd, capture_output=True)
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.decode("utf-8", "replace").strip())
        quadros = []
        for i, arq in enumerate(sorted(Path(tmp).glob("q_*.jpg"))):
            with Image.open(arq) as img:
                quadros.append((ini + i * passo, img.convert("RGB")))
        return quadros


def fonte(tamanho):
    try:
        return ImageFont.load_default(size=tamanho)
    except TypeError:  # Pillow antigo
        return ImageFont.load_default()


def mmss(t: float) -> str:
    t = max(0.0, t)
    return f"{int(t // 60):02d}:{t % 60:04.1f}"


def montar_folhas(quadros, destino_base: Path):
    """Grades COLUNAS x LINHAS com o tempo escrito em cada quadro. Devolve [(arquivo, t0, t1)]."""
    if not quadros:
        return []
    w, h = quadros[0][1].size
    f = fonte(max(18, w // 12))
    por_folha = COLUNAS * LINHAS
    folhas = []
    for n in range(0, len(quadros), por_folha):
        grupo = quadros[n:n + por_folha]
        linhas = (len(grupo) + COLUNAS - 1) // COLUNAS
        folha = Image.new("RGB", (COLUNAS * w, linhas * h), "black")
        d = ImageDraw.Draw(folha)
        for i, (t, img) in enumerate(grupo):
            x, y = (i % COLUNAS) * w, (i // COLUNAS) * h
            folha.paste(img.resize((w, h)), (x, y))
            rotulo = mmss(t)
            caixa = d.textbbox((x + 6, y + 6), rotulo, font=f)
            d.rectangle((caixa[0] - 4, caixa[1] - 3, caixa[2] + 4, caixa[3] + 3), fill="black")
            d.text((x + 6, y + 6), rotulo, fill="yellow", font=f)
        arq = destino_base.parent / f"{destino_base.name}_{n // por_folha + 1:02d}.jpg"
        folha.save(arq, quality=82)
        folhas.append((arq, grupo[0][0], grupo[-1][0]))
    return folhas


def picos_audio(audio: np.ndarray, janela=0.5, maximo=8):
    """Trechos bem mais altos que o normal do vídeo (grito, comemoração, carretilha cantando...)."""
    n = int(TAXA * janela)
    if len(audio) < n * 4:
        return [], None
    blocos = audio[: len(audio) // n * n].reshape(-1, n)
    db = 20 * np.log10(np.sqrt((blocos ** 2).mean(axis=1)) + 1e-9)
    mediana = float(np.median(db))
    limiar = max(float(np.percentile(db, 90)), mediana + 8)
    trechos, atual = [], None
    for i, v in enumerate(db):
        if v >= limiar:
            if atual and i - atual[1] <= 2:  # junta trechos separados por até 1 s
                atual[1], atual[2] = i, max(atual[2], v)
            else:
                atual = [i, i, v]
                trechos.append(atual)
    trechos = sorted(trechos, key=lambda t: -t[2])[:maximo]
    return sorted(((a * janela, (b + 1) * janela, v - mediana) for a, b, v in trechos)), mediana


def analisar(video: Path, raiz: Path, pasta_analise: Path, refazer: bool) -> dict:
    rel = video.relative_to(raiz)
    destino = pasta_analise / re.sub(r"[^\w.-]+", "_", str(rel.with_suffix("")))
    resumo = destino / "resumo.md"
    srt = video.with_suffix(".srt")
    atual = resumo.exists() and not refazer and (
        not srt.exists() or srt.stat().st_mtime <= resumo.stat().st_mtime)
    info = info_video(video)
    falas = ler_srt(srt) if srt.exists() else []
    if atual:
        return {"rel": rel, "resumo": resumo, "falas": len(falas), "pulado": True, **info}

    destino.mkdir(parents=True, exist_ok=True)
    for velho in destino.glob("folha_*.jpg"):
        velho.unlink()
    passo = max(2.0, info["duracao"] / 36)  # até ~36 quadros (3 folhas) por vídeo
    quadros = extrair_quadros(video, passo)
    folhas = montar_folhas(quadros, destino / "folha")
    w, h = quadros[0][1].size if quadros else (0, 0)
    picos, mediana = picos_audio(ler_audio(video)) if info["tem_audio"] else ([], None)

    linhas = [
        f"# {rel}", "",
        f"- Arquivo: `{video}`",
        f"- Duração: {mmss(info['duracao'])} ({info['duracao']:.1f} s)",
        f"- Formato: {'vertical' if h > w else 'horizontal' if w > h else 'quadrado'} ({w}x{h} na folha)",
        f"- Áudio: {'sim' if info['tem_audio'] else 'NÃO'}",
        f"- Quadros a cada {passo:.1f} s nas folhas:",
    ]
    linhas += [f"  - `{a.name}`: {mmss(t0)} a {mmss(t1)}" for a, t0, t1 in folhas]
    linhas += ["", "## Momentos de áudio alto"]
    if picos:
        linhas.append(f"(dB acima do nível típico do vídeo, que é {mediana:.0f} dBFS)")
        linhas += [f"- {mmss(a)}–{mmss(b)}: +{d:.0f} dB" for a, b, d in picos]
    else:
        linhas.append("- nenhum destaque" if info["tem_audio"] else "- vídeo sem áudio")
    linhas += ["", "## Fala (do .srt)"]
    linhas += [f"- [{mmss(a)}–{mmss(b)}] {t}" for a, b, t in falas] or [
        "- sem .srt (rode a transcrição antes)" if not srt.exists() else "- nenhuma fala detectada"]
    resumo.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return {"rel": rel, "resumo": resumo, "falas": len(falas), "pulado": False, **info}


def cmd_lote(args):
    raiz = args.pasta.resolve()
    pasta_analise = raiz / PASTA_SAIDA / "_analise"
    videos = listar_videos(raiz, args.excluir)
    if not videos:
        sys.exit(f"Nenhum vídeo encontrado em {raiz}")
    resultados, falhas = [], []
    for n, v in enumerate(videos, 1):
        print(f"[{n}/{len(videos)}] {v.relative_to(raiz)}", flush=True)
        try:
            resultados.append(analisar(v, raiz, pasta_analise, args.refazer))
        except Exception as e:
            print(f"    ERRO: {e}")
            falhas.append((v, str(e)))

    total = sum(r["duracao"] for r in resultados)
    linhas = [f"# Índice da análise — {raiz}", "",
              f"{len(resultados)} vídeos, {total / 60:.0f} min no total.", "",
              "| pasta | arquivo | duração | falas | resumo |", "|---|---|---|---|---|"]
    for r in resultados:
        pasta = r["rel"].parent.as_posix() if r["rel"].parent != Path(".") else "(raiz)"
        resumo = r["resumo"].relative_to(pasta_analise).as_posix()
        linhas.append(f"| {pasta} | {r['rel'].name} | {mmss(r['duracao'])} | {r['falas']} | `{resumo}` |")
    if falhas:
        linhas += ["", "## Vídeos com erro"] + [f"- `{v}`: {e}" for v, e in falhas]
    indice = pasta_analise / "indice.md"
    pasta_analise.mkdir(parents=True, exist_ok=True)
    indice.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    print(f"\nÍndice: {indice}")
    if falhas:
        sys.exit(1)


def cmd_detalhe(args):
    video = args.video.resolve()
    quadros = extrair_quadros(video, args.passo, args.inicio, args.fim)
    destino = args.saida or video.parent
    destino.mkdir(parents=True, exist_ok=True)
    stem = re.sub(r"[^\w-]+", "_", video.stem)
    base = destino / f"detalhe_{stem}_{args.inicio:.1f}-{args.fim:.1f}"
    for arq, t0, t1 in montar_folhas(quadros, base):
        print(f"{arq}  ({mmss(t0)} a {mmss(t1)})")


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if len(sys.argv) > 1 and sys.argv[1] == "detalhe":
        ap = argparse.ArgumentParser(prog="analisar_videos.py detalhe")
        ap.add_argument("video", type=Path)
        ap.add_argument("inicio", type=float)
        ap.add_argument("fim", type=float)
        ap.add_argument("--passo", type=float, default=0.5)
        ap.add_argument("--saida", type=Path, help="pasta das folhas (padrão: ao lado do vídeo)")
        cmd_detalhe(ap.parse_args(sys.argv[2:]))
    else:
        ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
        ap.add_argument("pasta", type=Path)
        ap.add_argument("--excluir", nargs="+", default=[], metavar="PASTA")
        ap.add_argument("--refazer", action="store_true")
        cmd_lote(ap.parse_args())


if __name__ == "__main__":
    main()
