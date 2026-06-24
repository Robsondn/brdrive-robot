import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
import random

PASTA = r'C:\Users\Robo Transporte\OneDrive - J&T EXPRESS - FILIAL SP\Power BI Gus'
agora = datetime.now().replace(second=0, microsecond=0)

colunas = [
    'Número do ID', 'Status', 'Nome da viagem', 'Tipo de viagem', 'Tipo de linha',
    'Saída do dia', 'Quilometragem', 'Placa do carro', 'Modelo do veículo',
    'Nome completo do transportador', 'Tipo de transportador', 'Abreviatura de transportador',
    'Condutor', 'Telefone do carro', 'Código de estação de partida',
    'Nome de estação de partida', 'Regional de saída do carro',
    'Quantidade de encomendas escaneadas', 'Número de Pedido mãe',
    'Tempo de início do carregamento', 'Tempo de término do carregamento',
    'Tempo de carregamento (min)', 'Horario de carregamento passou das 20:00 hs?',
    'hora de lacre', 'Tempo de partida planejada', 'Horário real de saída',
    'Horário de check-out do condutor', 'Código de estação de chegada',
    'Nome de estação de chegada', 'Regional de chegada do carro',
    'Tempo de chegada planejado', 'Tempo real de chegada', 'Duração de atraso (min)',
    'Horário de check-in do motorista', 'hora de deslacre',
    'Tempo de espera entre o check-in até o início do descarregamento (min)',
    'Tempo de início de descarga', 'Tempo de término de descarga',
    'Tempo de descarregamento (min)',
]

def make_row(tipo_linha, origem, regional, saida_plan_dt,
             status='Programado：已调度', ja_saiu=False):
    # horário limpo — arredonda para múltiplo de 5min
    m = (saida_plan_dt.minute // 5) * 5
    saida_plan_dt = saida_plan_dt.replace(minute=m, second=0, microsecond=0)
    cheg_plan  = saida_plan_dt + timedelta(hours=2)
    saida_real = (saida_plan_dt - timedelta(minutes=5)).strftime('%Y-%m-%d %H:%M:%S') if ja_saiu else None
    condutores = ['Carlos Alberto', 'Valdecir Gomes', 'José da Silva', 'Antonio Pereira']
    return {
        'Número do ID':                    f'SRTR{random.randint(22601000000,22602000000)}',
        'Status':                          status,
        'Nome da viagem':                  f'BRE-{origem[:3].upper()}-0000-1',
        'Tipo de viagem':                  'Linha secundária',
        'Tipo de linha':                   tipo_linha,
        'Saída do dia':                    saida_plan_dt.strftime('%Y-%m-%d'),
        'Quilometragem':                   random.randint(30, 200),
        'Placa do carro':                  f'ABC{random.randint(1000,9999)}',
        'Modelo do veículo':               'VW Delivery',
        'Nome completo do transportador':  'JET SP TRANSPORTES LTDA',
        'Tipo de transportador':           'Próprio',
        'Abreviatura de transportador':    'JET SP',
        'Condutor':                        random.choice(condutores),
        'Telefone do carro':               '11999990000',
        'Código de estação de partida':    origem[:3].upper(),
        'Nome de estação de partida':      origem,
        'Regional de saída do carro':      regional,
        'Quantidade de encomendas escaneadas': random.randint(50, 300),
        'Número de Pedido mãe':            random.randint(100, 999),
        'Tempo de início do carregamento': (saida_plan_dt - timedelta(hours=1)).strftime('%Y-%m-%d %H:%M:%S'),
        'Tempo de término do carregamento':(saida_plan_dt - timedelta(minutes=30)).strftime('%Y-%m-%d %H:%M:%S'),
        'Tempo de carregamento (min)':     30,
        'Horario de carregamento passou das 20:00 hs?': 'Não',
        'hora de lacre':                   None,
        'Tempo de partida planejada':      saida_plan_dt.strftime('%Y-%m-%d %H:%M:%S'),
        'Horário real de saída':           saida_real,
        'Horário de check-out do condutor':None,
        'Código de estação de chegada':    'DST',
        'Nome de estação de chegada':      'DC SBN-SP',
        'Regional de chegada do carro':    regional,
        'Tempo de chegada planejado':      cheg_plan.strftime('%Y-%m-%d %H:%M:%S'),
        'Tempo real de chegada':           None,
        'Duração de atraso (min)':         None,
        'Horário de check-in do motorista':None,
        'hora de deslacre':                None,
        'Tempo de espera entre o check-in até o início do descarregamento (min)': None,
        'Tempo de início de descarga':     None,
        'Tempo de término de descarga':    None,
        'Tempo de descarregamento (min)':  None,
    }

t = lambda m: agora + timedelta(minutes=m)

# Próxima ocorrência de 08:00 (simula Devolução — hora < 13)
amanha_8h = (agora + timedelta(days=1)).replace(hour=8, minute=0, second=0, microsecond=0)

linhas = [
    # ── ALERTAM AGORA (dentro de 60min, hora >= 13h) ─────────────────────────
    # Coleta PA  (prioridade: origem começa com PA, hora não importa)
    make_row('Coleta',  'PA-Centro-SP', 'SPS', t(40)),
    make_row('Coleta',  'PA-Leste-SP',  'SPE', t(55)),
    # Coleta Base (Coleta + hora >= 13:00)
    make_row('Coleta',  'SP BRE',       'SPS', t(45)),
    make_row('Coleta',  'SJC-SP',       'SPE', t(50)),
    make_row('Coleta',  'SSZ-SP',       'SPS', t(30)),
    # Secundária  (Entrega)
    make_row('Entrega', 'SP BRE',       'SPS', t(45)),
    make_row('Entrega', 'SJC-SP',       'SPE', t(52)),
    make_row('Entrega', 'ABC-SP',       'SPE', t(38)),

    # ── DEVOLUÇÃO — alertaria às ~07:00 de amanhã (hora < 13h) ───────────────
    make_row('Coleta',  'SP BRE',       'SPS', amanha_8h),
    make_row('Coleta',  'SJC-SP',       'SPE', amanha_8h + timedelta(minutes=30)),

    # ── NÃO ALERTAM ──────────────────────────────────────────────────────────
    make_row('Entrega', 'SP BRE',       'SPS', t(90)),               # fora da janela
    make_row('Entrega', 'SP BRE',       'SPS', t(40), ja_saiu=True), # já saiu
    make_row('Coleta',  'SP BRE',       'MG',  t(40)),               # regional MG
    make_row('Entrega', 'SP BRE',       'SPS', t(40),
             status='Concluído：已完成'),                              # status errado
]

df = pd.DataFrame(linhas, columns=colunas)
out = str(Path(PASTA) / 'JMS_Teste.xlsx')
df.to_excel(out, index=False)

print(f'Criado: {out}  ({len(df)} linhas)')
print(f'\nAgora: {agora.strftime("%d/%m/%Y %H:%M")}')
print()
print(f'{"ALERTA?":8s} {"REG":4s} {"CATEGORIA":14s} {"ORIGEM":18s} {"SAÍDA PLAN.":18s} {"DIFF":>8s}')
print('-' * 80)
for _, r in df.iterrows():
    ts   = pd.to_datetime(r['Tempo de partida planejada'])
    diff = (ts - agora).total_seconds() / 60
    reg  = r['Regional de saída do carro']
    orig = str(r['Nome de estação de partida'])
    tipo = r['Tipo de linha']
    saiu = pd.notna(r['Horário real de saída'])
    prog = 'Programado' in str(r['Status'])

    if orig.upper().startswith('PA'):
        cat = 'Coleta PA'
    elif tipo == 'Coleta' and ts.hour < 13:
        cat = 'Devolução'
    elif tipo == 'Coleta':
        cat = 'Coleta Base'
    elif tipo == 'Entrega':
        cat = 'Secundária'
    else:
        cat = '?'

    vai_alertar = (0 <= diff <= 60) and not saiu and prog and reg in ('SPS','SPE')
    flag = 'ALERTA' if vai_alertar else '------'
    print(f'{flag:8s} {reg:4s} {cat:14s} {orig:18s} {ts.strftime("%d/%m %H:%M"):18s} {diff:+.0f}min')
