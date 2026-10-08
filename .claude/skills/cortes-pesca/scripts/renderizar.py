"""Renderiza os cortes descritos em um plano.json (formato em references/plano.md).

Cada corte junta 1 ou mais clipes (de um ou de vários vídeos), enquadra em
vertical 1080x1920 ou horizontal 1920x1080, normaliza o áudio, queima a
legenda tirada do .srt original e grava em <raiz>/Editados_IA/<nome>.mp4,
mais <nome>.txt com título/descrição/hashtags e o relatorio.md geral.

Uso:
    python renderizar.py "C:\\...\\Instagram\\Editados_IA\\plano.json"
    python renderizar.py plano.json --so 01_tucuna_explodindo --rapido
    python renderizar.py plano.json --validar      # só confere o plano
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from analisar_videos import info_video  # noqa: E402
from transcrever_videos import PASTA_SAIDA, ler_srt  # noqa: E402

TAMANHOS = {"vertical": (1080, 1920), "horizontal": (1920, 1080)}
LIMITES = {"shorts": 180, "reels": 180, "tiktok": 600}  # segundos; acima disso só avisa


def segundos(v) -> float:
    """Aceita 12.5, "12.5", "01:23", "01:23.4" ou "1:02:03"."""
    if isinstance(v, (int, float)):
        return float(v)
    partes = [float(p) for p in str(v).strip().split(":")]
    t = 0.0
    for p in partes:
        t = t * 60 + p
    return t


def tempo_ass(t: float) -> str:
    cs = int(round(max(0.0, t) * 100))
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def texto_ass(t: str) -> str:
    return t.replace("\\", "/").replace("{", "(").replace("}", ")").replace("\n", "\\N")


def montar_ass(clipe, formato, legenda: bool) -> str:
    w, h = TAMANHOS[formato]
    vertical = formato == "vertical"
    cab = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Legenda,Arial,{70 if vertical else 56},&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,5,0,2,80,80,{420 if vertical else 70},1
Style: Topo,Arial,{84 if vertical else 64},&H0000FFFF,&H0000FFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,6,0,8,60,60,{220 if vertical else 60},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    ini, fim, vel, dur = clipe["ini"], clipe["fim"], clipe["vel"], clipe["dur"]
    eventos = []
    if legenda:
        for a, b, txt in clipe["falas"]:
            a, b = max(a, ini), min(b, fim)
            if b - a >= 0.2:
                eventos.append(f"Dialogue: 0,{tempo_ass((a - ini) / vel)},{tempo_ass((b - ini) / vel)},Legenda,,0,0,0,,{texto_ass(txt)}")
    if clipe.get("texto_tela"):
        eventos.append(f"Dialogue: 1,{tempo_ass(0)},{tempo_ass(dur)},Topo,,0,0,0,,{texto_ass(clipe['texto_tela'])}")
    return cab + "\n".join(eventos) + "\n"


def filtro(clipe, formato) -> str:
    w, h = TAMANHOS[formato]
    vel = clipe["vel"]
    v = f"[0:v]setpts=PTS/{vel}," if vel != 1 else "[0:v]"
    if clipe["enquadramento"] == "desfoque":
        v += (f"split[a][b];[a]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},"
              f"boxblur=20:2,eq=brightness=-0.08[bg];[b]scale={w}:{h}:force_original_aspect_ratio=decrease[fg];"
              f"[bg][fg]overlay=(W-w)/2:(H-h)/2,")
    else:
        cx = clipe["centro_x"]
        v += (f"scale={w}:{h}:force_original_aspect_ratio=increase,"
              f"crop={w}:{h}:'min(max(iw*{cx}-{w}/2,0),iw-{w})':'(ih-{h})/2',")
    v += "fps=30,setsar=1,format=yuv420p,ass=c.ass[v]"
    d = clipe["dur"]
    if clipe["tem_audio"]:
        a = "[0:a]" + (f"atempo={vel}," if vel != 1 else "")
        a += "loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000,aformat=channel_layouts=stereo,"
    else:
        a = "[1:a]"
    a += f"afade=t=in:d=0.08,afade=t=out:st={max(0.0, d - 0.15):.3f}:d=0.15[a]"
    return v + ";" + a


def rodar(cmd, cwd=None):
    proc = subprocess.run(cmd, capture_output=True, cwd=cwd)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.decode("utf-8", "replace").strip()[-1500:])


def preparar(plano_path: Path):
    """Lê e valida o plano. Devolve (raiz, cortes normalizados, avisos, erros)."""
    plano = json.loads(plano_path.read_text(encoding="utf-8-sig"))
    raiz = Path(plano.get("pasta") or plano_path.parent.parent).resolve()
    cortes, avisos, erros, cache = [], [], [], {}
    nomes = set()
    for i, c in enumerate(plano.get("cortes", []), 1):
        nome = re.sub(r'[<>:"/\\|?*]+', "_", str(c.get("nome") or f"corte_{i:02d}")).strip()
        if nome in nomes:
            erros.append(f"{nome}: nome repetido")
        nomes.add(nome)
        formato = c.get("formato", "vertical")
        if formato not in TAMANHOS:
            erros.append(f"{nome}: formato '{formato}' inválido (use vertical ou horizontal)")
            continue
        clipes = []
        for j, cl in enumerate(c.get("clipes", []), 1):
            ref = f"{nome}, clipe {j}"
            arq = Path(cl.get("arquivo", ""))
            arq = arq if arq.is_absolute() else raiz / arq
            if not arq.is_file():
                erros.append(f"{ref}: arquivo não encontrado: {arq}")
                continue
            if arq not in cache:
                srt = arq.with_suffix(".srt")
                cache[arq] = (info_video(arq), ler_srt(srt) if srt.exists() else [])
            info, falas = cache[arq]
            ini, fim = segundos(cl.get("inicio", 0)), segundos(cl.get("fim", info["duracao"]))
            fim = min(fim, info["duracao"])
            vel = float(cl.get("velocidade", 1))
            if not 0.5 <= vel <= 2:
                erros.append(f"{ref}: velocidade {vel} fora de 0.5–2")
                continue
            if fim - ini < 0.5:
                erros.append(f"{ref}: trecho {ini:.1f}–{fim:.1f} s curto demais ou invertido")
                continue
            clipes.append({
                "arquivo": arq, "ini": ini, "fim": fim, "vel": vel, "dur": (fim - ini) / vel,
                "enquadramento": cl.get("enquadramento", "corte"),
                "centro_x": min(max(float(cl.get("centro_x", 0.5)), 0.0), 1.0),
                "texto_tela": cl.get("texto_tela", ""), "tem_audio": info["tem_audio"], "falas": falas,
            })
        if not clipes:
            erros.append(f"{nome}: nenhum clipe válido")
            continue
        dur = sum(cl["dur"] for cl in clipes)
        for p in c.get("plataformas", []):
            lim = LIMITES.get(str(p).lower())
            if lim and dur > lim:
                avisos.append(f"{nome}: {dur:.0f} s passa do limite de {lim} s do {p}")
        cortes.append({**c, "nome": nome, "formato": formato, "clipes": clipes, "dur": dur,
                       "legenda": c.get("legenda", True)})
    return raiz, cortes, avisos, erros


def renderizar(corte, saida: Path, preset: str):
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        partes = []
        for k, cl in enumerate(corte["clipes"]):
            (tmp / "c.ass").write_text(montar_ass(cl, corte["formato"], corte["legenda"]), encoding="utf-8")
            parte = tmp / f"parte_{k:03d}.mp4"
            cmd = ["ffmpeg", "-nostdin", "-y", "-hide_banner", "-loglevel", "error",
                   "-ss", f"{cl['ini']:.3f}", "-t", f"{cl['fim'] - cl['ini']:.3f}", "-i", str(cl["arquivo"])]
            if not cl["tem_audio"]:
                cmd += ["-f", "lavfi", "-t", f"{cl['dur']:.3f}", "-i", "anullsrc=r=48000:cl=stereo"]
            cmd += ["-filter_complex", filtro(cl, corte["formato"]), "-map", "[v]", "-map", "[a]",
                    "-c:v", "libx264", "-preset", preset, "-crf", "20",
                    "-c:a", "aac", "-b:a", "192k", "-t", f"{cl['dur']:.3f}", parte.name]
            rodar(cmd, cwd=tmp)  # cwd=tmp: o filtro ass lê "c.ass" sem dor de cabeça com C:\ no caminho
            partes.append(parte.name)
        (tmp / "lista.txt").write_text("".join(f"file '{p}'\n" for p in partes), encoding="utf-8")
        rodar(["ffmpeg", "-nostdin", "-y", "-hide_banner", "-loglevel", "error", "-f", "concat",
               "-safe", "0", "-i", "lista.txt", "-c", "copy", "-movflags", "+faststart", "final.mp4"], cwd=tmp)
        shutil.move(str(tmp / "final.mp4"), saida)


def mmss(t):
    return f"{int(t // 60):02d}:{t % 60:04.1f}"


def ficha(corte, raiz: Path) -> str:
    def rel(p):
        return p.relative_to(raiz).as_posix() if p.is_relative_to(raiz) else str(p)

    tags = corte.get("hashtags", [])
    linhas = [
        f"TÍTULO: {corte.get('titulo', '')}",
        f"PLATAFORMAS: {', '.join(corte.get('plataformas', []))}",
        f"FORMATO: {corte['formato']} — {corte['dur']:.1f} s", "",
        "DESCRIÇÃO:", corte.get("descricao", ""), "",
        "HASHTAGS: " + (" ".join(tags) if isinstance(tags, list) else str(tags)), "",
        "POR QUE ESTE CORTE: " + corte.get("justificativa", ""), "", "ORIGEM:",
    ]
    linhas += [f"  {rel(cl['arquivo'])}  {mmss(cl['ini'])}–{mmss(cl['fim'])}"
               + (f"  (velocidade {cl['vel']}x)" if cl["vel"] != 1 else "") for cl in corte["clipes"]]
    return "\n".join(linhas) + "\n"


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("plano", type=Path)
    ap.add_argument("--so", nargs="+", metavar="NOME", help="renderiza só estes cortes")
    ap.add_argument("--refazer", action="store_true", help="regrava cortes que já existem")
    ap.add_argument("--rapido", action="store_true", help="codificação rápida (prévia, arquivo maior)")
    ap.add_argument("--validar", action="store_true", help="só confere o plano, não renderiza")
    args = ap.parse_args()

    raiz, cortes, avisos, erros = preparar(args.plano.resolve())
    for a in avisos:
        print(f"AVISO: {a}")
    for e in erros:
        print(f"ERRO NO PLANO: {e}")
    print(f"{len(cortes)} corte(s) válidos, {sum(c['dur'] for c in cortes) / 60:.1f} min no total.")
    if args.validar or not cortes:
        sys.exit(1 if erros else 0)

    saida_dir = raiz / PASTA_SAIDA
    saida_dir.mkdir(exist_ok=True)
    falhas = []
    for n, c in enumerate(cortes, 1):
        if args.so and c["nome"] not in args.so:
            continue
        saida = saida_dir / f"{c['nome']}.mp4"
        (saida_dir / f"{c['nome']}.txt").write_text(ficha(c, raiz), encoding="utf-8")
        if saida.exists() and not args.refazer:
            print(f"[{n}/{len(cortes)}] {c['nome']} — já existe, pulando")
            continue
        print(f"[{n}/{len(cortes)}] {c['nome']} ({c['formato']}, {c['dur']:.0f} s, {len(c['clipes'])} clipe(s))...", flush=True)
        try:
            renderizar(c, saida, "veryfast" if args.rapido else "medium")
        except Exception as e:
            print(f"    ERRO: {e}")
            falhas.append(c["nome"])

    rel = ["# Cortes gerados", "", "| corte | formato | duração | plataformas | por quê |", "|---|---|---|---|---|"]
    for c in cortes:
        ok = (saida_dir / f"{c['nome']}.mp4").exists()
        rel.append(f"| {c['nome']}{'' if ok else ' (NÃO GERADO)'} | {c['formato']} | {c['dur']:.0f} s | "
                   f"{', '.join(c.get('plataformas', []))} | {c.get('justificativa', '').replace('|', '/')} |")
    (saida_dir / "relatorio.md").write_text("\n".join(rel) + "\n", encoding="utf-8")
    print(f"\nPronto. Cortes e relatório em {saida_dir}")
    if falhas or erros:
        sys.exit(1)


if __name__ == "__main__":
    main()
