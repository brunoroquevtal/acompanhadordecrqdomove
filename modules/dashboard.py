"""
Módulo para componentes do dashboard
"""
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from modules.calculations import (
    calculate_statistics, get_activities_by_status,
    get_delayed_activities, get_next_activities,
    get_milestones, get_activities_blocked_by_dependencies
)
from modules.ui import render_status_card, render_sequence_status_card


def render_main_indicators(stats):
    """
    Renderiza indicadores principais (cards)
    
    Args:
        stats: Estatísticas calculadas
    """
    st.subheader("📊 Indicadores Principais")
    
    col1, col2, col3, col4, col5 = st.columns(5)
    
    geral = stats["geral"]
    
    with col1:
        render_status_card("Total de Atividades", geral["total"])
    
    with col2:
        pct = geral.get("pct_concluidas", 0)
        render_status_card(
            "✅ Concluídas",
            f"{geral['concluidas']} ({pct:.1f}%)",
            delta=None
        )
    
    with col3:
        pct = geral.get("pct_em_execucao", 0)
        render_status_card(
            "⏳ Em Execução",
            f"{geral['em_execucao']} ({pct:.1f}%)",
            delta=None
        )
    
    with col4:
        pct = geral.get("pct_planejadas", 0)
        render_status_card(
            "🟡 Planejadas",
            f"{geral['planejadas']} ({pct:.1f}%)",
            delta=None
        )
    
    with col5:
        pct = geral.get("pct_atrasadas", 0)
        render_status_card(
            "🔴 Atrasadas",
            f"{geral['atrasadas']} ({pct:.1f}%)",
            delta="negative" if geral['atrasadas'] > 0 else None
        )
    
    st.divider()


def render_burndown_chart(data_dict, crq_filtro=None):
    """
    Renderiza gráfico Burndown com tempo no eixo horizontal
    Apenas atividades "Concluídas" reduzem o trabalho restante.
    Outros status (Em Execução, Atrasado, Adiantado) são tratados como "Planejado".
    
    Args:
        data_dict: Dicionário com dataframes
        crq_filtro: CRQ específico para filtrar (None para todas)
    """
    import pandas as pd
    from datetime import datetime
    from config import SEQUENCIAS, DATE_FORMAT
    from modules.calculations import parse_datetime_string
    
    # Filtro por CRQ
    col1, col2 = st.columns([1, 3])
    with col1:
        crqs_disponiveis = ["Todas"] + sorted(list(data_dict.keys()))
        crq_selecionado = st.selectbox(
            "Filtrar por CRQ:",
            crqs_disponiveis,
            key="burndown_crq_filter",
            index=0
        )
    
    # Determinar qual CRQ usar
    if crq_selecionado == "Todas":
        crqs_para_processar = sorted(list(data_dict.keys()))
    else:
        if crq_selecionado in data_dict:
            crqs_para_processar = [crq_selecionado]
        else:
            st.warning(f"CRQ '{crq_selecionado}' não encontrado")
            return
    
    # Coletar todas as atividades e calcular totais
    all_activities = []
    total_atividades = 0
    
    for crq in crqs_para_processar:
        if crq not in data_dict:
            continue
        
        df = data_dict[crq]["dataframe"].copy()
        
        # Excluir milestones das contagens
        if "Is_Milestone" in df.columns:
            df = df[df["Is_Milestone"].fillna(False) == False]
        
        total_atividades += len(df)
        
        # Coletar atividades concluídas com data de fim real
        for _, row in df.iterrows():
            status = row.get("Status", "Planejado")
            if status == "Concluído":
                horario_fim_real = row.get("Horario_Fim_Real")
                if horario_fim_real and pd.notna(horario_fim_real) and str(horario_fim_real).strip():
                    try:
                        # Tentar parsear a data
                        if isinstance(horario_fim_real, str):
                            dt = parse_datetime_string(horario_fim_real)
                        elif hasattr(horario_fim_real, 'to_pydatetime'):
                            dt = horario_fim_real.to_pydatetime()
                        elif isinstance(horario_fim_real, datetime):
                            dt = horario_fim_real
                        else:
                            continue
                        
                        if dt:
                            all_activities.append({
                                'data': dt,
                                'crq': crq
                            })
                    except:
                        continue
    
    if total_atividades == 0:
        st.info("Não há atividades para exibir")
        return
    
    # Ordenar atividades por data
    all_activities.sort(key=lambda x: x['data'])
    
    # Calcular burndown ao longo do tempo
    if not all_activities:
        # Se não há atividades concluídas, mostrar apenas o total
        timestamps = [datetime.now()]
        restantes = [total_atividades]
        concluidas = [0]
    else:
        # Criar pontos temporais: início (total) + cada conclusão
        timestamps = []
        restantes = []
        concluidas = []
        
        # Ponto inicial: todas as atividades ainda pendentes
        if all_activities:
            # Usar a primeira data de conclusão ou data atual como início
            primeira_data = all_activities[0]['data']
            timestamps.append(primeira_data)
            restantes.append(total_atividades)
            concluidas.append(0)
        
        # Adicionar pontos para cada atividade concluída
        concluidas_count = 0
        for activity in all_activities:
            concluidas_count += 1
            timestamps.append(activity['data'])
            restantes.append(total_atividades - concluidas_count)
            concluidas.append(concluidas_count)
        
        # Adicionar ponto final (atual)
        timestamps.append(datetime.now())
        restantes.append(total_atividades - concluidas_count)
        concluidas.append(concluidas_count)
    
    # Criar gráfico Burndown
    fig = go.Figure()
    
    # Linha do trabalho restante (real)
    fig.add_trace(go.Scatter(
        x=timestamps,
        y=restantes,
        mode='lines+markers',
        name='Trabalho Restante (Real)',
        line=dict(color='#dc3545', width=3),
        marker=dict(size=8, color='#dc3545'),
        hovertemplate='<b>%{x|%d/%m/%Y %H:%M:%S}</b><br>Trabalho Restante: %{y} atividades<extra></extra>',
        fill='tozeroy',
        fillcolor='rgba(220, 53, 69, 0.1)'
    ))
    
    # Linha do trabalho total (inicial) - constante
    if timestamps:
        fig.add_trace(go.Scatter(
            x=[timestamps[0], timestamps[-1]],
            y=[total_atividades, total_atividades],
            mode='lines',
            name='Total de Atividades',
            line=dict(color='#6c757d', width=2, dash='dash'),
            hovertemplate='Total: %{y} atividades<extra></extra>'
        ))
    
    # Linha das concluídas acumuladas (para referência)
    fig.add_trace(go.Scatter(
        x=timestamps,
        y=concluidas,
        mode='lines+markers',
        name='Concluídas (Acumulado)',
        line=dict(color='#28a745', width=2),
        marker=dict(size=6, color='#28a745'),
        hovertemplate='<b>%{x|%d/%m/%Y %H:%M:%S}</b><br>Concluídas: %{y} atividades<extra></extra>'
    ))
    
    # Configurar layout
    titulo = f'📉 Gráfico Burndown - Trabalho Restante ao Longo do Tempo'
    if crq_selecionado != "Todas":
        crq_info = SEQUENCIAS.get(crq_selecionado, {})
        nome_crq = crq_info.get("nome", crq_selecionado)
        titulo += f' ({nome_crq})'
    
    fig.update_layout(
        title={
            'text': titulo,
            'x': 0.5,
            'xanchor': 'center',
            'font': {'size': 18}
        },
        xaxis_title="Data/Hora",
        yaxis_title="Quantidade de Atividades",
        hovermode='x unified',
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        ),
        height=500,
        yaxis=dict(
            rangemode='tozero',
            gridcolor='lightgray',
            gridwidth=1
        ),
        xaxis=dict(
            gridcolor='lightgray',
            gridwidth=1,
            type='date',
            tickformat='%d/%m/%Y %H:%M'
        ),
        plot_bgcolor='white'
    )
    
    st.plotly_chart(fig, width='stretch')
    
    # Adicionar informações adicionais
    st.info("ℹ️ **Como funciona o Burndown:**\n"
           "- Apenas atividades **Concluídas** reduzem o trabalho restante\n"
           "- Status como Em Execução, Atrasado e Adiantado são tratados como Planejado (não reduzem o total)\n"
           "- O trabalho restante = Total - Concluídas")


def render_activities_tables(data_dict):
    """
    Renderiza tabelas de detalhes
    
    Args:
        data_dict: Dicionário com dataframes
    """
    st.subheader("📋 Tabelas de Detalhes")
    
    # Tabela 1: Atividades em Execução (segmentada por CRQ)
    st.markdown("#### ⏳ Atividades em Execução")
    exec_df = get_activities_by_status(data_dict, "Em Execução")
    
    if len(exec_df) > 0:
        # Agrupar por CRQ
        if "CRQ" in exec_df.columns:
            for crq in sorted(exec_df["CRQ"].unique()):
                crq_df = exec_df[exec_df["CRQ"] == crq].copy()
                from config import SEQUENCIAS
                crq_info = SEQUENCIAS.get(crq, {})
                emoji = crq_info.get("emoji", "📊")
                nome = crq_info.get("nome", crq)
                
                st.markdown(f"**{emoji} {nome}** ({len(crq_df)} atividades)")
                display_cols = ["Seq", "Atividade", "Executor", "Tempo", "Horario_Inicio_Real"]
                available_cols = [col for col in display_cols if col in crq_df.columns]
                crq_display = crq_df[available_cols].sort_values("Seq")
                st.dataframe(crq_display, width='stretch', hide_index=True)
                st.divider()
        else:
            display_cols = ["Seq", "Atividade", "Executor", "Tempo", "Horario_Inicio_Real"]
            available_cols = [col for col in display_cols if col in exec_df.columns]
            exec_display = exec_df[available_cols].sort_values("Seq")
            st.dataframe(exec_display, width='stretch', hide_index=True)
    else:
        st.info("Não há atividades em execução no momento")
    
    st.divider()
    
    # Tabela 2: Atividades Atrasadas (segmentada por CRQ)
    st.markdown("#### 🚨 Atividades Atrasadas")
    delayed_df = get_delayed_activities(data_dict)
    
    if len(delayed_df) > 0:
        from modules.calculations import format_delay
        delayed_display = delayed_df.copy()
        delayed_display["Atraso"] = delayed_display["Atraso_Minutos"].apply(format_delay)
        
        # Agrupar por CRQ
        if "CRQ" in delayed_display.columns:
            for crq in sorted(delayed_display["CRQ"].unique()):
                crq_df = delayed_display[delayed_display["CRQ"] == crq].copy()
                from config import SEQUENCIAS
                crq_info = SEQUENCIAS.get(crq, {})
                emoji = crq_info.get("emoji", "📊")
                nome = crq_info.get("nome", crq)
                
                st.markdown(f"**{emoji} {nome}** ({len(crq_df)} atividades)")
                display_cols = ["Seq", "Atividade", "Executor", "Atraso", "Observacoes"]
                available_cols = [col for col in display_cols if col in crq_df.columns]
                # Ordenar antes de filtrar colunas (usando Atraso_Minutos que existe no DataFrame original)
                if "Atraso_Minutos" in crq_df.columns:
                    crq_df_sorted = crq_df.sort_values("Atraso_Minutos", ascending=False)
                else:
                    crq_df_sorted = crq_df
                crq_display = crq_df_sorted[available_cols]
                st.dataframe(crq_display, width='stretch', hide_index=True)
                st.divider()
        else:
            display_cols = ["Seq", "Atividade", "Executor", "Atraso", "Observacoes"]
            available_cols = [col for col in display_cols if col in delayed_display.columns]
            # Ordenar antes de filtrar colunas (usando Atraso_Minutos que existe no DataFrame original)
            if "Atraso_Minutos" in delayed_display.columns:
                delayed_display_sorted = delayed_display.sort_values("Atraso_Minutos", ascending=False)
            else:
                delayed_display_sorted = delayed_display
            delayed_display_final = delayed_display_sorted[available_cols]
            st.dataframe(delayed_display_final, width='stretch', hide_index=True)
    else:
        st.info("Não há atividades atrasadas")
    
    st.divider()
    
    # Tabela 3: Próximas Atividades (segmentada por CRQ)
    st.markdown("#### 📅 Próximas Atividades a Executar")
    next_df = get_next_activities(data_dict, limit=10)
    
    if len(next_df) > 0:
        # Agrupar por CRQ
        if "CRQ" in next_df.columns:
            for crq in sorted(next_df["CRQ"].unique()):
                crq_df = next_df[next_df["CRQ"] == crq].copy()
                from config import SEQUENCIAS
                crq_info = SEQUENCIAS.get(crq, {})
                emoji = crq_info.get("emoji", "📊")
                nome = crq_info.get("nome", crq)
                
                st.markdown(f"**{emoji} {nome}** ({len(crq_df)} atividades)")
                display_cols = ["Seq", "Atividade", "Executor", "Inicio"]
                available_cols = [col for col in display_cols if col in crq_df.columns]
                crq_display = crq_df[available_cols].sort_values("Inicio")
                
                # Formatar data
                if "Inicio" in crq_display.columns:
                    crq_display["Inicio"] = crq_display["Inicio"].apply(
                        lambda x: x.strftime("%d/%m/%Y %H:%M:%S") if pd.notna(x) and hasattr(x, 'strftime') else ""
                    )
                
                st.dataframe(crq_display, width='stretch', hide_index=True)
                st.divider()
        else:
            display_cols = ["Seq", "Atividade", "Executor", "Inicio"]
            available_cols = [col for col in display_cols if col in next_df.columns]
            next_display = next_df[available_cols].sort_values("Inicio")
            
            # Formatar data
            if "Inicio" in next_display.columns:
                next_display["Inicio"] = next_display["Inicio"].apply(
                    lambda x: x.strftime("%d/%m/%Y %H:%M:%S") if pd.notna(x) and hasattr(x, 'strftime') else ""
                )
            
            st.dataframe(next_display, width='stretch', hide_index=True)
    else:
        st.info("Não há próximas atividades planejadas")
    
    st.divider()
    
    # Tabela 4: Atividades Bloqueadas por Dependências (segmentada por CRQ)
    st.markdown("#### 🔒 Atividades Bloqueadas por Dependências")
    blocked_df = get_activities_blocked_by_dependencies(data_dict)
    
    if len(blocked_df) > 0:
        # Agrupar por CRQ
        if "CRQ" in blocked_df.columns:
            for crq in sorted(blocked_df["CRQ"].unique()):
                crq_df = blocked_df[blocked_df["CRQ"] == crq].copy()
                from config import SEQUENCIAS
                crq_info = SEQUENCIAS.get(crq, {})
                emoji = crq_info.get("emoji", "📊")
                nome = crq_info.get("nome", crq)
                
                st.markdown(f"**{emoji} {nome}** ({len(crq_df)} atividades bloqueadas)")
                display_cols = ["Seq", "Atividade", "Status", "Predecessoras", "Predecessoras_Pendentes"]
                available_cols = [col for col in display_cols if col in crq_df.columns]
                crq_display = crq_df[available_cols].sort_values("Seq")
                st.dataframe(crq_display, width='stretch', hide_index=True)
                st.divider()
        else:
            display_cols = ["Seq", "Atividade", "Status", "Predecessoras", "Predecessoras_Pendentes"]
            available_cols = [col for col in display_cols if col in blocked_df.columns]
            blocked_display = blocked_df[available_cols].sort_values("Seq")
            st.dataframe(blocked_display, width='stretch', hide_index=True)
        
        st.warning("⚠️ Estas atividades não podem ser iniciadas até que suas predecessoras sejam concluídas.")
    else:
        st.info("✅ Não há atividades bloqueadas por dependências")
    
    st.divider()


def render_sequence_status_cards(stats):
    """
    Renderiza cards de status por CRQ
    
    Args:
        stats: Estatísticas calculadas
    """
    st.subheader("📊 Status por CRQ")
    
    from config import SEQUENCIAS
    
    for sequencia_key, sequencia_info in SEQUENCIAS.items():
        if sequencia_key in stats["por_sequencia"]:
            seq_stats = stats["por_sequencia"][sequencia_key]
            # Usar total real (sem milestones) em vez do config
            total = seq_stats["total"]
            render_sequence_status_card(sequencia_key, seq_stats, total)


def render_full_dashboard(data_dict):
    """
    Renderiza dashboard completo
    
    Args:
        data_dict: Dicionário com dataframes
    """
    if not data_dict:
        st.warning("⚠️ Nenhum dado carregado. Por favor, carregue um arquivo Excel primeiro.")
        return
    
    # Calcular estatísticas
    stats = calculate_statistics(data_dict)
    
    # Indicadores principais
    render_main_indicators(stats)
    
    st.divider()
    
    # Tabelas de detalhes
    render_activities_tables(data_dict)
    
    # Status por CRQ
    render_sequence_status_cards(stats)
