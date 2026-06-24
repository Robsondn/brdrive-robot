# BRDrive Robot — J&T Express SP

Robô de automação que executa a cada 25 minutos, faz login automático no sistema JMS BR (incluindo solução de CAPTCHA slider via visão computacional), extrai o relatório consolidado de viagens, processa os dados e dispara alertas inteligentes via Feishu para a equipe operacional.

---

## O que o robô faz (a cada ciclo)

1. Faz login no JMS BR via Selenium (Edge)
2. Resolve o CAPTCHA slider automaticamente com OpenCV (template matching)
3. Exporta o relatório consolidado de viagens
4. Processa os dados: Status de Lacre, Pontualidade, categorização de operações
5. Atualiza o Database e o BRDrive no OneDrive compartilhado
6. Dispara alertas via Feishu Bot para viagens com saída/chegada atrasada
7. Evita alertas duplicados (controle por ID de viagem + data)

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
| Automação web | Python, Selenium (Edge WebDriver) |
| Solução de CAPTCHA | OpenCV, NumPy (template matching) |
| Processamento de dados | Pandas |
| Alertas | Feishu Bot API (OAuth2) |
| Backup de alertas | Gmail SMTP |
| Agendamento | Loop com `time.sleep()` configurável |

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
# Edite .env com suas credenciais (JMS, Feishu)

# 3. Instalar Edge WebDriver compatível com sua versão do Edge
# https://developer.microsoft.com/en-us/microsoft-edge/tools/webdriver/
# Coloque msedgedriver.exe na pasta do projeto

# 4. Testar uma execução
python main.py --agora

# 5. Rodar continuamente
python main.py
```

## Parâmetros

```bash
python main.py                   # ciclos a cada 25 minutos
python main.py --agora           # executa uma vez imediatamente
python main.py --intervalo 30    # altera intervalo para 30 minutos
```

## Manter rodando 24h (Windows)

Adicionar atalho do `iniciar_robo.bat` na pasta de inicialização do Windows:
`Win + R` → `shell:startup` → colar atalho

## Deduplicação de alertas

O arquivo `logs/alertas_enviados.json` registra todos os IDs que já receberam alerta no dia. A cada novo dia o arquivo é resetado automaticamente — nenhuma viagem recebe o mesmo alerta duas vezes no mesmo dia.

---

*Desenvolvido por Robson Noberto — Analista de Processos | J&T Express Filial SP*
