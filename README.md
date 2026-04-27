# Jurídico do Dia

Site estático que compila notícias jurídicas dos tribunais superiores (STF, STJ) e dos principais veículos de imprensa especializada (Conjur, Migalhas), classificadas automaticamente por área do Direito: **Societário**, **Família e Sucessões**, **Cível** e **Tributário**.

Atualização diária via GitHub Actions, hospedagem gratuita no GitHub Pages.

---

## Como funciona

1. Um script Python (`build.py`) lê os feeds RSS configurados em `feeds.json`.
2. Cada notícia recebe uma pontuação para cada área do Direito com base em palavras-chave (`keywords.json`).
3. A área com maior pontuação "fica com" a notícia. Itens sem pontuação suficiente são descartados.
4. O script gera HTML estático em `docs/` — uma página inicial com cards e uma página por área.
5. O GitHub Actions roda esse processo todo dia às 09h (horário de Brasília) e publica no GitHub Pages.

## Estrutura do projeto

```
.
├── build.py                       # Script principal (fetch + classify + render)
├── feeds.json                     # Fontes (RSS URLs)
├── keywords.json                  # Palavras-chave por área (editável)
├── requirements.txt               # Dependências Python
├── templates/
│   ├── base.html                  # Layout comum
│   ├── index.html                 # Página inicial
│   └── area.html                  # Página por área
├── static/
│   └── style.css                  # Estilos
├── .github/workflows/update.yml   # Automação diária
└── docs/                          # Saída gerada (não versionada)
```

## Deploy no GitHub Pages

1. **Criar repositório** no GitHub (público ou privado — Pages funciona em ambos com conta paga; em conta gratuita, precisa ser público).
2. **Subir os arquivos:**
   ```bash
   git init
   git add .
   git commit -m "Versão inicial"
   git branch -M main
   git remote add origin https://github.com/SEU-USUARIO/SEU-REPO.git
   git push -u origin main
   ```
3. **Habilitar Pages:** no repositório, vá em **Settings → Pages** e em **Source** selecione **GitHub Actions**.
4. **Pronto.** O workflow rodará no primeiro push e a partir daí todo dia às 09h (Brasília). O site ficará em `https://SEU-USUARIO.github.io/SEU-REPO/`.

Para forçar uma atualização manual: aba **Actions → Atualizar notícias diárias → Run workflow**.

## Rodar localmente (opcional)

Requer Python 3.10+:

```bash
pip install -r requirements.txt
python build.py
# Abra docs/index.html no navegador
```

## Personalização

### Refinar a classificação

Edite `keywords.json`. Cada área tem dois grupos:

- `strong_keywords` — termos com peso **3** (sinal forte da área)
- `keywords` — termos com peso **1** (sinal moderado)

A pontuação mínima para uma notícia ser incluída é **2** (configurável em `build.py:MIN_SCORE`). Se uma notícia se encaixar em mais de uma área, vai para a de maior pontuação.

**Dica:** se notícias estão indo para a área errada, adicione termos discriminantes ao `strong_keywords` da área correta, ou termos do "ruído" como `strong_keywords` da área que está absorvendo indevidamente.

### Adicionar/remover áreas

Edite `keywords.json` adicionando uma nova entrada com `id`, `name`, `description`, `strong_keywords` e `keywords`. O site será regenerado automaticamente com a nova área. Não esqueça de garantir que o `id` seja um nome de arquivo válido (sem espaços, sem acentos).

### Mudar fontes

Edite `feeds.json`. Para fontes que não têm RSS público (caso de muitos sites de escritório), use Google News como intermediário:

```json
{
  "id": "escritorio-x",
  "name": "Escritório X",
  "short": "EscritórioX",
  "url": "https://news.google.com/rss/search?q=site:escritoriox.com.br&hl=pt-BR&gl=BR&ceid=BR:pt-419"
}
```

Não esqueça de adicionar uma classe CSS correspondente em `static/style.css` (`.source-escritorio-x`) se quiser cor própria no badge.

### Mudar o horário da atualização

Edite o `cron` em `.github/workflows/update.yml`. O horário é UTC. Brasília = UTC-3, então `0 12 * * *` = 09h Brasília.

## Limitações conhecidas

- **JOTA** não está incluído — o site não disponibiliza feed RSS público estável.
- **Links via Google News:** STF, STJ e Migalhas são acessados via Google News RSS (porque seus feeds próprios estão protegidos ou indisponíveis). Os links abrem o artigo original, mas passam por um redirect do Google.
- **Classificação por palavras-chave** acerta cerca de 80–85% dos casos. Notícias de fronteira (ex: "ICMS sobre prestação de serviço cível em sociedade limitada") podem ir para a área "errada" pelo critério de maior pontuação.
- **Cobertura limitada ao que está nos feeds.** Geralmente são os destaques de cada veículo, não todo o conteúdo.

## Licença e responsabilidade

Este projeto agrega **títulos, descrições curtas e links** de fontes públicas — não reproduz o conteúdo integral. Os artigos são propriedade de seus respectivos veículos. O usuário é direcionado ao site de origem para ler a matéria completa.

A classificação automática é uma ferramenta de organização, não uma análise jurídica. Não constitui aconselhamento legal.
