# Escalas do Louvor

Sistema simples para montar a escala mensal da equipe de louvor.

**Fluxo de todo mês (≈10 minutos):**
1. **Criar o mês** (painel → Meses → "Criar novo mês"). Ajuste temas/pregadores e remova cultos que não existirão.
2. **Enviar o link pessoal** de cada pessoa (botão WhatsApp na página do mês). Cada um abre no celular e marca os cultos em que **não pode**.
3. **Gerar a escala** (um clique). O sistema respeita indisponibilidades e regras, e distribui para ninguém ficar sobrecarregado.
4. **Ajustar à mão** o que quiser (a alteração fica travada 🔒), **baixar o Excel** e **publicar**.
5. **Enviar a escala** de cada pessoa pelo WhatsApp (tela "Avisos").

## Como rodar
```bash
cd /home/felipe/Documentos/MeusProjetos/escalas
./run.sh
```
Abra `http://localhost:5000/admin`. Senha padrão `louvor123` — **troque**:
```bash
ESCALAS_ADMIN_PASSWORD="minha-senha" ./run.sh
```
Requer Python 3.10+. Os dados ficam em `data/escalas.db` (faça cópia desse arquivo como backup).

## Como as pessoas acessam (celular)
- **Mesma rede Wi‑Fi da igreja/casa:** use `http://IP-DO-SEU-PC:5000` (descubra o IP com `hostname -I`). Defina `ESCALAS_BASE_URL="http://IP:5000"` para os links saírem certos.
- **De qualquer lugar (recomendado):** um túnel gratuito, sem abrir portas no roteador:
  `cloudflared tunnel --url http://localhost:5000` → gera um endereço `https://….trycloudflare.com`. Use-o em `ESCALAS_BASE_URL`.
  Para ficar sempre no ar, o ideal é hospedar em um servidor pequeno (VPS/Render/Fly) — o projeto roda igual.
- Cada pessoa tem um **link pessoal secreto** (sem senha para decorar). Se vazar, gere outro em Pessoas → pessoa → "Gerar novo link".

## Regras (já embutidas, editáveis)
Em **Pessoas** (por pessoa): funções, máximo mensal, duplas que tocam juntas. **A indisponibilidade é informada pela própria pessoa no link pessoal** (calendário + motivo obrigatório, até o prazo do mês); não há mais bloqueios fixos por dia da semana na tela (as restrições antigas foram zeradas em 12/11/2026 — cópia em `data/escalas.db.backup-antes-remover-restricoes-*`).
Em **Regras** (globais): limite confortável de cultos/mês, máximo de dias por semana, regra "domingo de manhã ≠ domingo à noite" (com exceção para culto marcado como *banda fixa*), tempo de cálculo.
O sistema também considera o **mês anterior**: quem tocou muito no mês passado tem o limite reduzido.

**Regras personalizadas** (tela Regras → "Nova regra"): *nunca juntos*, *bloquear dia + turno*, *fixar pessoa em culto* e *mínimo de cultos*, cada uma **obrigatória** ou **preferência**; dá para pausar ou excluir. São aplicadas ao gerar a escala e conferidas em "Conflitos com regras" (inclusive após ajustes manuais). Ficam na tabela `regra_custom`; lógica em `rules.py` e `scheduler.py`.

A equipe inicial foi carregada das escalas de nov/dez 2026 (`seed.py`). **Confira em Pessoas** as funções. (Numa instalação nova, o `seed.py` ainda cadastra os bloqueios antigos por dia da semana.)

## Avisos no futuro (WhatsApp / notificação)
Hoje: botões que abrem o WhatsApp com a mensagem pronta (`notify.py`). Para disparo automático, basta trocar a função `send()` por uma integração (WhatsApp Cloud API, Evolution API, ntfy.sh para push no celular…). As mensagens já são montadas e registradas na tabela `outbox`.

## Interface e design system
Sem dependências nem build: CSS, JS e ícones locais (funciona sem internet).
- `static/css/tokens.css`: **todas** as cores, espaçamentos, raios, sombras e tipografia, nos temas claro e escuro. Para mudar a identidade visual, mexa só aqui.
- `static/css/layout.css`: estrutura (barra lateral, cabeçalho, responsividade). `static/css/components.css`: botões, campos, cards, tabelas, indicadores etc.
- `templates/_ui.html`: macros Jinja dos componentes (`icon`, `badge`, `stat`, `alert`, `page_head`…). `templates/base.html`: layouts do painel e das páginas públicas.
- `static/js/ui.js`: tema (claro/escuro/sistema, salvo no navegador), menu no celular, busca, copiar, abas e modais.
- `static/icons.svg`: ícones. **Catálogo de componentes:** abra `/static/design-system.html` com o sistema rodando.

## Arquivos
`app.py` (site) · `scheduler.py` (otimizador/regras) · `db.py` · `seed.py` (equipe inicial) · `exporter.py` (Excel) · `notify.py` · `templates/` · `static/`
