"""
Transforma o histórico de estoque em uma lista priorizada de ações,
com o valor financeiro de cada uma.

Para cada SKU, usando os últimos 12 meses de histórico:
  - giro anual          = vendas dos últimos 12 meses / estoque médio no período
  - dias de cobertura   = estoque atual / venda média diária
  - status:
      "Risco de ruptura"   -> cobertura atual é menor que o lead time de reposição
      "Excesso de estoque" -> cobertura atual é mais que 2x o alvo de segurança
      "Saudável"           -> dentro da faixa esperada

Duas métricas de negócio saem disso, por SKU:
  - capital_liberavel  (R$): quanto dá pra tirar do estoque parado sem
                             arriscar falta, para SKUs com excesso
  - lucro_em_risco     (R$): margem que pode ser perdida nos próximos dias
                             se a reposição não chegar a tempo, para SKUs
                             com risco de ruptura

O resultado é salvo em data/analise_estoque.csv e usado para montar o painel.
"""

import os
import numpy as np
import pandas as pd

BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(BASE_DIR, "..", "data")

produtos = pd.read_csv(os.path.join(DATA_DIR, "produtos.csv"))
estoque = pd.read_csv(os.path.join(DATA_DIR, "estoque_mensal.csv"))

ULTIMO_MES = estoque["mes"].max()
meses_ordenados = sorted(estoque["mes"].unique())
ultimos_12 = meses_ordenados[-12:]

df_12m = estoque[estoque["mes"].isin(ultimos_12)]

agregado = df_12m.groupby("sku_id").agg(
    vendas_12m=("vendas_unidades", "sum"),
    estoque_medio_12m=("estoque_final", "mean"),
    dias_ruptura_12m=("dias_ruptura", "sum"),
).reset_index()

estoque_atual = (
    estoque[estoque["mes"] == ULTIMO_MES][["sku_id", "estoque_final"]]
    .rename(columns={"estoque_final": "estoque_atual"})
)

base = produtos.merge(agregado, on="sku_id").merge(estoque_atual, on="sku_id")

base["margem_unitaria"] = base["preco_venda"] - base["custo_unitario"]
base["vendas_media_diaria"] = base["vendas_12m"] / 365.0
base["giro_anual"] = base["vendas_12m"] / base["estoque_medio_12m"].replace(0, np.nan)
base["giro_anual"] = base["giro_anual"].fillna(0)
base["dias_cobertura_atual"] = np.where(
    base["vendas_media_diaria"] > 0,
    base["estoque_atual"] / base["vendas_media_diaria"],
    np.inf,
)

# alvo de cobertura de segurança: 2x o lead time (política razoável de estoque de segurança)
base["cobertura_alvo_dias"] = base["lead_time_dias"] * 2

def classificar(row):
    if row["dias_cobertura_atual"] < row["lead_time_dias"]:
        return "Risco de ruptura"
    if row["dias_cobertura_atual"] > row["cobertura_alvo_dias"] * 2:
        return "Excesso de estoque"
    return "Saudável"

base["status"] = base.apply(classificar, axis=1)

# capital liberável: unidades acima do alvo de cobertura, ao custo unitário
excedente_unidades = (
    base["estoque_atual"] - base["cobertura_alvo_dias"] * base["vendas_media_diaria"]
).clip(lower=0)
base["capital_liberavel"] = np.where(
    base["status"] == "Excesso de estoque",
    excedente_unidades * base["custo_unitario"],
    0.0,
)

# lucro em risco: unidades que faltarão até a reposição chegar (lead time), à margem unitária
unidades_faltantes = (
    (base["lead_time_dias"] - base["dias_cobertura_atual"]) * base["vendas_media_diaria"]
).clip(lower=0)
base["lucro_em_risco"] = np.where(
    base["status"] == "Risco de ruptura",
    unidades_faltantes * base["margem_unitaria"],
    0.0,
)

base["capital_investido_atual"] = base["estoque_atual"] * base["custo_unitario"]

colunas_saida = [
    "sku_id", "produto_nome", "categoria", "custo_unitario", "preco_venda",
    "margem_unitaria", "lead_time_dias", "vendas_12m", "vendas_media_diaria",
    "estoque_atual", "giro_anual", "dias_cobertura_atual", "cobertura_alvo_dias",
    "status", "capital_investido_atual", "capital_liberavel", "lucro_em_risco",
]
analise = base[colunas_saida].round(2)
analise.to_csv(os.path.join(DATA_DIR, "analise_estoque.csv"), index=False)

print("SKUs analisados:", len(analise))
print(analise["status"].value_counts())
print("Capital liberável total: R$", round(analise["capital_liberavel"].sum(), 2))
print("Lucro em risco total: R$", round(analise["lucro_em_risco"].sum(), 2))
