"""Identifica sons (carretilha, splash, grito, risada...) com o modelo CLAP, sem treino.

O CLAP compara cada janela de áudio com as descrições em texto de `sons.json`
(na pasta da habilidade) e diz qual combina mais. Para reconhecer um som novo
ou corrigir um que erra muito, basta editar as descrições, sem programar nada.

Precisa de: pip install torch --index-url https://download.pytorch.org/whl/cpu
            pip install transformers
Na primeira vez o modelo (~600 MB) é baixado do HuggingFace.
"""

import hashlib
import json
from pathlib import Path

import numpy as np

TAXA_CLAP = 48000
CONFIG = Path(__file__).resolve().parent.parent / "sons.json"


def carregar_config():
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    cfg["assinatura"] = hashlib.sha1(CONFIG.read_bytes()).hexdigest()[:12]
    return cfg


def disponivel() -> str | None:
    """None se dá para classificar; senão, o motivo."""
    try:
        import torch  # noqa: F401
        import transformers  # noqa: F401
    except ImportError as e:
        return f"faltando {e.name} (veja o cabeçalho de sons.py para instalar)"
    return None


def _vetor(saida, *nomes):
    """get_*_features devolve tensor em umas versões do transformers e objeto em outras."""
    import torch

    if isinstance(saida, torch.Tensor):
        return saida
    for n in nomes:
        v = getattr(saida, n, None)
        if v is not None:
            return v
    raise TypeError(f"saída inesperada do CLAP: {type(saida).__name__}")


class ClassificadorSons:
    def __init__(self, cfg=None, modelo=None, processador=None):
        import torch

        self.torch = torch
        self.cfg = cfg or carregar_config()
        if modelo is None:
            from transformers import ClapModel, ClapProcessor

            processador = ClapProcessor.from_pretrained(self.cfg["modelo"])
            modelo = ClapModel.from_pretrained(self.cfg["modelo"])
        self.modelo, self.proc = modelo.eval(), processador
        prompts = [r["prompt"] for r in self.cfg["rotulos"]]
        with torch.no_grad():
            txt = self.proc.tokenizer(prompts, padding=True, return_tensors="pt")
            t = _vetor(self.modelo.get_text_features(**txt), "text_embeds", "pooler_output")
        self.texto = t / t.norm(dim=-1, keepdim=True)
        self.escala = float(self.modelo.logit_scale_a.detach().exp()) if hasattr(self.modelo, "logit_scale_a") else 100.0

    def _probs(self, janelas):
        fe = self.proc.feature_extractor
        # o modo de entrada precisa casar com o modelo: "fusion" (4 canais) só nos modelos *-fused
        fusao = getattr(getattr(self.modelo.config, "audio_config", None), "enable_fusion", False)
        entrada = fe(janelas, sampling_rate=TAXA_CLAP, return_tensors="pt",
                     truncation="fusion" if fusao else "rand_trunc", padding="repeatpad")
        with self.torch.no_grad():
            a = _vetor(self.modelo.get_audio_features(**entrada), "audio_embeds", "pooler_output")
        a = a / a.norm(dim=-1, keepdim=True)
        return (self.escala * a @ self.texto.T).softmax(dim=-1).numpy()

    def classificar(self, audio: np.ndarray, lote=8):
        """Lista de janelas: (inicio, fim, nome_do_som, probabilidade)."""
        jan, passo = self.cfg["janela_s"], self.cfg["passo_s"]
        n_jan, n_passo = int(jan * TAXA_CLAP), int(passo * TAXA_CLAP)
        inicios = list(range(0, max(1, len(audio) - n_jan + n_passo), n_passo))
        nomes = [r["nome"] for r in self.cfg["rotulos"]]
        saida = []
        for k in range(0, len(inicios), lote):
            grupo = inicios[k:k + lote]
            probs = self._probs([audio[i:i + n_jan] for i in grupo])
            for i, p in zip(grupo, probs):
                melhor = int(np.argmax(p))
                fim = min(i + n_jan, len(audio)) / TAXA_CLAP
                saida.append((i / TAXA_CLAP, fim, nomes[melhor], float(p[melhor])))
        return saida


def trechos_destaque(janelas, cfg):
    """Junta janelas seguidas com o mesmo som de destaque: [(inicio, fim, nome, prob_max)]."""
    destaque = {r["nome"] for r in cfg["rotulos"] if r.get("destaque")}
    trechos = []
    for a, b, nome, p in janelas:
        if nome not in destaque or p < cfg["prob_minima"]:
            continue
        if trechos and trechos[-1][2] == nome and a <= trechos[-1][1]:
            trechos[-1] = (trechos[-1][0], b, nome, max(trechos[-1][3], p))
        else:
            trechos.append((a, b, nome, p))
    return trechos


def som_em(janelas, cfg, ini, fim):
    """Som que mais aparece (com confiança) entre ini e fim, ou None."""
    contagem = {}
    for a, b, nome, p in janelas:
        if b > ini and a < fim and p >= cfg["prob_minima"]:
            contagem[nome] = contagem.get(nome, 0) + p
    return max(contagem, key=contagem.get) if contagem else None
