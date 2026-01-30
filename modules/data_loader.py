"""
Módulo para carregamento de dados do arquivo Excel
"""
import pandas as pd
import streamlit as st
from datetime import datetime
from config import EXCEL_COLUMNS, SEQUENCIAS


@st.cache_data(show_spinner="Carregando arquivo Excel...")
def load_excel_file(uploaded_file):
    """
    Carrega arquivo Excel e retorna dados de todas as abas
    
    Args:
        uploaded_file: Arquivo Excel carregado via Streamlit
        
    Returns:
        dict: Dicionário com dados de cada sequência
    """
    try:
        # Ler todas as abas do Excel
        excel_file = pd.ExcelFile(uploaded_file)
        sheet_names = excel_file.sheet_names
        
        dados = {}
        
        for sheet_name in sheet_names:
            # Identificar sequência pelo nome da aba
            sequencia = None
            for seq_key, seq_info in SEQUENCIAS.items():
                if seq_key in sheet_name.upper():
                    sequencia = seq_key
                    break
            
            if not sequencia:
                # Tentar identificar por padrão
                if "REDE" in sheet_name.upper():
                    sequencia = "REDE"
                elif "OPENSHIFT" in sheet_name.upper():
                    sequencia = "OPENSHIFT"
                elif "NFS" in sheet_name.upper():
                    sequencia = "NFS"
                elif "SI" in sheet_name.upper():
                    sequencia = "SI"
                else:
                    # Pular abas não reconhecidas
                    continue
            
            # Ler aba
            df = pd.read_excel(uploaded_file, sheet_name=sheet_name)
            
            # Verificar se já tem cabeçalhos corretos
            expected_cols = ["Seq", "Atividade", "Grupo", "Localidade", 
                            "Executor", "Telefone", "Inicio", "Fim", "Tempo"]
            
            # Se as colunas já estão corretas, usar como estão
            if list(df.columns[:9]) == expected_cols:
                df = df.iloc[:, :9]  # Manter apenas as 9 primeiras colunas
            elif len(df.columns) >= 9:
                # Mapear colunas (assumindo que as colunas estão na ordem correta)
                df = df.iloc[:, :9]  # Pegar apenas as 9 primeiras colunas
                df.columns = expected_cols
            else:
                # Se não tiver cabeçalhos ou estrutura diferente, tentar mapear
                st.warning(f"Estrutura da aba {sheet_name} pode estar incorreta. Esperado: 9 colunas, encontrado: {len(df.columns)}")
                continue
            
            # Limpar dados
            df = df.dropna(subset=["Seq", "Atividade"])  # Remover linhas sem Seq ou Atividade
            
            # Converter tipos
            try:
                df["Seq"] = pd.to_numeric(df["Seq"], errors='coerce').astype('Int64')
                df = df.dropna(subset=["Seq"])  # Remover linhas sem Seq válido
            except Exception:
                st.warning(f"Erro ao converter Seq na aba {sheet_name}")
                continue
            
            # Converter datas
            for col in ["Inicio", "Fim"]:
                if col in df.columns:
                    df[col] = pd.to_datetime(df[col], errors='coerce')
            
            # Converter colunas de texto para string (evitar tipos mistos)
            # Função robusta para converter qualquer tipo para string
            def safe_str_convert(val):
                if pd.isna(val) or val is None:
                    return ""
                try:
                    if isinstance(val, (int, float)):
                        return str(int(val)) if isinstance(val, float) and val.is_integer() else str(val)
                    return str(val)
                except:
                    return ""
            
            for col in ["Telefone", "Grupo", "Localidade", "Executor", "Tempo", "Atividade"]:
                if col in df.columns:
                    df[col] = df[col].apply(safe_str_convert)
            
            # Adicionar CRQ ao dataframe
            df["CRQ"] = sequencia
            
            dados[sequencia] = {
                "dataframe": df,
                "sheet_name": sheet_name
            }
        
        return dados
    
    except Exception as e:
        st.error(f"Erro ao carregar arquivo Excel: {str(e)}")
        return None


def merge_control_data(excel_data, control_data):
    """
    Mescla dados do Excel com dados de controle do banco
    
    Args:
        excel_data: Dados carregados do Excel
        control_data: Dados de controle do banco de dados
        
    Returns:
        dict: Dados mesclados
    """
    merged_data = {}
    
    for sequencia, data in excel_data.items():
        df = data["dataframe"].copy()
        
        # Adicionar colunas de controle
        df["Status"] = "Planejado"
        df["Horario_Inicio_Real"] = None
        df["Horario_Fim_Real"] = None
        df["Atraso_Minutos"] = 0
        df["Observacoes"] = ""
        df["Is_Milestone"] = False
        df["Predecessoras"] = ""
        
        # Marcar como milestone linhas com Tempo vazio ou zero
        if "Tempo" in df.columns:
            for idx, row in df.iterrows():
                tempo_value = row.get("Tempo")
                # Verificar se Tempo está vazio (NaN), string vazia, ou é zero (qualquer tipo)
                is_empty_or_zero = (
                    pd.isna(tempo_value) or 
                    tempo_value == "" or 
                    tempo_value == 0 or 
                    tempo_value == "0" or
                    tempo_value == 0.0 or
                    (isinstance(tempo_value, str) and tempo_value.strip() == "")
                )
                if is_empty_or_zero:
                    df.at[idx, "Is_Milestone"] = True
        
        # Preencher com dados de controle existentes
        for idx, row in df.iterrows():
            seq = int(row["Seq"])
            key = f"{seq}_{sequencia}"
            
            if key in control_data:
                control = control_data[key]
                df.at[idx, "Status"] = control.get("status", "Planejado")
                df.at[idx, "Horario_Inicio_Real"] = control.get("horario_inicio_real")
                df.at[idx, "Horario_Fim_Real"] = control.get("horario_fim_real")
                df.at[idx, "Atraso_Minutos"] = control.get("atraso_minutos", 0)
                df.at[idx, "Observacoes"] = control.get("observacoes", "")
                # Se já existe milestone no banco, manter o valor do banco
                # Caso contrário, usar o valor detectado do Excel
                if control.get("is_milestone", False):
                    df.at[idx, "Is_Milestone"] = True
                # Se não está no banco mas foi detectado como milestone, manter True
                # (já foi definido acima)
                df.at[idx, "Predecessoras"] = control.get("predecessoras", "")
        
        merged_data[sequencia] = {
            "dataframe": df,
            "sheet_name": data["sheet_name"]
        }
    
    return merged_data


def validate_excel_structure(uploaded_file):
    """
    Valida se o arquivo Excel tem a estrutura esperada
    
    Args:
        uploaded_file: Arquivo Excel carregado
        
    Returns:
        bool: True se válido, False caso contrário
    """
    try:
        excel_file = pd.ExcelFile(uploaded_file)
        
        if len(excel_file.sheet_names) == 0:
            return False
        
        # Verificar se pelo menos uma aba tem estrutura válida
        for sheet_name in excel_file.sheet_names[:1]:  # Verificar primeira aba
            df = pd.read_excel(uploaded_file, sheet_name=sheet_name, nrows=5)
            if len(df.columns) < 5:  # Mínimo de colunas esperadas
                return False
        
        return True
    
    except Exception:
        return False
