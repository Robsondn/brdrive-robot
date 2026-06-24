# BRDrive Robot — J&T Express SP

Robô de automação que executa a cada 5 minutos, consome a API REST do JMS BR diretamente via `requests`, processa os dados de viagens e dispara alertas inteligentes via Feishu para a equipe operacional — sem abrir browser, sem Selenium.

---

## Como funciona a autenticação

O JMS usa CAPTCHA no login, o que impossibilita automação de browser de forma confiável. A solução adotada:

1. **Login manual uma única vez** — o usuário acessa o JMS normalmente no navegador
2. **Captura do token** — o `YL_TOKEN` é extraído do `localStorage` via console (F12)
3. **Extração contínua via API** — o robô usa o token para chamar a API REST do JMS a cada 5 minutos, sem precisar de browser

O token tem longa duração. Enquanto não expirar, o robô roda de forma totalmente autônoma.

---

## O que o robô faz (a cada ciclo)

1. Chama a API REST do JMS com o token de sessão via `requests`
2. Processa os dados: Status de Lacre, Pontualidade, categorização de operações
3. Atualiza o Database e o BRDrive no OneDrive compartilhado
4. Dispara alertas via Feishu Bot para viagens com saída/chegada atrasada
5. Evita alertas duplicados (controle por ID de viagem + data)

## Alertas disparados

| Situação | Gatilho |
|----------|---------|
| Saída não realizada | Motorista não deu saída após horário planejado |
| Chegada não realizada | Viagem não chegou ao destino no prazo |
| Alerta de lacre | Viagem Coleta Base SPS recebeu lacre sem baixa no ID |

**Destinos por categoria:**

| Categoria | Critério |
|-----------|---------|
| Coleta PA | Origem começa com "PA" |
| Devolução | Tipo Coleta, saída 00:00–13:59 |
| Coleta Base | Tipo Coleta, saída 14:00–23:59 |
| Secundária | Tipo de linha = Entrega |

## Tecnologias

| Componente | Tecnologia |
|------------|-----------|
| Extração de dados | Python, `requests` (API REST do JMS) |
| Processamento de dados | Pandas |
| Alertas | Feishu Bot API (OAuth2) |
| Backup de alertas | Gmail SMTP |
| Agendamento | Loop com `time.sleep()` configurável (5 min) |

## Estrutura

```
BRDrive_Robot/
├── main.py               # Agendador principal — rode este
├── jms_extractor.py      # Robô Selenium: login + CAPTCHA + download
├── processador.py        # Lógicas de negócio: status, pontualidade, categorias
├── alertas_jms.py        # Detecta viagens atrasadas e gera lista de alertas
├── faishu_alertas.py     # Integração Feishu Bot API + e-mail backup
├── controle_alertas.py   # Deduplicação: evita reenviar alerta já enviado hoje
├── limpeza.py            # Limpeza de arquivos temporários e logs antigos
├── listar_grupos.py      # Utilitário: lista grupos/chats disponíveis no Feishu
├── setup.py              # Configuração inicial do ambiente
├── .env                  # Credenciais (não vai ao GitHub)
├── .env.example          # Modelo de configuração
├── requirements.txt
└── logs/                 # Logs diários (criado automaticamente)
```

## Instalação

```bash
# 1. Instalar dependências
pip install -r requirements.txt

# 2. Configurar credenciais
cp .env.example .env
# Edite .env com o YL_TOKEN do JMS e credenciais do Feishu

# 3. Testar uma execução
python main.py --agora

# 4. Rodar continuamente (a cada 5 minutos)
python main.py
```

**Como obter o YL_TOKEN:**
```
1. Abrir JMS no navegador e fazer login normalmente
2. F12 → Console
3. Digitar: localStorage.getItem("YL_TOKEN")
4. Copiar o valor e colar no .env
```

## Parâmetros

```bash
python main.py                   # ciclos a cada 5 minutos
python main.py --agora           # executa uma vez imediatamente
python main.py --intervalo 10    # altera intervalo para 10 minutos
```

## Manter rodando 24h (Windows)

Adicionar atalho do `iniciar_robo.bat` na pasta de inicialização do Windows:
`Win + R` → `shell:startup` → colar atalho

## Deduplicação de alertas

O arquivo `logs/alertas_enviados.json` registra todos os IDs que já receberam alerta no dia. A cada novo dia o arquivo é resetado automaticamente — nenhuma viagem recebe o mesmo alerta duas vezes no mesmo dia.

---

*Desenvolvido por Robson Noberto — Analista de Processos | J&T Express Filial SP*
