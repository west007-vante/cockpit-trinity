#!/usr/bin/env python3
"""Peças compartilhadas — nomes das listas, mapeamentos e o índice do quadro.

Fica separado pra migrar_quadro, roteador, agendador e espelho falarem a mesma
língua. Mudou o nome de uma lista? Muda aqui e o sistema inteiro acompanha.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

L_ENTRADA    = "📥 Entrada"
L_TAREFAS    = "📋 Tarefas"
L_HOJE       = "🗓️ Hoje"
L_FAZENDO    = "🔨 Fazendo"
L_PARADO     = "⏸️ Parado"
L_ADIADO     = "🕐 Adiado"
L_FEITO      = "✅ Feito"
L_DESCARTADO = "🗑️ Descartado"
L_CLIENTES   = "👥 Clientes"
L_BANCADA    = "🧪 Bancada"

# Listas em que um card é considerado "vivo" — o agendador só mexe nessas.
VIVAS = (L_ENTRADA, L_TAREFAS, L_HOJE, L_FAZENDO)
# Listas em que o robô NUNCA mexe sozinho: decisão humana mora aqui.
INTOCAVEIS = (L_DESCARTADO, L_ADIADO, L_PARADO)

AREAS = {
    "A": "MERCADOR · Mercado Livre", "B": "Shopee · Upseller", "C": "GF Cortes",
    "D": "VERSO · EcommerceVerso", "E": "Tikebum", "F": "Máquina Zero→Venda",
    "G": "Infra e decisões", "H": "Entrega Steve → Tikebum",
    "I": "A Cara do Steve · Comercial",
}

ETIQUETA_DA_AREA = {
    "A": "A · MERCADOR", "B": "B · Shopee", "C": "C · GF Cortes", "D": "D · VERSO",
    "E": "E · Tikebum", "F": "F · Zero→Venda", "G": "G · Infra", "H": "H · Entrega",
    "I": "I · Comercial",
}
ETIQUETA_DO_TIPO = {"obra": "🔨 obra", "cliente": "🎯 cliente", "bancada": "🧪 bancada"}


def lista_da_tarefa(faixa, status):
    """Onde uma tarefa do Quadro da Obra nasce no Trello.

    O estado manda mais que a faixa: pronto é pronto, esperar terceiro é parado.
    """
    if status == "pronto":
        return L_FEITO
    if status == "terceiro":
        return L_PARADO
    if faixa in ("agora", "relogio"):
        return L_HOJE
    if faixa == "fila":
        return L_ADIADO
    return L_TAREFAS


def lista_do_veredito(tipo):
    """Onde um trabalho capturado do worklog nasce, segundo o classificador."""
    return {"obra": L_TAREFAS, "cliente": L_TAREFAS,
            "bancada": L_BANCADA}.get(tipo, L_ENTRADA)


class Indice:
    """Índice vivo do quadro: nome → id, pra não pedir a mesma coisa 50 vezes.

    O Trello limita 300 requisições por 10 s por chave. Numa migração de 53
    tarefas isso estoura fácil se cada card pedir a lista de listas de novo.
    """

    def __init__(self, t):
        self.t = t
        self.listas = {l["name"]: l["id"] for l in (t.listas() or [])}
        self.listas_por_id = {v: k for k, v in self.listas.items()}
        self.etiquetas = {(e.get("name") or ""): e["id"] for e in (t.etiquetas() or [])}
        self.membros = {}
        for m in (t.membros() or []):
            for chave in (m.get("username"), (m.get("fullName") or "").lower()):
                if chave:
                    self.membros[chave] = m["id"]
        self._cards = None

    def lista(self, nome):
        if nome not in self.listas:
            raise KeyError(
                f"a lista {nome!r} não existe no quadro. "
                f"Rode:  python3 ~/trinity/trello/bootstrap_board.py")
        return self.listas[nome]

    def etiqueta(self, nome):
        return self.etiquetas.get(nome)

    def etiquetas_de(self, tipo=None, area=None):
        ids = []
        for nome in (ETIQUETA_DO_TIPO.get(tipo), ETIQUETA_DA_AREA.get(area)):
            if nome and self.etiquetas.get(nome):
                ids.append(self.etiquetas[nome])
        return ids

    def membro(self, quem):
        """Aceita usuário do Trello ou o nome como está no rotas.json."""
        q = (quem or "").lower().lstrip("@")
        return self.membros.get(q)

    def cards(self, recarregar=False):
        if self._cards is None or recarregar:
            self._cards = self.t.cards_do_board() or []
        return self._cards

    def por_task_id(self, recarregar=False):
        """#A1 → card. É o que impede a migração de duplicar quando roda de novo."""
        from cartao import id_do_nome, ler_desc
        m = {}
        for c in self.cards(recarregar):
            tid = id_do_nome(c.get("name")) or (ler_desc(c.get("desc")) or {}).get("id")
            if tid:
                m[tid] = c
        return m

    def por_db_sid(self, recarregar=False):
        """session_id do worklog → card. Impede o roteador de repetir o mesmo trabalho."""
        from cartao import ler_desc
        m = {}
        for c in self.cards(recarregar):
            d = ler_desc(c.get("desc")) or {}
            if d.get("db_sid"):
                m[d["db_sid"]] = c
        return m
