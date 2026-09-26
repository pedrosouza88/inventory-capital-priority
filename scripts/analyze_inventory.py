"""
Transforma o histórico de estoque em uma lista priorizada de ações,
com o valor financeiro de cada uma.

Para cada SKU, usando os últimos 12 meses de histórico até um mês de referência:
  - giro anual        = vendas do período / estoque médio no período
  - dias de cobertura = estoque no mês de referência / venda média diária
  - status:
      "Risco de ruptura"   -> cobertura é menor que o lead time de reposição
      "Excesso de estoque" -> cobertura passa de 2x o alvo de segurança (2x o lead time)
      "Saudável"           -> dentro da faixa esperada

Duas métricas de negócio saem disso, por SKU:
  - capital_liberavel  (R$): quanto dá pra tirar do estoque parado sem
                             arriscar falta, para SKUs com excesso
  - lucro_em_risco     (R$): margem que pode ser perdida nos próximos dias
                             se a reposição não chegar a tempo, para SKUs
                             com risco de ruptura

Sobre isso, uma camada de PRIORIDADE de negócio (não confundir com o
diagnóstico acima):
  - "Urgente"  -> risco de ruptura em produto de margem acima da mediana
                  (perder essa venda dói mais no lucro)
  - "Atenção"  -> excesso de estoque com mais de 180 dias de cobertura
                  (capital parado há tempo demais)
  - "OK"       -> o resto (inclui excesso leve e risco de baixa margem)

Saídas:
  - data/analise_estoque.csv   (situação atual, uma linha por SKU)
  - data/tendencia_mensal.csv  (últimos 6 meses: capital parado e lucro em
                                 risco totais, recalculados como se cada mês
                                 fosse "hoje" — mostra se a situação está
                                 melhorando ou piorando)
"""

import os
import numpy as np
import pandas as pd

BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(BASE_DIR, "..", "data")

produtos = pd.read_csv(os.path.join(DATA_DIR, "produtos.csv"))
estoque = pd.read_csv(os.path.join(DATA_DIR, "estoque_mensal.csv"))

meses_ordenados = sorted(estoque["mes"].unique())
MEDIANA_MARGEM = (produtos["preco_venda"] - produtos["custo_unitario"]).median()


def analisar_periodo(mes_fim: str) -> pd.DataFrame:
    """Recalcula giro / cobertura / status / valores como se `mes_fim`
    fosse o mês mais recente disponível, usando os 12 meses anteriores a ele."""
    idx_fim = meses_ordenados.index(mes_fim)
    janela = meses_ordenados[max(0, idx_fim - 11): idx_fim + 1]

    df_janela = estoque[estoque["mes"].isin(janela)]
    agregado = df_janela.groupby("sku_id").agg(
        vendas_periodo=("vendas_unidades", "sum"),
        estoque_medio_periodo=("estoque_final", "mean"),
    ).reset_index()

    estoque_no_mes = (
        estoque[estoque["mes"] == mes_fim][["sku_id", "estoque_final"]]
        .rename(columns={"estoque_final": "estoque_atual"})
    )

    base = produtos.merge(agregado, on="sku_id").merge(estoque_no_mes, on="sku_id")

    base["margem_unitaria"] = base["preco_venda"] - base["custo_unitario"]
    dias_periodo = len(janela) * 30.4
    base["vendas_media_diaria"] = base["vendas_periodo"] / dias_periodo
    base["giro_anual"] = (base["vendas_periodo"] / base["estoque_medio_periodo"].replace(0, np.nan)) * (365 / dias_periodo)
    base["giro_anual"] = base["giro_anual"].fillna(0)
    base["dias_cobertura_atual"] = np.where(
        base["vendas_media_diaria"] > 0,
        base["estoque_atual"] / base["vendas_media_diaria"],
        np.inf,
    )
    base["cobertura_alvo_dias"] = base["lead_time_dias"] * 2

    def classificar(row):
        if row["dias_cobertura_atual"] < row["lead_time_dias"]:
            return "Risco de ruptura"
        if row["dias_cobertura_atual"] > row["cobertura_alvo_dias"] * 2:
            return "Excesso de estoque"
        return "Saudável"

    base["status"] = base.apply(classificar, axis=1)

    excedente_unidades = (
        base["estoque_atual"] - base["cobertura_alvo_dias"] * base["vendas_media_diaria"]
    ).clip(lower=0)
    base["capital_liberavel"] = np.where(
        base["status"] == "Excesso de estoque",
        excedente_unidades * base["custo_unitario"],
        0.0,
    )

    unidades_faltantes = (
        (base["lead_time_dias"] - base["dias_cobertura_atual"]) * base["vendas_media_diaria"]
    ).clip(lower=0)
    base["lucro_em_risco"] = np.where(
        base["status"] == "Risco de ruptura",
        unidades_faltantes * base["margem_unitaria"],
        0.0,
    )

    base["capital_investido_atual"] = base["estoque_atual"] * base["custo_unitario"]

    def priorizar(row):
        if row["status"] == "Risco de ruptura" and row["margem_unitaria"] >= MEDIANA_MARGEM:
            return "Urgente"
        if row["status"] == "Excesso de estoque" and row["dias_cobertura_atual"] > 180:
            return "Atenção"
        return "OK"

    base["urgencia"] = base.apply(priorizar, axis=1)

    return base


# ---------------------------------------------------------------
# 1) SITUAÇÃO ATUAL (último mês) — detalhe completo por SKU
# ---------------------------------------------------------------
ULTIMO_MES = meses_ordenados[-1]
analise = analisar_periodo(ULTIMO_MES)

# última compra registrada de cada SKU (mês mais recente com reposição real,
# ignorando ajustes residuais menores que meia unidade)
compras_reais = estoque[estoque["compras_unidades"] >= 0.5]
ultima_compra = (
    compras_reais.groupby("sku_id")["mes"].max().rename("ultima_compra_mes")
)
analise = analise.merge(ultima_compra, on="sku_id", how="left")
analise["ultima_compra_mes"] = analise["ultima_compra_mes"].fillna("—")

colunas_saida = [
    "sku_id", "produto_nome", "categoria", "fornecedor", "comprador",
    "custo_unitario", "preco_venda", "margem_unitaria", "lead_time_dias",
    "vendas_periodo", "vendas_media_diaria", "estoque_atual", "giro_anual",
    "dias_cobertura_atual", "cobertura_alvo_dias", "status", "urgencia",
    "capital_investido_atual", "capital_liberavel", "lucro_em_risco",
    "ultima_compra_mes",
]
analise_saida = analise[colunas_saida].round(2)
analise_saida.to_csv(os.path.join(DATA_DIR, "analise_estoque.csv"), index=False)

print("SKUs analisados:", len(analise_saida))
print(analise_saida["status"].value_counts())
print(analise_saida["urgencia"].value_counts())
print("Capital liberável total: R$", round(analise_saida["capital_liberavel"].sum(), 2))
print("Lucro em risco total: R$", round(analise_saida["lucro_em_risco"].sum(), 2))

# ---------------------------------------------------------------
# 2) TENDÊNCIA DOS ÚLTIMOS 6 MESES (recalcula tudo em cada mês de corte)
# ---------------------------------------------------------------
ultimos_6_meses = meses_ordenados[-6:]
linhas_tendencia = []
for mes in ultimos_6_meses:
    periodo = analisar_periodo(mes)
    linhas_tendencia.append({
        "mes": mes,
        "capital_liberavel_total": round(float(periodo["capital_liberavel"].sum()), 2),
        "lucro_risco_total": round(float(periodo["lucro_em_risco"].sum()), 2),
        "n_excesso": int((periodo["status"] == "Excesso de estoque").sum()),
        "n_risco": int((periodo["status"] == "Risco de ruptura").sum()),
    })

tendencia = pd.DataFrame(linhas_tendencia)
tendencia.to_csv(os.path.join(DATA_DIR, "tendencia_mensal.csv"), index=False)
print("\nTendência 6 meses:")
print(tendencia)
