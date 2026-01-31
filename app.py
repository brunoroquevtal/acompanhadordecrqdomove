"""
Aplicação Principal - Janela de Mudança TI
Aplicação web interativa para gerenciamento de janelas de mudança de TI
"""
import streamlit as st
import pyperclip
import json
from datetime import datetime
from modules.database import DatabaseManager
from modules.data_loader import load_excel_file, merge_control_data, validate_excel_structure
from modules.dashboard import render_full_dashboard
from modules.data_editor import render_data_editor
from modules.message_builder import build_whatsapp_message
from modules.calculations import calculate_statistics
from modules.auth import (
    init_session_auth, is_authenticated, has_permission,
    can_edit_data, get_user_name, get_user_type, render_login_page, logout
)
from config import DATE_FORMAT


# Configuração da página
st.set_page_config(
    page_title="Janela de Mudança TI",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Inicializar autenticação
init_session_auth()

# Inicializar banco de dados
if "db_manager" not in st.session_state:
    st.session_state.db_manager = DatabaseManager()

# Inicializar session_state
if "data_dict" not in st.session_state:
    st.session_state.data_dict = {}
    st.session_state.current_file = None
    # Tentar carregar dados persistidos do banco apenas se não houver dados em memória
    try:
        saved_excel_data = st.session_state.db_manager.load_excel_data()
        if saved_excel_data:
            # Mesclar com dados de controle
            control_data = st.session_state.db_manager.get_all_activities_control()
            from modules.data_loader import merge_control_data
            st.session_state.data_dict = merge_control_data(saved_excel_data, control_data)
            st.session_state.current_file = "Dados persistidos do banco"
    except Exception as e:
        # Se houver erro ao carregar, continuar sem dados
        st.session_state.data_dict = {}
        st.session_state.current_file = None

if "has_unsaved_changes" not in st.session_state:
    st.session_state.has_unsaved_changes = False

if "current_file" not in st.session_state:
    st.session_state.current_file = None

# Verificar autenticação
if not is_authenticated():
    render_login_page()
    st.stop()


def load_data_from_excel(uploaded_file, show_success_message=True):
    """Carrega dados do Excel e mescla com dados de controle"""
    try:
        with st.spinner("Carregando dados do Excel..."):
            # Limpar cache antes de carregar novo arquivo
            load_excel_file.clear()
            
            # Carregar dados do Excel
            excel_data = load_excel_file(uploaded_file)
            
            if not excel_data:
                st.error("Erro ao carregar arquivo Excel")
                return False
            
            # Contar total de registros antes de salvar
            total_rows = sum(len(data["dataframe"]) for data in excel_data.values())
            
            # Salvar dados do Excel no banco PRIMEIRO (antes de mesclar)
            total_saved = st.session_state.db_manager.save_excel_data(excel_data, uploaded_file.name)
            if total_saved == 0:
                st.warning("⚠️ Nenhum registro foi salvo no banco. Verifique os dados do Excel.")
                return False
            
            # Carregar dados de controle do banco
            control_data = st.session_state.db_manager.get_all_activities_control()
            
            # Mesclar dados
            merged_data = merge_control_data(excel_data, control_data)
            
            # Salvar no session_state
            st.session_state.data_dict = merged_data
            st.session_state.current_file = uploaded_file.name
            
            # Inicializar dados de controle no banco se necessário
            for sequencia, data in merged_data.items():
                df = data["dataframe"]
                for _, row in df.iterrows():
                    seq = int(row["Seq"])
                    existing = st.session_state.db_manager.get_activity_control(seq, sequencia)
                    if not existing:
                        # Obter valor de Is_Milestone do dataframe (já detectado na importação)
                        is_milestone = row.get("Is_Milestone", False) if "Is_Milestone" in row else False
                        st.session_state.db_manager.save_activity_control(
                            seq=seq,
                            sequencia=sequencia,
                            status="Planejado",
                            is_milestone=is_milestone
                        )
            
            if show_success_message:
                st.success(f"✅ Dados carregados e persistidos com sucesso! ({total_saved} registros, {len(merged_data)} CRQs)")
            st.rerun()
            return True
    
    except Exception as e:
        st.error(f"Erro ao carregar dados: {str(e)}")
        import traceback
        st.code(traceback.format_exc())
        return False


def export_state():
    """Exporta estado atual para JSON"""
    if not st.session_state.data_dict:
        st.warning("Nenhum dado para exportar")
        return None
    
    export_data = {}
    
    for sequencia, data in st.session_state.data_dict.items():
        df = data["dataframe"]
        export_data[sequencia] = df.to_dict("records")
    
    return json.dumps(export_data, indent=2, default=str)


# Sidebar
with st.sidebar:
    st.title("🚀 Janela de Mudança TI")
    
    # Informações do usuário
    tipo_usuario = get_user_type()
    tipo_display = {
        "admin": "Administrador",
        "lider": "Líder da Mudança",
        "visualizador": "Visualizador"
    }.get(tipo_usuario, tipo_usuario.title() if tipo_usuario else "Desconhecido")
    st.info(f"👤 {get_user_name()}\n🔑 {tipo_display}")
    
    if st.button("🚪 Sair", width='stretch'):
        logout()
        st.rerun()
    
    st.divider()
    
    # Menu de navegação baseado em permissões
    st.subheader("📊 Navegação")
    
    pages_available = []
    if has_permission("dashboard"):
        pages_available.append("Dashboard")
    if has_permission("dados"):
        pages_available.append("Dados")
    if has_permission("mensagem"):
        pages_available.append("Comunicação")
    if has_permission("configuracoes"):
        pages_available.append("Configurações")
    
    if pages_available:
        page = st.radio(
            "Selecione a página:",
            pages_available,
            key="page_selector"
        )
    else:
        st.warning("Sem permissões de acesso")
        page = None
        st.stop()
    
    st.divider()
    
    # Gerenciamento de arquivo (apenas para administradores)
    if get_user_type() == "admin":
        st.subheader("📁 Gerenciamento de Arquivo")
        
        uploaded_file = st.file_uploader(
            "Carregar arquivo Excel",
            type=["xlsx", "xls"],
            key="file_uploader"
        )
        
        # Verificar se é um novo arquivo (não o mesmo que já está carregado)
        file_uploaded_key = "last_uploaded_file_name"
        if file_uploaded_key not in st.session_state:
            st.session_state[file_uploaded_key] = None
        
        if uploaded_file is not None:
            # Verificar se é um arquivo novo
            is_new_file = st.session_state[file_uploaded_key] != uploaded_file.name
            
            if st.button("📥 Carregar Dados", width='stretch'):
                if validate_excel_structure(uploaded_file):
                    load_data_from_excel(uploaded_file)
                    st.session_state[file_uploaded_key] = uploaded_file.name
                else:
                    st.error("Arquivo Excel inválido. Verifique a estrutura do arquivo.")
        
        if st.session_state.current_file:
            st.info(f"📄 Arquivo atual: {st.session_state.current_file}")
            
            col1, col2 = st.columns(2)
            
            with col1:
                if st.button("🔄 Atualizar", width='stretch'):
                    # Limpar cache e recarregar
                    load_excel_file.clear()
                    # Só recarregar se houver um arquivo selecionado E for diferente do atual
                    if uploaded_file is not None and uploaded_file.name != st.session_state.current_file:
                        load_data_from_excel(uploaded_file)
                        st.session_state[file_uploaded_key] = uploaded_file.name
                    else:
                        # Se não houver arquivo novo, apenas recarregar do banco (sem salvar Excel novamente)
                        saved_excel_data = st.session_state.db_manager.load_excel_data()
                        if saved_excel_data:
                            control_data = st.session_state.db_manager.get_all_activities_control()
                            from modules.data_loader import merge_control_data
                            st.session_state.data_dict = merge_control_data(saved_excel_data, control_data)
                            st.success("✅ Dados atualizados do banco!")
                            st.rerun()
                        else:
                            st.warning("⚠️ Nenhum dado encontrado no banco.")
            
            with col2:
                if st.button("🗑️ Limpar Cache", width='stretch'):
                    load_excel_file.clear()
                    st.session_state.data_dict = {}
                    st.session_state.current_file = None
                    st.success("✅ Cache limpo!")
                    st.rerun()
        
        # Opção para limpar todos os dados e reimportar
        st.divider()
        st.subheader("⚠️ Gerenciamento de Dados")
        st.warning("**Atenção:** A ação abaixo irá apagar TODOS os dados do banco (atividades e controles) e permitir uma nova importação.")
        
        if st.button("🗑️ Limpar Todos os Dados e Reimportar", width='stretch', type="secondary"):
            with st.spinner("Limpando todos os dados..."):
                # Limpar todos os dados do banco
                excel_count, control_count, success = st.session_state.db_manager.clear_all_data()
                # Limpar cache do Streamlit
                load_excel_file.clear()
                # Limpar session_state completamente
                st.session_state.data_dict = {}
                st.session_state.current_file = None
                st.session_state.has_unsaved_changes = False
                # Limpar todas as chaves relacionadas a processamento
                keys_to_remove = [key for key in list(st.session_state.keys()) if key.startswith("processing_") or key.startswith("last_hash_")]
                for key in keys_to_remove:
                    if key in st.session_state:
                        del st.session_state[key]
            
            if success:
                st.success(f"✅ Todos os dados foram apagados do banco! ({excel_count} registros Excel, {control_count} controles deletados). Agora você pode importar um novo arquivo Excel.")
            else:
                st.error("⚠️ Erro ao limpar alguns dados. Tente novamente.")
            st.rerun()
        
        # Exportar/Importar dados completos (para transferência entre máquinas)
        st.divider()
        st.subheader("🔄 Transferência de Dados entre Máquinas")
        st.info("💡 Use esta funcionalidade para transferir todos os dados (Excel + controles) entre máquinas de diferentes colaboradores.")
        
        col_export, col_import = st.columns(2)
        
        with col_export:
            st.markdown("#### 📤 Exportar Dados")
            if st.button("💾 Exportar Todos os Dados", width='stretch', type="primary"):
                try:
                    export_data = st.session_state.db_manager.export_all_data()
                    if export_data:
                        export_json = json.dumps(export_data, indent=2, default=str, ensure_ascii=False)
                        excel_count = export_data["metadata"]["excel_count"]
                        control_count = export_data["metadata"]["control_count"]
                        
                        st.success(f"✅ Dados exportados com sucesso! ({excel_count} registros Excel, {control_count} controles)")
                        
                        # Criar nome do arquivo com data/hora
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        filename = f"backup_janela_mudanca_{timestamp}.json"
                        
                        st.download_button(
                            label="📥 Baixar Arquivo de Backup",
                            data=export_json,
                            file_name=filename,
                            mime="application/json",
                            key="download_backup"
                        )
                    else:
                        st.warning("⚠️ Nenhum dado encontrado para exportar.")
                except Exception as e:
                    st.error(f"❌ Erro ao exportar dados: {str(e)}")
                    import traceback
                    with st.expander("Detalhes do erro"):
                        st.code(traceback.format_exc())
        
        with col_import:
            st.markdown("#### 📥 Importar Dados")
            uploaded_backup = st.file_uploader(
                "Selecione o arquivo de backup (.json)",
                type=["json"],
                key="backup_uploader"
            )
            
            if uploaded_backup is not None:
                if st.button("📥 Importar Dados do Backup", width='stretch', type="primary"):
                    try:
                        # Ler arquivo JSON
                        import_data = json.load(uploaded_backup)
                        
                        # Validar estrutura
                        if "excel_data" not in import_data or "control_data" not in import_data:
                            st.error("❌ Arquivo de backup inválido. Estrutura não reconhecida.")
                        else:
                            with st.spinner("Importando dados..."):
                                # Limpar cache
                                load_excel_file.clear()
                                
                                # Importar dados
                                excel_imported, control_imported, success = st.session_state.db_manager.import_all_data(import_data)
                                
                                if success:
                                    # Recarregar dados do banco para o session_state
                                    saved_excel_data = st.session_state.db_manager.load_excel_data()
                                    if saved_excel_data:
                                        control_data = st.session_state.db_manager.get_all_activities_control()
                                        from modules.data_loader import merge_control_data
                                        st.session_state.data_dict = merge_control_data(saved_excel_data, control_data)
                                        st.session_state.current_file = "Dados importados do backup"
                                    
                                    st.success(f"✅ Dados importados com sucesso! ({excel_imported} registros Excel, {control_imported} controles)")
                                    st.info("🔄 A página será recarregada para exibir os dados importados.")
                                    st.rerun()
                                else:
                                    st.error("❌ Erro ao importar alguns dados. Verifique o arquivo de backup.")
                    except json.JSONDecodeError:
                        st.error("❌ Erro: Arquivo JSON inválido.")
                    except Exception as e:
                        st.error(f"❌ Erro ao importar dados: {str(e)}")
                        import traceback
                        with st.expander("Detalhes do erro"):
                            st.code(traceback.format_exc())
        
        # Exportar estado (mantido para compatibilidade)
        if st.session_state.data_dict:
            st.divider()
            st.subheader("💾 Exportar Estado (Legado)")
            st.caption("⚠️ Esta opção exporta apenas o estado em memória. Para transferência completa entre máquinas, use a opção acima.")
            
            export_json = export_state()
            if export_json:
                st.download_button(
                    label="📤 Exportar Estado (JSON)",
                    data=export_json,
                    file_name=f"estado_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                    mime="application/json",
                    width='stretch'
                )
    else:
        # Para outros usuários, apenas mostrar arquivo atual se existir
        if st.session_state.current_file:
            st.info(f"📄 Arquivo atual: {st.session_state.current_file}")
            st.caption("💡 Apenas administradores podem carregar novos arquivos")
    
    # Indicador de mudanças não salvas
    if st.session_state.has_unsaved_changes:
        st.warning("⚠️ Há alterações não salvas")
    
    st.divider()
    st.markdown("**Versão:** 1.1.0")
    st.markdown("**Desenvolvido com Streamlit**")
    
    # Informações de acesso
    if can_edit_data():
        st.success("✅ Permissão de edição ativa")
    else:
        st.info("👁️ Modo visualização apenas")


# Conteúdo principal
if page == "Dashboard":
    st.header("📊 Dashboard Executivo")
    
    if st.session_state.data_dict:
        render_full_dashboard(st.session_state.data_dict)
    else:
        st.warning("⚠️ Nenhum dado carregado. Por favor, carregue um arquivo Excel primeiro na sidebar.")

elif page == "Dados":
    st.header("✏️ Editor de Dados")
    
    if not can_edit_data():
        st.error("❌ Você não tem permissão para editar dados. Apenas usuários Administrador e Líder da Mudança podem editar.")
        st.info("💡 Use a página Dashboard para visualizar os dados.")
    elif st.session_state.data_dict:
        render_data_editor(st.session_state.data_dict, st.session_state.db_manager)
    else:
        st.warning("⚠️ Nenhum dado carregado. Por favor, carregue um arquivo Excel primeiro na sidebar.")

elif page == "Comunicação":
    st.header("💬 Comunicação")
    
    if st.session_state.data_dict:
        # Gerar mensagem
        message = build_whatsapp_message(st.session_state.data_dict)
        
        # Botão para copiar
        col1, col2 = st.columns([1, 4])
        
        with col1:
            if st.button("📋 Copiar para Clipboard", width='stretch'):
                try:
                    pyperclip.copy(message)
                    st.success("✅ Mensagem copiada para clipboard!")
                except Exception as e:
                    # Fallback: mostrar código para copiar manualmente
                    st.warning("⚠️ Não foi possível copiar automaticamente. Use o código abaixo:")
                    st.code(message, language=None)
                    st.info("💡 Selecione o texto acima e pressione Ctrl+C para copiar")
        
        st.divider()
        
        # Preview da mensagem
        st.subheader("📄 Preview da Mensagem de Comunicação")
        st.markdown("---")
        # Mostrar mensagem formatada (markdown preserva quebras de linha com dois espaços)
        st.markdown(message.replace("\n", "  \n"))  # Dois espaços antes do \n força quebra no markdown
        st.markdown("---")
        
        # Estatísticas rápidas
        st.subheader("📈 Estatísticas Rápidas")
        stats = calculate_statistics(st.session_state.data_dict)
        geral = stats["geral"]
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Total", geral["total"])
        with col2:
            st.metric("Concluídas", geral["concluidas"], f"{geral.get('pct_concluidas', 0):.1f}%")
        with col3:
            st.metric("Em Execução", geral["em_execucao"], f"{geral.get('pct_em_execucao', 0):.1f}%")
        with col4:
            st.metric("Atrasadas", geral["atrasadas"], f"{geral.get('pct_atrasadas', 0):.1f}%")
        
        st.info("💡 A mensagem é atualizada automaticamente conforme os dados são editados.")
    
    else:
        st.warning("⚠️ Nenhum dado carregado. Por favor, carregue um arquivo Excel primeiro na sidebar.")

elif page == "Configurações":
    st.header("⚙️ Configurações")
    
    st.subheader("📋 Informações da Aplicação")
    st.markdown("""
    **Janela de Mudança TI** é uma aplicação web interativa para gerenciamento de janelas de mudança de TI.
    
    ### Funcionalidades:
    - ✅ Importação de dados de arquivo Excel
    - ✅ Edição interativa de dados em tempo real
    - ✅ Dashboard executivo com gráficos e indicadores
    - ✅ Geração automática de mensagem consolidada para WhatsApp
    - ✅ Persistência de dados em banco SQLite local
    
    ### Formato de Data/Hora:
    - Formato esperado: `DD/MM/AAAA HH:MM:SS`
    - Exemplo: `25/12/2024 14:30:00`
    
    ### Status Disponíveis:
    - **Planejado**: Atividade ainda não iniciada
    - **Em Execução**: Atividade em andamento
    - **Concluído**: Atividade finalizada
    - **Atrasado**: Atividade concluída com atraso
    - **Adiantado**: Atividade concluída antes do prazo
    
    ### Estrutura do Arquivo Excel:
    O arquivo Excel deve conter 4 abas com os seguintes nomes (ou contendo):
    - **REDE** (72 atividades)
    - **OPENSHIFT** (39 atividades)
    - **NFS** (17 atividades)
    - **SI** (25 atividades)
    
    Cada aba deve ter as seguintes colunas:
    - Seq, Atividade, Grupo, Localidade, Executor, Telefone, Inicio, Fim, Tempo
    (Nota: As colunas Localidade, Executor e Telefone são importadas mas não são exibidas por questões de segurança)
    """)
    
    st.divider()
    
    st.subheader("🔧 Informações Técnicas")
    st.markdown(f"""
    - **Banco de Dados**: SQLite local (`db/activity_control.db`)
    - **Formato de Data**: `{DATE_FORMAT}`
    - **Total de Atividades**: 153
    """)
    
    if st.session_state.data_dict:
        st.divider()
        st.subheader("📊 Status Atual")
        stats = calculate_statistics(st.session_state.data_dict)
        geral = stats["geral"]
        
        st.json({
            "Total": geral["total"],
            "Concluídas": geral["concluidas"],
            "Em Execução": geral["em_execucao"],
            "Planejadas": geral["planejadas"],
            "Atrasadas": geral["atrasadas"]
        })
