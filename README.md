# Priorização de Capital em Estoque

A maioria dos painéis de estoque mostra o que já aconteceu. Este vai um passo além: a partir do histórico de vendas e reposição, aponta **onde há capital parado em excesso de estoque** e **onde há risco real de perder venda por ruptura** — com o valor de cada oportunidade em reais, não só um gráfico bonito.

**Demo:** _(depois de ativar o GitHub Pages, cole aqui o link — algo como `https://seuusuario.github.io/inventory-capital-priority/`)_

<!-- Tire um print do painel aberto no navegador, salve como docs/preview.png e descomente a linha abaixo -->
<!-- ![preview do painel](docs/preview.png) -->

## O que o painel mostra

- Capital total liberável (dinheiro parado em estoque excedente) e lucro em risco (por SKUs perto de ruptura)
- Dispersão de todos os SKUs por giro anual x dias de cobertura, com o tamanho da bolha representando capital investido
- Capital liberável por categoria, para saber onde focar a revisão de compras primeiro
- Tabela de oportunidades priorizadas por valor financeiro, cada uma com uma ação recomendada

## Metodologia

Para cada SKU, usando os últimos 12 meses de histórico:

| Métrica | Cálculo |
|---|---|
| Giro anual | vendas dos últimos 12 meses ÷ estoque médio no período |
| Dias de cobertura | estoque atual ÷ venda média diária |
| Status | "Risco de ruptura" se a cobertura é menor que o lead time de reposição; "Excesso de estoque" se a cobertura passa de 2x o alvo de segurança (2x o lead time); "Saudável" no meio termo |
| Capital liberável | unidades acima do alvo de cobertura, multiplicadas pelo custo unitário — só para SKUs com excesso |
| Lucro em risco | unidades que faltarão até a reposição chegar, multiplicadas pela margem unitária — só para SKUs com risco de ruptura |

A ideia central: **giro alto não é sempre bom e estoque alto não é sempre ruim** — depende da relação entre os dois e do lead time de cada produto. Um SKU pode ter giro baixo por ter excesso de estoque (problema de compra) ou por ter demanda baixa mesmo (aí o problema é outro). Este painel foca no primeiro caso, que é o que dá pra agir imediatamente sobre.

## Estrutura do projeto

```
inventory-capital-priority/
├── data/
│   ├── produtos.csv           # catálogo de 500 SKUs (custo, preço, categoria, lead time)
│   ├── estoque_mensal.csv     # histórico de 60 meses por SKU (~30.000 linhas)
│   └── analise_estoque.csv    # saída da análise: giro, cobertura, status, valores
├── scripts/
│   ├── generate_data.py       # gera produtos.csv e estoque_mensal.csv
│   ├── analyze_inventory.py   # calcula giro, cobertura, status e valores financeiros
│   ├── build_dashboard.py     # monta docs/index.html a partir da análise
│   └── dashboard_template.html
└── docs/
    └── index.html             # painel publicado via GitHub Pages
```

## Como rodar localmente

```bash
pip install pandas numpy
python scripts/generate_data.py        # gera os CSVs em data/
python scripts/analyze_inventory.py    # gera data/analise_estoque.csv
python scripts/build_dashboard.py      # gera docs/index.html
```

Depois é só abrir `docs/index.html` no navegador.

## Limitações

Os dados são sintéticos: gerei 500 SKUs com perfis de compra propositalmente variados (parte com excesso, parte com risco de ruptura, a maioria com política razoável) para o painel ter algo relevante para mostrar. Em um cenário real, as métricas de giro e cobertura são um bom ponto de partida, mas a decisão final também depende de fatores que este painel não modela — sazonalidade específica do produto, contratos mínimos de compra com fornecedores, produtos em final de vida útil, entre outros.

O alvo de cobertura de segurança (2x o lead time) é uma regra simples e configurável — em um caso real, isso normalmente varia por criticidade do produto e variabilidade da demanda (algo que métodos de estoque de segurança mais sofisticados, como os baseados em desvio-padrão da demanda, calculam de forma mais precisa).

## Stack

Python (pandas, numpy) para geração de dados e análise · HTML/CSS/JS puro + Chart.js para o painel.
