"""
Gera dados sintéticos de estoque para análise de priorização de capital.

Duas tabelas:
  - produtos.csv         (~500 SKUs: custo, preço, categoria, lead time de reposição)
  - estoque_mensal.csv   (~30.000 linhas: 500 SKUs x 60 meses de histórico de estoque)

O objetivo não é só descrever o estoque, mas simular padrões reais de gestão:
uma parte dos SKUs foi comprada em excesso (capital parado), outra parte foi
subestocada (risco de perda de venda), e o restante segue uma política de
reposição razoável.
"""

import os
import numpy as np
import pandas as pd
from datetime import date

rng = np.random.default_rng(7)

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
os.makedirs(OUT_DIR, exist_ok=True)

# ---------------------------------------------------------------
# 1) CATÁLOGO DE PRODUTOS
# ---------------------------------------------------------------
categorias_config = {
    # categoria: (n_skus, faixa_custo, faixa_markup, faixa_lead_time_dias)
    "Eletrônicos":            (70, (60, 1800), (1.35, 1.9), (25, 55)),
    "Casa e Utilidades":      (70, (15, 300),  (1.6, 2.6),  (15, 35)),
    "Beleza e Higiene":       (65, (8, 150),   (1.8, 3.0),  (10, 25)),
    "Esporte e Lazer":        (60, (25, 700),  (1.5, 2.3),  (20, 40)),
    "Papelaria":              (55, (3, 90),    (1.9, 3.2),  (7, 20)),
    "Ferramentas":            (60, (20, 900),  (1.4, 2.0),  (20, 45)),
    "Pet":                    (55, (10, 250),  (1.7, 2.6),  (10, 25)),
    "Alimentos Não Perecíveis": (65, (5, 60),  (1.5, 2.2),  (7, 18)),
}

nomes_base = {
    "Eletrônicos": ["Fone Bluetooth", "Carregador Turbo", "Cabo USB-C", "Caixa de Som", "Adaptador HDMI", "Mouse sem Fio", "Teclado Compacto", "Hub USB"],
    "Casa e Utilidades": ["Organizador Multiuso", "Jogo de Panelas", "Luminária de Mesa", "Cortina Blackout", "Tapete Antiderrapante", "Suporte de Prateleira"],
    "Beleza e Higiene": ["Shampoo 400ml", "Creme Hidratante", "Escova de Cabelo", "Kit Manicure", "Sabonete Líquido", "Protetor Solar"],
    "Esporte e Lazer": ["Garrafa Térmica", "Faixa Elástica", "Bola de Treino", "Luva de Academia", "Corda de Pular", "Mochila Esportiva"],
    "Papelaria": ["Caderno Universitário", "Caneta Gel (cx)", "Marcador de Texto", "Agenda Anual", "Pasta Organizadora", "Post-it Colorido"],
    "Ferramentas": ["Furadeira Compacta", "Kit Chaves de Fenda", "Trena 5m", "Nível a Laser", "Parafusadeira", "Serra Manual"],
    "Pet": ["Ração Premium 3kg", "Brinquedo Mordedor", "Coleira Ajustável", "Areia Sanitária", "Petisco Natural", "Cama Pet"],
    "Alimentos Não Perecíveis": ["Café em Grãos 500g", "Barra de Cereal (cx)", "Azeite Extra Virgem", "Macarrão Tipo 1", "Molho de Tomate", "Chá em Sachês"],
}

linhas_produto = []
sku_id = 1
for categoria, (n_skus, faixa_custo, faixa_markup, faixa_lead) in categorias_config.items():
    base_nomes = nomes_base[categoria]
    for i in range(n_skus):
        custo = round(rng.uniform(*faixa_custo), 2)
        markup = rng.uniform(*faixa_markup)
        preco = round(custo * markup, 2)
        lead_time = int(rng.integers(faixa_lead[0], faixa_lead[1] + 1))
        nome_base = base_nomes[i % len(base_nomes)]
        variacao = i // len(base_nomes)
        nome = f"{nome_base}" + (f" v{variacao+1}" if variacao else "")

        # perfil de demanda: lognormal favorece poucos best-sellers e muitos itens de cauda longa
        vendas_mensais_base = max(2, rng.lognormal(mean=2.6, sigma=1.0))

        # perfil de política de compra: a maioria é razoável, mas uma fatia é
        # deliberadamente "excesso" (comprou demais) e outra "risco" (comprou de menos)
        perfil = rng.choice(
            ["razoavel", "excesso", "risco_ruptura"],
            p=[0.65, 0.20, 0.15],
        )

        linhas_produto.append({
            "sku_id": sku_id,
            "produto_nome": nome,
            "categoria": categoria,
            "custo_unitario": custo,
            "preco_venda": preco,
            "lead_time_dias": lead_time,
            "vendas_mensais_base": round(vendas_mensais_base, 1),
            "perfil_compra": perfil,
        })
        sku_id += 1

produtos = pd.DataFrame(linhas_produto)

# ---------------------------------------------------------------
# 1b) FORNECEDOR E COMPRADOR RESPONSÁVEL
# ---------------------------------------------------------------
# feito depois do laço principal (com um gerador de números aleatórios à parte)
# para não alterar a sequência de sorteios já usada nos atributos acima.
rng_compras = np.random.default_rng(101)

fornecedores_por_categoria = {
    "Eletrônicos": ["TechSupply Distribuidora", "Import Eletrônicos BR", "Nexus Componentes"],
    "Casa e Utilidades": ["Lar & Cia Distribuidora", "CasaForte Suprimentos"],
    "Beleza e Higiene": ["BelezaPura Distribuidora", "Cosmetic Brasil"],
    "Esporte e Lazer": ["Vida Ativa Distribuidora", "SportMax Suprimentos"],
    "Papelaria": ["Papel & Cia", "EscritorioTotal Distribuidora"],
    "Ferramentas": ["FerroForte Distribuidora", "ToolPro Suprimentos"],
    "Pet": ["PetLife Distribuidora", "AmigoFiel Suprimentos"],
    "Alimentos Não Perecíveis": ["Empório Atacado", "Mercado Sul Distribuidora"],
}

# cada categoria tem um comprador principal; alguns compradores cuidam de mais
# de uma categoria, como costuma acontecer em times de compras enxutos
categoria_comprador = {
    "Eletrônicos": "Ricardo Nunes",
    "Casa e Utilidades": "Camila Torres",
    "Beleza e Higiene": "Juliana Prado",
    "Esporte e Lazer": "Marcelo Duarte",
    "Papelaria": "Fernanda Lima",
    "Ferramentas": "Ricardo Nunes",
    "Pet": "Camila Torres",
    "Alimentos Não Perecíveis": "Fernanda Lima",
}

produtos["fornecedor"] = produtos["categoria"].apply(
    lambda cat: rng_compras.choice(fornecedores_por_categoria[cat])
)
produtos["comprador"] = produtos["categoria"].map(categoria_comprador)

# ---------------------------------------------------------------
# 2) HISTÓRICO MENSAL DE ESTOQUE (60 meses)
# ---------------------------------------------------------------
N_MESES = 60
DATA_INICIO = date(2021, 1, 1)
meses = pd.date_range(DATA_INICIO, periods=N_MESES, freq="MS")

linhas_estoque = []
for _, prod in produtos.iterrows():
    base = prod["vendas_mensais_base"]
    perfil = prod["perfil_compra"]
    lead_time_meses = prod["lead_time_dias"] / 30

    # cobertura alvo (em meses de venda) que a política de compra deste SKU mira
    if perfil == "excesso":
        cobertura_alvo = rng.uniform(3.0, 5.5)   # compra muito além do necessário
    elif perfil == "risco_ruptura":
        cobertura_alvo = rng.uniform(0.3, 0.7)   # compra menos que o lead time exige
    else:
        cobertura_alvo = rng.uniform(1.2, 2.2)   # política razoável

    estoque = base * cobertura_alvo  # estoque inicial
    for i, mes in enumerate(meses):
        # sazonalidade leve: novembro/dezembro vendem mais em quase todas categorias
        fator_sazonal = 1.0
        if mes.month == 11:
            fator_sazonal = 1.45
        elif mes.month == 12:
            fator_sazonal = 1.25

        demanda_desejada = max(0, rng.normal(base * fator_sazonal, base * 0.18))
        vendas_efetivas = min(demanda_desejada, estoque)
        dias_ruptura = 0
        if demanda_desejada > estoque:
            # parte do mês ficou sem estoque suficiente pra atender a demanda
            falta_relativa = (demanda_desejada - estoque) / max(demanda_desejada, 1e-6)
            dias_ruptura = int(round(falta_relativa * 30))

        estoque_apos_vendas = max(0, estoque - vendas_efetivas)

        # reposição: repõe até a cobertura alvo, com algum ruído de execução
        alvo_unidades = base * fator_sazonal * cobertura_alvo
        necessidade = max(0, alvo_unidades - estoque_apos_vendas)
        eficiencia_compra = rng.uniform(0.85, 1.05)
        compras = necessidade * eficiencia_compra

        estoque_final = estoque_apos_vendas + compras

        linhas_estoque.append({
            "sku_id": prod["sku_id"],
            "mes": mes.strftime("%Y-%m"),
            "estoque_inicial": round(estoque, 1),
            "vendas_unidades": round(vendas_efetivas, 1),
            "compras_unidades": round(compras, 1),
            "estoque_final": round(estoque_final, 1),
            "dias_ruptura": dias_ruptura,
        })

        estoque = estoque_final

estoque_mensal = pd.DataFrame(linhas_estoque)

# ---------------------------------------------------------------
# EXPORTA
# ---------------------------------------------------------------
produtos.drop(columns=["perfil_compra"]).to_csv(os.path.join(OUT_DIR, "produtos.csv"), index=False)
estoque_mensal.to_csv(os.path.join(OUT_DIR, "estoque_mensal.csv"), index=False)

print("produtos:", produtos.shape)
print("estoque_mensal:", estoque_mensal.shape)
print("capital total em estoque (último mês):",
      round((estoque_mensal[estoque_mensal.mes == meses[-1].strftime("%Y-%m")]
             .merge(produtos, on="sku_id")
             .eval("estoque_final * custo_unitario")).sum(), 2))
