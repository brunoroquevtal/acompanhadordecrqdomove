"""
Módulo para gerenciamento do banco de dados SQLite
"""
import sqlite3
import os
from datetime import datetime
from config import DB_PATH


class DatabaseManager:
    """Gerenciador do banco de dados SQLite"""
    
    def __init__(self):
        self.db_path = DB_PATH
        self.init_database()
    
    def get_connection(self):
        """Retorna conexão com o banco de dados"""
        return sqlite3.connect(self.db_path)
    
    def init_database(self):
        """Inicializa o banco de dados e cria tabelas se não existirem"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS activity_control (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                seq INTEGER,
                sequencia TEXT,
                status TEXT DEFAULT 'Planejado',
                horario_inicio_real TEXT,
                horario_fim_real TEXT,
                atraso_minutos INTEGER DEFAULT 0,
                observacoes TEXT,
                is_milestone INTEGER DEFAULT 0,
                predecessoras TEXT,
                data_criacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                data_atualizacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(seq, sequencia)
            )
        """)
        
        # Adicionar novas colunas se a tabela já existir (migração)
        try:
            cursor.execute("ALTER TABLE activity_control ADD COLUMN is_milestone INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass  # Coluna já existe
        
        try:
            cursor.execute("ALTER TABLE activity_control ADD COLUMN predecessoras TEXT")
        except sqlite3.OperationalError:
            pass  # Coluna já existe
        
        # Criar índices para melhor performance
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_seq_sequencia 
            ON activity_control(seq, sequencia)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_status 
            ON activity_control(status)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_sequencia 
            ON activity_control(sequencia)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_seq 
            ON activity_control(seq)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_is_milestone 
            ON activity_control(is_milestone)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_status_sequencia 
            ON activity_control(status, sequencia)
        """)
        
        # Criar tabela para persistir dados base do Excel
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS excel_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sequencia TEXT,
                seq INTEGER,
                atividade TEXT,
                grupo TEXT,
                localidade TEXT,
                executor TEXT,
                telefone TEXT,
                inicio TEXT,
                fim TEXT,
                tempo TEXT,
                data_importacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(sequencia, seq)
            )
        """)
        
        # Criar índices para excel_data
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_excel_sequencia 
            ON excel_data(sequencia)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_excel_seq_sequencia 
            ON excel_data(seq, sequencia)
        """)
        
        conn.commit()
        conn.close()
    
    def get_activity_control(self, seq, sequencia):
        """Busca dados de controle de uma atividade específica"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT status, horario_inicio_real, horario_fim_real, 
                   atraso_minutos, observacoes, is_milestone, predecessoras
            FROM activity_control
            WHERE seq = ? AND sequencia = ?
        """, (seq, sequencia))
        
        result = cursor.fetchone()
        conn.close()
        
        if result:
            return {
                "status": result[0],
                "horario_inicio_real": result[1],
                "horario_fim_real": result[2],
                "atraso_minutos": result[3],
                "observacoes": result[4],
                "is_milestone": bool(result[5]) if result[5] is not None else False,
                "predecessoras": result[6] if result[6] else ""
            }
        return None
    
    def save_activity_control(self, seq, sequencia, status=None, 
                             horario_inicio_real=None, horario_fim_real=None,
                             atraso_minutos=None, observacoes=None,
                             is_milestone=None, predecessoras=None):
        """Salva ou atualiza dados de controle de uma atividade"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Verificar se já existe
        existing = self.get_activity_control(seq, sequencia)
        
        if existing:
            # Atualizar
            updates = []
            params = []
            
            if status is not None:
                updates.append("status = ?")
                params.append(status)
            if horario_inicio_real is not None:
                updates.append("horario_inicio_real = ?")
                params.append(horario_inicio_real)
            if horario_fim_real is not None:
                updates.append("horario_fim_real = ?")
                params.append(horario_fim_real)
            if atraso_minutos is not None:
                updates.append("atraso_minutos = ?")
                params.append(atraso_minutos)
            if observacoes is not None:
                updates.append("observacoes = ?")
                params.append(observacoes)
            if is_milestone is not None:
                updates.append("is_milestone = ?")
                params.append(1 if is_milestone else 0)
            if predecessoras is not None:
                updates.append("predecessoras = ?")
                params.append(predecessoras)
            
            updates.append("data_atualizacao = ?")
            params.append(datetime.now().isoformat())
            params.extend([seq, sequencia])
            
            cursor.execute(f"""
                UPDATE activity_control
                SET {', '.join(updates)}
                WHERE seq = ? AND sequencia = ?
            """, params)
        else:
            # Inserir novo
            cursor.execute("""
                INSERT INTO activity_control 
                (seq, sequencia, status, horario_inicio_real, horario_fim_real, 
                 atraso_minutos, observacoes, is_milestone, predecessoras)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (seq, sequencia, 
                  status or "Planejado",
                  horario_inicio_real,
                  horario_fim_real,
                  atraso_minutos or 0,
                  observacoes,
                  1 if is_milestone else 0,
                  predecessoras or ""))
        
        conn.commit()
        conn.close()
    
    def get_all_activities_control(self):
        """Retorna todos os dados de controle"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT seq, sequencia, status, horario_inicio_real, 
                   horario_fim_real, atraso_minutos, observacoes,
                   is_milestone, predecessoras
            FROM activity_control
        """)
        
        results = cursor.fetchall()
        conn.close()
        
        activities = {}
        for row in results:
            seq, sequencia = row[0], row[1]
            key = f"{seq}_{sequencia}"
            activities[key] = {
                "seq": seq,
                "sequencia": sequencia,
                "status": row[2],
                "horario_inicio_real": row[3],
                "horario_fim_real": row[4],
                "atraso_minutos": row[5],
                "observacoes": row[6],
                "is_milestone": bool(row[7]) if row[7] is not None else False,
                "predecessoras": row[8] if row[8] else ""
            }
        
        return activities
    
    def clear_all_control_data(self):
        """Limpa todos os dados de controle (útil para reset)"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM activity_control")
        
        conn.commit()
        conn.close()
    
    def bulk_save_activities(self, activities_data):
        """Salva múltiplas atividades de uma vez"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        for activity in activities_data:
            cursor.execute("""
                INSERT OR REPLACE INTO activity_control
                (seq, sequencia, status, horario_inicio_real, horario_fim_real,
                 atraso_minutos, observacoes, data_atualizacao)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                activity["seq"],
                activity["sequencia"],
                activity.get("status", "Planejado"),
                activity.get("horario_inicio_real"),
                activity.get("horario_fim_real"),
                activity.get("atraso_minutos", 0),
                activity.get("observacoes"),
                datetime.now().isoformat()
            ))
        
        conn.commit()
        conn.close()
    
    def save_excel_data(self, data_dict, file_name=None):
        """
        Salva dados do Excel no banco de dados
        
        Args:
            data_dict: Dicionário com dataframes de cada sequência
            file_name: Nome do arquivo Excel (opcional)
        """
        import pandas as pd
        
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Limpar dados antigos do Excel
        cursor.execute("DELETE FROM excel_data")
        conn.commit()
        
        # Contador de registros salvos
        total_saved = 0
        
        # Salvar novos dados
        for sequencia, data in data_dict.items():
            df = data["dataframe"]
            for _, row in df.iterrows():
                try:
                    # Converter datas para string ISO
                    inicio_str = None
                    fim_str = None
                    
                    if "Inicio" in row and pd.notna(row["Inicio"]):
                        if hasattr(row["Inicio"], 'isoformat'):
                            inicio_str = row["Inicio"].isoformat()
                        elif isinstance(row["Inicio"], str):
                            inicio_str = row["Inicio"]
                        else:
                            inicio_str = str(row["Inicio"])
                    
                    if "Fim" in row and pd.notna(row["Fim"]):
                        if hasattr(row["Fim"], 'isoformat'):
                            fim_str = row["Fim"].isoformat()
                        elif isinstance(row["Fim"], str):
                            fim_str = row["Fim"]
                        else:
                            fim_str = str(row["Fim"])
                    
                    # Converter Seq para int
                    seq_value = None
                    if "Seq" in row and pd.notna(row["Seq"]):
                        try:
                            seq_value = int(row["Seq"])
                        except (ValueError, TypeError):
                            continue  # Pular se não conseguir converter
                    
                    if seq_value is None:
                        continue  # Pular se Seq for None
                    
                    cursor.execute("""
                        INSERT OR REPLACE INTO excel_data
                        (sequencia, seq, atividade, grupo, localidade, executor, 
                         telefone, inicio, fim, tempo)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        sequencia,
                        seq_value,
                        str(row.get("Atividade", "")),
                        str(row.get("Grupo", "")),
                        str(row.get("Localidade", "")),
                        str(row.get("Executor", "")),
                        str(row.get("Telefone", "")),
                        inicio_str,
                        fim_str,
                        str(row.get("Tempo", ""))
                    ))
                    total_saved += 1
                except Exception as e:
                    # Log do erro mas continua
                    print(f"Erro ao salvar linha {row.get('Seq', 'N/A')} da sequência {sequencia}: {e}")
                    continue
        
        conn.commit()
        conn.close()
        
        return total_saved
    
    def load_excel_data(self):
        """
        Carrega dados do Excel salvos no banco de dados
        
        Returns:
            dict: Dicionário com dataframes de cada sequência ou None se não houver dados
        """
        import pandas as pd
        
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT sequencia, seq, atividade, grupo, localidade, executor, 
                   telefone, inicio, fim, tempo
            FROM excel_data
            ORDER BY sequencia, seq
        """)
        
        results = cursor.fetchall()
        conn.close()
        
        if not results:
            return None
        
        # Agrupar por sequência e criar lista de dados
        data_by_sequence = {}
        for row in results:
            sequencia = row[0]
            if sequencia not in data_by_sequence:
                data_by_sequence[sequencia] = []
            
            # Converter datas
            inicio = None
            fim = None
            try:
                if row[7]:
                    inicio = pd.to_datetime(row[7], errors='coerce')
                if row[8]:
                    fim = pd.to_datetime(row[8], errors='coerce')
            except:
                pass
            
            data_by_sequence[sequencia].append({
                "Seq": int(row[1]) if row[1] is not None else None,
                "Atividade": row[2] or "",
                "Grupo": row[3] or "",
                "Localidade": row[4] or "",
                "Executor": row[5] or "",
                "Telefone": row[6] or "",
                "Inicio": inicio,
                "Fim": fim,
                "Tempo": row[9] or "",
                "CRQ": sequencia
            })
        
        # Criar dataframes para cada sequência
        data_dict = {}
        for sequencia, rows in data_by_sequence.items():
            if rows:
                # Criar DataFrame com tipos explícitos para evitar warnings
                df = pd.DataFrame(rows)
                # Converter Seq para Int64
                if "Seq" in df.columns:
                    df["Seq"] = pd.to_numeric(df["Seq"], errors='coerce').astype('Int64')
                data_dict[sequencia] = {
                    "dataframe": df,
                    "sheet_name": sequencia
                }
        
        return data_dict if data_dict else None
    
    def clear_all_data(self):
        """
        Limpa todos os dados do banco (Excel e controle)
        
        Returns:
            tuple: (excel_deleted, control_deleted) - número de registros deletados
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Contar registros antes de deletar
        cursor.execute("SELECT COUNT(*) FROM excel_data")
        excel_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM activity_control")
        control_count = cursor.fetchone()[0]
        
        # Deletar todos os dados
        cursor.execute("DELETE FROM excel_data")
        cursor.execute("DELETE FROM activity_control")
        
        # Verificar se foi deletado
        cursor.execute("SELECT COUNT(*) FROM excel_data")
        excel_remaining = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM activity_control")
        control_remaining = cursor.fetchone()[0]
        
        conn.commit()
        conn.close()
        
        return (excel_count, control_count, excel_remaining == 0 and control_remaining == 0)
    
    def export_all_data(self):
        """
        Exporta todos os dados do banco (Excel + controle) para um formato JSON
        
        Returns:
            dict: Dicionário com todos os dados exportados
        """
        import json
        
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Exportar dados do Excel
        cursor.execute("""
            SELECT sequencia, seq, atividade, grupo, localidade, executor, 
                   telefone, inicio, fim, tempo
            FROM excel_data
            ORDER BY sequencia, seq
        """)
        excel_rows = cursor.fetchall()
        
        excel_data = []
        for row in excel_rows:
            excel_data.append({
                "sequencia": row[0],
                "seq": row[1],
                "atividade": row[2],
                "grupo": row[3],
                "localidade": row[4],
                "executor": row[5],
                "telefone": row[6],
                "inicio": row[7],
                "fim": row[8],
                "tempo": row[9]
            })
        
        # Exportar dados de controle
        cursor.execute("""
            SELECT seq, sequencia, status, horario_inicio_real, horario_fim_real,
                   atraso_minutos, observacoes, is_milestone, predecessoras,
                   data_criacao, data_atualizacao
            FROM activity_control
            ORDER BY sequencia, seq
        """)
        control_rows = cursor.fetchall()
        
        control_data = []
        for row in control_rows:
            control_data.append({
                "seq": row[0],
                "sequencia": row[1],
                "status": row[2],
                "horario_inicio_real": row[3],
                "horario_fim_real": row[4],
                "atraso_minutos": row[5],
                "observacoes": row[6],
                "is_milestone": bool(row[7]) if row[7] is not None else False,
                "predecessoras": row[8],
                "data_criacao": row[9],
                "data_atualizacao": row[10]
            })
        
        conn.close()
        
        # Criar estrutura de exportação
        export_data = {
            "version": "1.0",
            "export_date": datetime.now().isoformat(),
            "excel_data": excel_data,
            "control_data": control_data,
            "metadata": {
                "excel_count": len(excel_data),
                "control_count": len(control_data)
            }
        }
        
        return export_data
    
    def import_all_data(self, import_data):
        """
        Importa todos os dados do formato JSON para o banco
        
        Args:
            import_data: Dicionário com dados exportados
            
        Returns:
            tuple: (excel_imported, control_imported, success) - número de registros importados
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # Limpar dados existentes
            cursor.execute("DELETE FROM excel_data")
            cursor.execute("DELETE FROM activity_control")
            
            excel_imported = 0
            control_imported = 0
            
            # Importar dados do Excel
            if "excel_data" in import_data:
                for row in import_data["excel_data"]:
                    try:
                        cursor.execute("""
                            INSERT INTO excel_data
                            (sequencia, seq, atividade, grupo, localidade, executor, 
                             telefone, inicio, fim, tempo)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            row.get("sequencia"),
                            row.get("seq"),
                            row.get("atividade", ""),
                            row.get("grupo", ""),
                            row.get("localidade", ""),
                            row.get("executor", ""),
                            row.get("telefone", ""),
                            row.get("inicio"),
                            row.get("fim"),
                            row.get("tempo", "")
                        ))
                        excel_imported += 1
                    except Exception as e:
                        print(f"Erro ao importar linha Excel: {e}")
                        continue
            
            # Importar dados de controle
            if "control_data" in import_data:
                for row in import_data["control_data"]:
                    try:
                        cursor.execute("""
                            INSERT INTO activity_control
                            (seq, sequencia, status, horario_inicio_real, horario_fim_real,
                             atraso_minutos, observacoes, is_milestone, predecessoras,
                             data_criacao, data_atualizacao)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            row.get("seq"),
                            row.get("sequencia"),
                            row.get("status", "Planejado"),
                            row.get("horario_inicio_real"),
                            row.get("horario_fim_real"),
                            row.get("atraso_minutos", 0),
                            row.get("observacoes"),
                            1 if row.get("is_milestone", False) else 0,
                            row.get("predecessoras"),
                            row.get("data_criacao"),
                            row.get("data_atualizacao")
                        ))
                        control_imported += 1
                    except Exception as e:
                        print(f"Erro ao importar linha controle: {e}")
                        continue
            
            conn.commit()
            conn.close()
            
            return excel_imported, control_imported, True
            
        except Exception as e:
            print(f"Erro ao importar dados: {e}")
            return 0, 0, False