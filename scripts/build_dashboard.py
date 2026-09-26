"""
Monta o painel de 3 páginas a partir da análise (analise_estoque.csv +
tendencia_mensal.csv):

  docs/index.html     Executivo   — KPIs, Pareto, tendência, categoria %
  docs/compras.html   Compras     — excesso por fornecedor e por comprador
  docs/operacao.html  Operação    — catálogo completo com busca e filtros

Os três consomem o mesmo docs/data.js (uma fonte de dados só), e
compartilham docs/styles.css.
"""

import os
import json
import numpy as np
import pandas as pd

BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(BASE_DIR, "..", "data")
DOCS_DIR = os.path.join(BASE_DIR, "..", "docs")
os.makedirs(DOCS_DIR, exist_ok=True)

df = pd.read_csv(os.path.join(DATA_DIR, "analise_estoque.csv"))
tendencia = pd.read_csv(os.path.join(DATA_DIR, "tendencia_mensal.csv"))

categorias = sorted(df["categoria"].unique().tolist())
fornecedores = sorted(df["fornecedor"].unique().tolist())
compradores = sorted(df["comprador"].unique().tolist())
status_list = ["Saudável", "Excesso de estoque", "Risco de ruptura"]
urgencia_list = ["OK", "Atenção", "Urgente"]

# ---------------------------------------------------------------
# KPIs gerais
# ---------------------------------------------------------------
kpis = {
    "capitalLiberavel": round(float(df["capital_liberavel"].sum()), 2),
    "lucroRisco": round(float(df["lucro_em_risco"].sum()), 2),
    "capitalTotalInvestido": round(float(df["capital_investido_atual"].sum()), 2),
    "nExcesso": int((df["status"] == "Excesso de estoque").sum()),
    "nRisco": int((df["status"] == "Risco de ruptura").sum()),
    "nSaudavel": int((df["status"] == "Saudável").sum()),
    "nUrgente": int((df["urgencia"] == "Urgente").sum()),
    "nAtencao": int((df["urgencia"] == "Atenção").sum()),
    "nOk": int((df["urgencia"] == "OK").sum()),
    "nTotal": int(len(df)),
}

# ---------------------------------------------------------------
# Pareto de capital liberável (quantos SKUs concentram o excesso)
# ---------------------------------------------------------------
pareto_df = df[df["capital_liberavel"] > 0].sort_values("capital_liberavel", ascending=False).reset_index(drop=True)
total_liberavel = pareto_df["capital_liberavel"].sum()
pareto_df["cum_pct"] = pareto_df["capital_liberavel"].cumsum() / total_liberavel * 100
pareto_top = pareto_df.head(30)
pareto_json = [
    [r["produto_nome"], round(float(r["capital_liberavel"]), 2), round(float(r["cum_pct"]), 1)]
    for _, r in pareto_top.iterrows()
]
# leitura rápida: quantos SKUs (do total com excesso) somam até 80%
n_skus_80pct = int((pareto_df["cum_pct"] <= 80).sum()) + 1
n_skus_80pct = min(n_skus_80pct, len(pareto_df))

# ---------------------------------------------------------------
# Participação por categoria
# ---------------------------------------------------------------
cap_categoria = df.groupby("categoria")["capital_liberavel"].sum().sort_values(ascending=False)
cap_categoria = cap_categoria[cap_categoria > 0]
total_cat = cap_categoria.sum()
categoria_json = [
    [cat, round(float(v), 2), round(float(v / total_cat * 100), 1)]
    for cat, v in cap_categoria.items()
]

# ---------------------------------------------------------------
# Tendência 6 meses
# ---------------------------------------------------------------
tendencia_json = [
    [
        r["mes"], round(float(r["capital_liberavel_total"]), 2),
        round(float(r["lucro_risco_total"]), 2), int(r["n_excesso"]), int(r["n_risco"]),
    ]
    for _, r in tendencia.iterrows()
]

# ---------------------------------------------------------------
# Por fornecedor e por comprador (página Compras)
# ---------------------------------------------------------------
def agrega_por(coluna):
    g = df.groupby(coluna).agg(
        capital_liberavel=("capital_liberavel", "sum"),
        lucro_em_risco=("lucro_em_risco", "sum"),
        capital_investido=("capital_investido_atual", "sum"),
        n_excesso=("status", lambda s: (s == "Excesso de estoque").sum()),
        n_risco=("status", lambda s: (s == "Risco de ruptura").sum()),
        n_skus=("sku_id", "count"),
    ).reset_index().sort_values("capital_liberavel", ascending=False)
    return [
        [
            r[coluna], round(float(r["capital_liberavel"]), 2), round(float(r["lucro_em_risco"]), 2),
            round(float(r["capital_investido"]), 2), int(r["n_excesso"]), int(r["n_risco"]), int(r["n_skus"]),
        ]
        for _, r in g.iterrows()
    ]

por_fornecedor_json = agrega_por("fornecedor")
por_comprador_json = agrega_por("comprador")

# ---------------------------------------------------------------
# Catálogo completo (página Operação) — usado por busca e filtros
# ---------------------------------------------------------------
cat_idx = {c: i for i, c in enumerate(categorias)}
forn_idx = {c: i for i, c in enumerate(fornecedores)}
comp_idx = {c: i for i, c in enumerate(compradores)}
sta_idx = {c: i for i, c in enumerate(status_list)}
urg_idx = {c: i for i, c in enumerate(urgencia_list)}

def faixa_cobertura(dias):
    if not np.isfinite(dias):
        return 3  # 180+
    if dias <= 30:
        return 0
    if dias <= 90:
        return 1
    if dias <= 180:
        return 2
    return 3

def linha_catalogo(r):
    return [
        r["sku_id"], r["produto_nome"], cat_idx[r["categoria"]], forn_idx[r["fornecedor"]],
        comp_idx[r["comprador"]], sta_idx[r["status"]], urg_idx[r["urgencia"]],
        round(float(r["estoque_atual"]), 1), round(min(float(r["giro_anual"]), 30), 2),
        round(min(float(r["dias_cobertura_atual"]), 999), 1), round(float(r["cobertura_alvo_dias"]), 0),
        faixa_cobertura(r["dias_cobertura_atual"]), round(float(r["margem_unitaria"]), 2),
        round(float(r["capital_liberavel"]), 2), round(float(r["lucro_em_risco"]), 2),
        r["ultima_compra_mes"],
    ]

catalogo_json = df.apply(linha_catalogo, axis=1).tolist()

# ---------------------------------------------------------------
# Monta o payload compartilhado
# ---------------------------------------------------------------
payload = {
    "categorias": categorias,
    "fornecedores": fornecedores,
    "compradores": compradores,
    "status": status_list,
    "urgencia": urgencia_list,
    "faixasCobertura": ["0–30 dias", "30–90 dias", "90–180 dias", "180+ dias"],
    "kpis": kpis,
    "pareto": pareto_json,
    "nSkus80pct": n_skus_80pct,
    "nSkusComExcesso": int(len(pareto_df)),
    "categoriaParticipacao": categoria_json,
    "tendencia": tendencia_json,
    "porFornecedor": por_fornecedor_json,
    "porComprador": por_comprador_json,
    "catalogo": catalogo_json,
    "catalogoColunas": [
        "sku_id", "produto_nome", "categoriaIdx", "fornecedorIdx", "compradorIdx",
        "statusIdx", "urgenciaIdx", "estoqueAtual", "giroAnual", "diasCobertura",
        "coberturaAlvo", "faixaCoberturaIdx", "margemUnitaria", "capitalLiberavel",
        "lucroEmRisco", "ultimaCompraMes",
    ],
}

data_js = "const DASHBOARD_DATA = " + json.dumps(payload, separators=(",", ":")) + ";"
with open(os.path.join(DOCS_DIR, "data.js"), "w", encoding="utf-8") as f:
    f.write(data_js)

print("data.js gerado:", round(len(data_js) / 1_000_000, 3), "MB")
print(f"Pareto: {n_skus_80pct} SKUs concentram 80% dos R$ {total_liberavel:,.0f} liberáveis".replace(",", "."))

# ---------------------------------------------------------------
# Copia o CSS compartilhado
# ---------------------------------------------------------------
with open(os.path.join(BASE_DIR, "styles.css"), "r", encoding="utf-8") as f:
    css = f.read()
with open(os.path.join(DOCS_DIR, "styles.css"), "w", encoding="utf-8") as f:
    f.write(css)

# ---------------------------------------------------------------
# Monta as 3 páginas HTML a partir dos templates
# ---------------------------------------------------------------
paginas = ["template_executivo.html", "template_compras.html", "template_operacao.html"]
saidas = ["index.html", "compras.html", "operacao.html"]

for template_nome, saida_nome in zip(paginas, saidas):
    with open(os.path.join(BASE_DIR, template_nome), "r", encoding="utf-8") as f:
        html = f.read()
    with open(os.path.join(DOCS_DIR, saida_nome), "w", encoding="utf-8") as f:
        f.write(html)
    print(f"{saida_nome} gerado")
