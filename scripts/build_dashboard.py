import os
import json
import numpy as np
import pandas as pd

BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(BASE_DIR, "..", "data")
DOCS_DIR = os.path.join(BASE_DIR, "..", "docs")
os.makedirs(DOCS_DIR, exist_ok=True)

df = pd.read_csv(os.path.join(DATA_DIR, "analise_estoque.csv"))

categorias = sorted(df["categoria"].unique().tolist())
status_list = ["Saudável", "Excesso de estoque", "Risco de ruptura"]

cat_idx = {c: i for i, c in enumerate(categorias)}
sta_idx = {c: i for i, c in enumerate(status_list)}

def linha_sku(r):
    giro = min(r["giro_anual"], 20)  # limita outliers extremos pro gráfico ficar legível
    cobertura = min(r["dias_cobertura_atual"], 400) if np.isfinite(r["dias_cobertura_atual"]) else 400
    return [
        cat_idx[r["categoria"]],
        round(float(giro), 2),
        round(float(cobertura), 1),
        sta_idx[r["status"]],
        round(float(r["capital_investido_atual"]), 2),
        round(float(r["capital_liberavel"]), 2),
        round(float(r["lucro_em_risco"]), 2),
    ]

skus = df.apply(linha_sku, axis=1).tolist()

capital_liberavel_por_categoria = (
    df.groupby("categoria")["capital_liberavel"].sum().sort_values(ascending=False)
)
cap_por_categoria_json = [
    [cat, round(float(v), 2)] for cat, v in capital_liberavel_por_categoria.items() if v > 0
]

def acao_recomendada(row):
    if row["status"] == "Excesso de estoque":
        return f"Reduzir reposição / considerar promoção — R$ {row['capital_liberavel']:,.0f} parados".replace(",", ".")
    if row["status"] == "Risco de ruptura":
        return f"Repor com urgência — até R$ {row['lucro_em_risco']:,.0f} em lucro sob risco".replace(",", ".")
    return "Manter política atual"

df["acao_recomendada"] = df.apply(acao_recomendada, axis=1)
df["valor_oportunidade"] = df["capital_liberavel"] + df["lucro_em_risco"]

# o valor em risco de ruptura costuma ser bem menor em R$ do que o capital parado
# em excesso, então um ranking único faz os riscos de ruptura desaparecerem da tabela.
# Aqui pegamos o top de cada tipo separadamente, pra manter as duas histórias visíveis.
top_excesso = df[df["status"] == "Excesso de estoque"].sort_values(
    "valor_oportunidade", ascending=False
).head(15)
top_risco = df[df["status"] == "Risco de ruptura"].sort_values(
    "valor_oportunidade", ascending=False
).head(10)
top_oportunidades = pd.concat([top_risco, top_excesso]).sort_values(
    "valor_oportunidade", ascending=False
)

top_oportunidades_json = [
    [
        r["produto_nome"], r["categoria"], r["status"],
        round(float(r["valor_oportunidade"]), 2), r["acao_recomendada"],
    ]
    for _, r in top_oportunidades.iterrows()
]

kpis = {
    "capitalLiberavel": round(float(df["capital_liberavel"].sum()), 2),
    "lucroRisco": round(float(df["lucro_em_risco"].sum()), 2),
    "capitalTotalInvestido": round(float(df["capital_investido_atual"].sum()), 2),
    "nExcesso": int((df["status"] == "Excesso de estoque").sum()),
    "nRisco": int((df["status"] == "Risco de ruptura").sum()),
    "nSaudavel": int((df["status"] == "Saudável").sum()),
    "nTotal": int(len(df)),
}

payload = {
    "skus": skus,
    "categorias": categorias,
    "status": status_list,
    "capPorCategoria": cap_por_categoria_json,
    "topOportunidades": top_oportunidades_json,
    "kpis": kpis,
}

data_json = json.dumps(payload, separators=(",", ":"))

with open(os.path.join(BASE_DIR, "dashboard_template.html"), "r", encoding="utf-8") as f:
    template = f.read()

html = template.replace("__DATA_JSON__", data_json)

with open(os.path.join(DOCS_DIR, "index.html"), "w", encoding="utf-8") as f:
    f.write(html)

print("index.html gerado em docs/, tamanho:", round(len(html) / 1_000_000, 2), "MB")
