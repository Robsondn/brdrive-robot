# BRDrive Robot â€” J&T Express SP

RobÃ´ de automaÃ§Ã£o que executa a cada 5 minutos, consome a API REST do JMS BR diretamente via `requests`, processa os dados de viagens e dispara alertas inteligentes via Feishu para a equipe operacional â€” sem abrir browser, sem Selenium.

---

## Como funciona a autenticaÃ§Ã£o

O JMS usa CAPTCHA no login, o que impossibilita automaÃ§Ã£o de browser de forma confiÃ¡vel. A soluÃ§Ã£o adotada:

1. **Login manual uma Ãºnica vez** â€” o usuÃ¡rio acessa o JMS normalmente no navegador
2. **Captura do token** â€” o `YL_TOKEN` Ã© extraÃ­do do `localStorage` via console (F12)
3. **ExtraÃ§Ã£o contÃ­nua via API** â€” o robÃ´ usa o token para chamar a API REST do JMS a cada 5 minutos, sem precisar de browser

O token tem longa duraÃ§Ã£o. Enquanto nÃ£o expirar, o robÃ´ roda de forma totalmente autÃ´noma.

---

## O que o robÃ´ faz (a cada ciclo)

1. Chama a API REST do JMS com o token de sessÃ£o via `requests`
2. Processa os dados: Status de Lacre, Pontualidade, categorizaÃ§Ã£o de operaÃ§Ãµes
3. Atualiza o Database e o BRDrive no OneDrive compartilhado
4. Dispara alertas via Feishu Bot para viagens com saÃ­da/chegada atrasada
5. Evita alertas duplicados (controle por ID de viagem + data)

## Alertas disparados

| SituaÃ§Ã£o | Gatilho |
|----------|---------|
| SaÃ­da nÃ£o realizada | Motorista nÃ£o deu saÃ­da apÃ³s horÃ¡rio planejado |
| Chegada nÃ£o realizada | Viagem nÃ£o chegou ao destino no prazo |
| Alerta de lacre | Viagem Coleta Base SPS recebeu lacre sem baixa no ID |

**Destinos por categoria:**

| Categoria | CritÃ©rio |
|-----------|---------|
| Coleta PA | Origem comeÃ§a com "PA" |
| DevoluÃ§Ã£o | Tipo Coleta, saÃ­da 00:00â€“13:59 |
| Coleta Base | Tipo Coleta, saÃ­da 14:00â€“23:59 |
| SecundÃ¡ria | Tipo de linha = Entrega |

## Tecnologias

| Componente | Tecnologia |
|------------|-----------|
| ExtraÃ§Ã£o de dados | Python, `requests` (API REST do JMS) |
| Processamento de dados | Pandas |
| Alertas | Feishu Bot API (OAuth2) |
| Backup de alertas | Gmail SMTP |
| Agendamento | Loop com `time.sleep()` configurÃ¡vel (5 min) |

## Estrutura

```
BRDrive_Robot/
â”œâ”€â”€ main.py               # Agendador principal â€” rode este
â”œâ”€â”€ jms_extractor.py      # RobÃ´ Selenium: login + CAPTCHA + download
â”œâ”€â”€ processador.py        # LÃ³gicas de negÃ³cio: status, pontualidade, categorias
â”œâ”€â”€ alertas_jms.py        # Detecta viagens atrasadas e gera lista de alertas
â”œâ”€â”€ faishu_alertas.py     # IntegraÃ§Ã£o Feishu Bot API + e-mail backup
â”œâ”€â”€ controle_alertas.py   # DeduplicaÃ§Ã£o: evita reenviar alerta jÃ¡ enviado hoje
â”œâ”€â”€ limpeza.py            # Limpeza de arquivos temporÃ¡rios e logs antigos
â”œâ”€â”€ listar_grupos.py      # UtilitÃ¡rio: lista grupos/chats disponÃ­veis no Feishu
â”œâ”€â”€ setup.py              # ConfiguraÃ§Ã£o inicial do ambiente
â”œâ”€â”€ .env                  # Credenciais (nÃ£o vai ao GitHub)
â”œâ”€â”€ .env.example          # Modelo de configuraÃ§Ã£o
â”œâ”€â”€ requirements.txt
â””â”€â”€ logs/                 # Logs diÃ¡rios (criado automaticamente)
```

## InstalaÃ§Ã£o

```bash
# 1. Instalar dependÃªncias
pip install -r requirements.txt

# 2. Configurar credenciais
cp .env.example .env
# Edite .env com o YL_TOKEN do JMS e credenciais do Feishu

# 3. Testar uma execuÃ§Ã£o
python main.py --agora

# 4. Rodar continuamente (a cada 5 minutos)
python main.py
```

**Como obter o YL_TOKEN:**
```
1. Abrir JMS no navegador e fazer login normalmente
2. F12 â†’ Console
3. Digitar: localStorage.getItem("YL_TOKEN")
4. Copiar o valor e colar no .env
```

## ParÃ¢metros

```bash
python main.py                   # ciclos a cada 5 minutos
python main.py --agora           # executa uma vez imediatamente
python main.py --intervalo 10    # altera intervalo para 10 minutos
```

## Manter rodando 24h (Windows)

Adicionar atalho do `iniciar_robo.bat` na pasta de inicializaÃ§Ã£o do Windows:
`Win + R` â†’ `shell:startup` â†’ colar atalho

## DeduplicaÃ§Ã£o de alertas

O arquivo `logs/alertas_enviados.json` registra todos os IDs que jÃ¡ receberam alerta no dia. A cada novo dia o arquivo Ã© resetado automaticamente â€” nenhuma viagem recebe o mesmo alerta duas vezes no mesmo dia.

---

*Desenvolvido por Robson Noberto â€” Analista de Dados | J&T Express Filial SP*

