"""
EA Manager - Painel interativo do buscador Energisa.

Centraliza as operações do projeto: scheduler diário do robô,
disparos manuais (todas / com --force / por geradora), ANEEL,
relatórios XLSX e operacional do banco.
"""

import os
import sys
import sqlite3
import subprocess
import time
from datetime import datetime, date, timedelta

import schedule
from dotenv import load_dotenv
from rich.align import Align
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from database import DatabaseManager
from robo import geradoras_cnpjs

load_dotenv()

DB_PATH = "database/faturas.db"
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))

ASCII_TITULO = r"""
 ____       _             ____                          _              _____                      _
|  _ \ ___ | |__   ___   | __ ) _   _ ___  ___ __ _  __| | ___  _ __  | ____|_ __   ___ _ __ __ _(_)___  __ _
| |_) / _ \| '_ \ / _ \  |  _ \| | | / __|/ __/ _` |/ _` |/ _ \| '__| |  _| | '_ \ / _ \ '__/ _` | / __|/ _` |
|  _ < (_) | |_) | (_) | | |_) | |_| \__ \ (_| (_| | (_| | (_) | |    | |___| | | |  __/ | | (_| | \__ \ (_| |
|_| \_\___/|_.__/ \___/  |____/ \__,_|___/\___\__,_|\__,_|\___/|_|    |_____|_| |_|\___|_|  \__, |_|___/\__,_|
                                                                                            |___/
"""

# Mapa nome → CNPJ, reaproveitando a lista oficial em geradoras.py
GERADORAS_NOMES = {
    "29.698.168/0001-02": "ENERGIA A",
    "58.179.054/0001-46": "SULINA",
    "47.278.309/0001-01": "LUNA",
    "48.174.641/0001-99": "LB",
    "59.981.267/0001-50": "LUZ DIVINA",
    "52.028.408/0001-75": "G114",
    "250.262.911-04": "SLLG",
    "61.195.685/0001-63": "EVIC",
}


def limpar_tela() -> None:
    os.system("cls" if os.name == "nt" else "clear")


# ==================== STATS ====================

def obter_stats() -> dict:
    """Coleta números para o cabeçalho do painel. Tolerante a banco vazio/ausente."""
    stats = {
        "total": 0,
        "a_verificar": 0,
        "sucesso": 0,
        "erro": 0,
        "processadas_hoje": 0,
        "ultima_execucao": None,
        "geradoras": len(geradoras_cnpjs),
    }
    if not os.path.exists(DB_PATH):
        return stats
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("""
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN status='a_verificar' THEN 1 ELSE 0 END) AS a_verificar,
                SUM(CASE WHEN status='sucesso'     THEN 1 ELSE 0 END) AS sucesso,
                SUM(CASE WHEN status='erro'        THEN 1 ELSE 0 END) AS erro,
                MAX(data_processamento)            AS ultima
            FROM faturas
        """)
        row = cur.fetchone()
        if row:
            stats["total"] = row["total"] or 0
            stats["a_verificar"] = row["a_verificar"] or 0
            stats["sucesso"] = row["sucesso"] or 0
            stats["erro"] = row["erro"] or 0
            stats["ultima_execucao"] = row["ultima"]

        hoje = date.today().isoformat()
        cur.execute(
            "SELECT COUNT(*) AS qtd FROM faturas "
            "WHERE substr(data_processamento, 1, 10) = ?",
            (hoje,),
        )
        stats["processadas_hoje"] = cur.fetchone()["qtd"] or 0
        conn.close()
    except sqlite3.OperationalError:
        # Banco existe mas tabela não criada ainda — devolve defaults.
        pass
    return stats


# ==================== RENDER ====================

OPCOES_MENU = [
    ("1",  "Ativar servidor (scheduler em foreground)"),
    ("2",  "Rodar robô agora (todas as geradoras)"),
    ("3",  "Rodar robô agora com --force (reprocessar erros)"),
    ("4",  "Rodar robô para uma geradora específica"),
    ("5",  "Coletar códigos ANEEL (robo_aneel.py)"),
    ("6",  "Testar webhook ANEEL"),
    ("7",  "Status do banco (por status e por geradora)"),
    ("8",  "Listar execuções do dia"),
    ("9",  "Listar geradoras cadastradas"),
    ("10", "Gerar relatório XLSX de hoje"),
    ("11", "Gerar relatório XLSX por intervalo"),
    ("12", "Resetar faturas com erro"),
    ("0",  "Sair"),
]


def renderizar_painel(console: Console) -> None:
    limpar_tela()
    stats = obter_stats()

    titulo = Text(ASCII_TITULO, style="bold cyan", justify="left")
    console.print(titulo)

    hora_scheduler = os.environ.get("SCHEDULER_HORA", "08:00")
    subtitulo = Text.assemble(
        ("Painel Interativo · ", "bold"),
        ("ENERGISA", "bold yellow"),
        (" · Buscador de Faturas", "bold"),
        ("\n", ""),
        (f"⏰ scheduler diário às {hora_scheduler}", "dim"),
    )
    console.print(Align.center(subtitulo))

    ultima = stats["ultima_execucao"] or "—"
    if ultima != "—":
        ultima = str(ultima)[:19]  # corta microssegundos
    linha_stats = Text.assemble(
        (f"📡 {stats['geradoras']} geradoras", "bold green"),
        ("   ·   ", "dim"),
        (f"📥 {stats['a_verificar']} a verificar", "bold yellow"),
        ("   ·   ", "dim"),
        (f"✅ {stats['processadas_hoje']} processadas hoje", "bold cyan"),
        ("   ·   ", "dim"),
        (f"❌ {stats['erro']} com erro", "bold red"),
        ("   ·   ", "dim"),
        (f"🕐 última: {ultima}", "dim"),
    )
    console.print(Align.center(linha_stats))
    console.print()

    tabela = Table.grid(padding=(0, 4))
    tabela.add_column(justify="right", style="bold cyan", min_width=4)
    tabela.add_column(style="white")
    for num, descricao in OPCOES_MENU:
        if num == "1":
            tabela.add_row(num, Text(descricao, style="bold green"))
        elif num == "0":
            tabela.add_row(num, Text(descricao, style="bold red"))
        else:
            tabela.add_row(num, descricao)

    console.print(
        Panel(
            tabela,
            title="[bold]O que você quer fazer?[/bold]",
            border_style="cyan",
            padding=(1, 2),
        )
    )


# ==================== AÇÕES: SCHEDULER ====================

def _executar_robo(force: bool = False) -> None:
    """Roda robo.py em subprocess; logs vão direto para o terminal do painel."""
    args = [sys.executable, "robo.py"]
    if force:
        args.append("--force")
    subprocess.run(args, cwd=PROJECT_DIR)


def _executar_geradora(cnpj: str) -> None:
    """Roda processar_geradora_especifica para um CNPJ em subprocess."""
    codigo = (
        "import sys; "
        "from robo import processar_geradora_especifica; "
        "processar_geradora_especifica(sys.argv[1])"
    )
    subprocess.run(
        [sys.executable, "-c", codigo, cnpj],
        cwd=PROJECT_DIR,
    )


def acao_ativar_scheduler(console: Console) -> None:
    hora = os.environ.get("SCHEDULER_HORA", "08:00").strip()
    try:
        datetime.strptime(hora, "%H:%M")
    except ValueError:
        console.print(
            f"[red]❌ SCHEDULER_HORA inválido no .env: {hora!r} (formato esperado HH:MM)[/red]"
        )
        return

    schedule.clear()
    schedule.every().day.at(hora).do(_executar_robo)

    console.print()
    console.print(
        Panel(
            Text.assemble(
                ("Scheduler ativo em foreground.\n\n", "bold green"),
                (f"⏰ Horário programado: ", "white"),
                (f"todo dia às {hora}\n", "bold yellow"),
                ("📋 Ação: ", "white"),
                ("rodar robo.py (todas as geradoras)\n\n", "bold"),
                ("Pressione ", "dim"),
                ("Ctrl+C", "bold yellow"),
                (" para parar e voltar ao menu.", "dim"),
            ),
            title="🟢 SERVIDOR ATIVO",
            border_style="green",
        )
    )

    try:
        while True:
            proxima = schedule.next_run()
            agora = datetime.now()
            if proxima:
                falta = proxima - agora
                # Mostrar tempo restante na mesma linha (carriage return)
                horas, resto = divmod(int(falta.total_seconds()), 3600)
                minutos, segundos = divmod(resto, 60)
                sys.stdout.write(
                    f"\r⏳ Próxima execução: {proxima.strftime('%d/%m/%Y %H:%M:%S')}  "
                    f"(faltam {horas:02d}h{minutos:02d}m{segundos:02d}s)   "
                )
                sys.stdout.flush()
            schedule.run_pending()
            time.sleep(1)
    except KeyboardInterrupt:
        schedule.clear()
        print()
        console.print("\n[yellow]⏹  Scheduler interrompido. Voltando ao menu...[/yellow]")


# ==================== AÇÕES: ROBÔ ====================

def acao_rodar_robo(console: Console) -> None:
    console.print("\n[bold cyan]🚀 Iniciando robo.py (todas as geradoras)...[/bold cyan]\n")
    _executar_robo(force=False)


def acao_rodar_robo_force(console: Console) -> None:
    console.print(
        "\n[bold yellow]🚀 Iniciando robo.py --force (reprocessando erros)...[/bold yellow]\n"
    )
    _executar_robo(force=True)


def acao_rodar_geradora_especifica(console: Console) -> None:
    tabela = Table(title="Geradoras cadastradas", border_style="cyan")
    tabela.add_column("#", style="bold cyan", justify="right")
    tabela.add_column("Nome", style="bold")
    tabela.add_column("CNPJ / CPF", style="white")

    for i, cnpj in enumerate(geradoras_cnpjs, 1):
        tabela.add_row(str(i), GERADORAS_NOMES.get(cnpj, "?"), cnpj)
    console.print(tabela)

    escolha = input("\nDigite o número da geradora (ou ENTER para cancelar): ").strip()
    if not escolha:
        return
    try:
        idx = int(escolha) - 1
        if idx < 0 or idx >= len(geradoras_cnpjs):
            console.print("[red]Número fora do intervalo.[/red]")
            return
    except ValueError:
        console.print("[red]Entrada inválida.[/red]")
        return

    cnpj = geradoras_cnpjs[idx]
    nome = GERADORAS_NOMES.get(cnpj, "?")
    console.print(
        f"\n[bold cyan]🚀 Iniciando processamento da geradora {nome} ({cnpj})...[/bold cyan]\n"
    )
    _executar_geradora(cnpj)


# ==================== AÇÕES: ANEEL ====================

def acao_coletar_aneel(console: Console) -> None:
    if not os.path.exists(os.path.join(PROJECT_DIR, "robo_aneel.py")):
        console.print("[red]❌ robo_aneel.py não encontrado.[/red]")
        return
    console.print("\n[bold cyan]📡 Iniciando coleta de códigos ANEEL...[/bold cyan]\n")
    subprocess.run([sys.executable, "robo_aneel.py"], cwd=PROJECT_DIR)


def acao_testar_webhook_aneel(console: Console) -> None:
    if not os.path.exists(os.path.join(PROJECT_DIR, "teste_webhook_aneel.py")):
        console.print("[red]❌ teste_webhook_aneel.py não encontrado.[/red]")
        return
    console.print("\n[bold cyan]🧪 Testando webhook ANEEL...[/bold cyan]\n")
    subprocess.run([sys.executable, "teste_webhook_aneel.py"], cwd=PROJECT_DIR)


# ==================== AÇÕES: OPERACIONAL ====================

def acao_status_banco(console: Console) -> None:
    stats = obter_stats()

    geral = Table(title="📊 Visão geral", border_style="cyan")
    geral.add_column("Métrica", style="bold")
    geral.add_column("Valor", justify="right")
    geral.add_row("Total de faturas", str(stats["total"]))
    geral.add_row("A verificar", f"[yellow]{stats['a_verificar']}[/yellow]")
    geral.add_row("Sucesso", f"[green]{stats['sucesso']}[/green]")
    geral.add_row("Erro", f"[red]{stats['erro']}[/red]")
    geral.add_row("Processadas hoje", f"[cyan]{stats['processadas_hoje']}[/cyan]")
    ultima = stats["ultima_execucao"] or "—"
    if ultima != "—":
        ultima = str(ultima)[:19]
    geral.add_row("Última execução", ultima)
    console.print(geral)

    db = DatabaseManager()
    por_geradora = Table(title="📋 Por geradora", border_style="cyan")
    por_geradora.add_column("Nome", style="bold")
    por_geradora.add_column("CNPJ")
    por_geradora.add_column("Total", justify="right")
    por_geradora.add_column("A verificar", justify="right", style="yellow")
    por_geradora.add_column("Sucesso", justify="right", style="green")
    por_geradora.add_column("Erro", justify="right", style="red")
    for cnpj in geradoras_cnpjs:
        s = db.obter_estatisticas_geradora(cnpj)
        por_geradora.add_row(
            GERADORAS_NOMES.get(cnpj, "?"),
            cnpj,
            str(s.get("total") or 0),
            str(s.get("a_verificar") or 0),
            str(s.get("sucesso") or 0),
            str(s.get("erro") or 0),
        )
    console.print(por_geradora)


def acao_execucoes_dia(console: Console) -> None:
    db = DatabaseManager()
    execucoes = db.obter_execucoes_do_dia()
    if not execucoes:
        console.print(
            f"\n[yellow]Nenhuma execução registrada hoje ({date.today().isoformat()}).[/yellow]"
        )
        return

    tabela = Table(
        title=f"📅 Execuções de {date.today().strftime('%d/%m/%Y')}",
        border_style="cyan",
    )
    tabela.add_column("UC", style="bold")
    tabela.add_column("Geradora")
    tabela.add_column("Status")
    tabela.add_column("Total", justify="right")
    tabela.add_column("✅", justify="right", style="green")
    tabela.add_column("❌", justify="right", style="red")
    tabela.add_column("⏭", justify="right", style="yellow")
    tabela.add_column("Início")
    tabela.add_column("Fim")

    cores_status = {"completo": "green", "parcial": "yellow", "falha": "red"}
    for e in execucoes:
        cor = cores_status.get(e["status_execucao"], "white")
        tabela.add_row(
            e["nova_uc"],
            GERADORAS_NOMES.get(e["cnpj_geradora"], e["cnpj_geradora"]),
            f"[{cor}]{e['status_execucao']}[/{cor}]",
            str(e["total_faturas"]),
            str(e["faturas_sucesso"]),
            str(e["faturas_erro"]),
            str(e["faturas_puladas"]),
            str(e["data_hora_inicio"])[:19],
            str(e["data_hora_fim"] or "")[:19],
        )
    console.print(tabela)


def acao_listar_geradoras(console: Console) -> None:
    tabela = Table(title="🏭 Geradoras cadastradas", border_style="cyan")
    tabela.add_column("#", style="bold cyan", justify="right")
    tabela.add_column("Nome", style="bold")
    tabela.add_column("CNPJ / CPF")
    for i, cnpj in enumerate(geradoras_cnpjs, 1):
        tabela.add_row(str(i), GERADORAS_NOMES.get(cnpj, "?"), cnpj)
    console.print(tabela)


def acao_resetar_erros(console: Console) -> None:
    confirma = input(
        "Resetar TODAS as faturas com status 'erro' para 'a_verificar'? (s/n): "
    ).strip().lower()
    if confirma != "s":
        console.print("[yellow]Operação cancelada.[/yellow]")
        return
    db = DatabaseManager()
    qtd = db.resetar_status_erro()
    console.print(f"[green]✅ {qtd} faturas resetadas.[/green]")


# ==================== AÇÕES: RELATÓRIOS XLSX ====================
# Funções preservadas da versão anterior do ea_manager.py — mesma lógica,
# apenas isoladas para uso pelo novo menu.

def gerar_relatorio_unico(data_execucao: str):
    """Gera relatório XLSX para uma data específica (YYYY-MM-DD)."""
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    except ImportError:
        print("❌ Biblioteca openpyxl não encontrada!")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "openpyxl", "-q"])
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, nova_uc, mes_referencia, cnpj_geradora,
               status, tipo_operacao, valor, data_vencimento,
               situacao_pagamento, data_processamento, tentativas,
               mensagem_erro
        FROM faturas
        WHERE DATE(data_processamento) = ?
        ORDER BY cnpj_geradora, nova_uc, mes_referencia
    """, (data_execucao,))
    faturas = [dict(row) for row in cursor.fetchall()]

    cursor.execute("""
        SELECT cnpj_geradora, nova_uc, total_faturas,
               faturas_sucesso, faturas_erro, faturas_puladas,
               status_execucao, data_hora_inicio, data_hora_fim
        FROM execucoes_diarias
        WHERE data_execucao = ?
        ORDER BY cnpj_geradora, nova_uc
    """, (data_execucao,))
    execucoes = [dict(row) for row in cursor.fetchall()]
    conn.close()

    if not faturas and not execucoes:
        return None

    wb = Workbook()
    header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF", size=12)
    border = Border(
        left=Side(style="thin"), right=Side(style="thin"),
        top=Side(style="thin"), bottom=Side(style="thin"),
    )

    # ABA 1: RESUMO
    ws_resumo = wb.active
    ws_resumo.title = "Resumo"
    ws_resumo["A1"] = (
        f"RELATÓRIO DE EXECUÇÃO - "
        f"{datetime.strptime(data_execucao, '%Y-%m-%d').strftime('%d/%m/%Y')}"
    )
    ws_resumo["A1"].font = Font(bold=True, size=14)
    ws_resumo.merge_cells("A1:F1")

    total_faturas = len(faturas)
    total_sucesso = sum(1 for f in faturas if f["status"] == "sucesso")
    total_erro = sum(1 for f in faturas if f["status"] == "erro")

    ws_resumo["A3"] = "ESTATÍSTICAS GERAIS"
    ws_resumo["A3"].font = Font(bold=True, size=12)
    ws_resumo["A4"] = "Total de Faturas Processadas:"
    ws_resumo["B4"] = total_faturas
    ws_resumo["A5"] = "Sucesso:"
    ws_resumo["B5"] = total_sucesso
    ws_resumo["A6"] = "Erro:"
    ws_resumo["B6"] = total_erro
    ws_resumo["A7"] = "Taxa de Sucesso:"
    ws_resumo["B7"] = (
        f"{(total_sucesso / total_faturas * 100):.1f}%" if total_faturas > 0 else "0%"
    )

    ws_resumo["A9"] = "POR TIPO DE OPERAÇÃO"
    ws_resumo["A9"].font = Font(bold=True, size=12)
    tipos_operacao = {}
    for f in faturas:
        tipo = f["tipo_operacao"] or "Não registrado"
        tipos_operacao[tipo] = tipos_operacao.get(tipo, 0) + 1
    linha = 10
    for tipo, count in sorted(tipos_operacao.items()):
        ws_resumo[f"A{linha}"] = f"{tipo}:"
        ws_resumo[f"B{linha}"] = count
        linha += 1

    ws_resumo[f"A{linha + 1}"] = "POR GERADORA"
    ws_resumo[f"A{linha + 1}"].font = Font(bold=True, size=12)
    geradoras = {}
    for f in faturas:
        cnpj = f["cnpj_geradora"]
        if cnpj not in geradoras:
            geradoras[cnpj] = {"total": 0, "sucesso": 0, "erro": 0}
        geradoras[cnpj]["total"] += 1
        if f["status"] == "sucesso":
            geradoras[cnpj]["sucesso"] += 1
        else:
            geradoras[cnpj]["erro"] += 1
    linha += 3
    for col, valor in zip("ABCDE", ["CNPJ", "Total", "Sucesso", "Erro", "Taxa"]):
        ws_resumo[f"{col}{linha}"] = valor
        ws_resumo[f"{col}{linha}"].fill = header_fill
        ws_resumo[f"{col}{linha}"].font = header_font
        ws_resumo[f"{col}{linha}"].border = border
    linha += 1
    for cnpj, s in sorted(geradoras.items()):
        ws_resumo[f"A{linha}"] = cnpj
        ws_resumo[f"B{linha}"] = s["total"]
        ws_resumo[f"C{linha}"] = s["sucesso"]
        ws_resumo[f"D{linha}"] = s["erro"]
        ws_resumo[f"E{linha}"] = f"{(s['sucesso'] / s['total'] * 100):.1f}%"
        linha += 1
    for col, w in zip("ABCDE", [30, 15, 15, 15, 15]):
        ws_resumo.column_dimensions[col].width = w

    # ABA 2: FATURAS
    ws_faturas = wb.create_sheet("Faturas Processadas")
    headers = [
        "ID", "UC", "Mês Ref", "CNPJ", "Status", "Tipo Operação",
        "Valor", "Vencimento", "Situação Pgto", "Data Processamento",
        "Tentativas", "Mensagem Erro",
    ]
    for col_num, header in enumerate(headers, 1):
        cell = ws_faturas.cell(row=1, column=col_num, value=header)
        cell.fill = header_fill
        cell.font = header_font
        cell.border = border
        cell.alignment = Alignment(horizontal="center", vertical="center")
    for row_num, fatura in enumerate(faturas, 2):
        ws_faturas.cell(row=row_num, column=1, value=fatura["id"])
        ws_faturas.cell(row=row_num, column=2, value=fatura["nova_uc"])
        ws_faturas.cell(row=row_num, column=3, value=fatura["mes_referencia"])
        ws_faturas.cell(row=row_num, column=4, value=fatura["cnpj_geradora"])
        ws_faturas.cell(row=row_num, column=5, value=fatura["status"])
        ws_faturas.cell(row=row_num, column=6, value=fatura["tipo_operacao"] or "N/A")
        ws_faturas.cell(
            row=row_num, column=7,
            value=f"R$ {fatura['valor']}" if fatura["valor"] else "N/A",
        )
        ws_faturas.cell(row=row_num, column=8, value=fatura["data_vencimento"] or "N/A")
        ws_faturas.cell(row=row_num, column=9, value=fatura["situacao_pagamento"] or "N/A")
        ws_faturas.cell(row=row_num, column=10, value=fatura["data_processamento"])
        ws_faturas.cell(row=row_num, column=11, value=fatura["tentativas"])
        ws_faturas.cell(row=row_num, column=12, value=fatura["mensagem_erro"] or "")
        fill = (
            PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")
            if fatura["status"] == "sucesso"
            else PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")
        )
        for col_num in range(1, 13):
            ws_faturas.cell(row=row_num, column=col_num).fill = fill
            ws_faturas.cell(row=row_num, column=col_num).border = border
    for col, w in zip("ABCDEFGHIJKL", [10, 15, 12, 20, 12, 18, 15, 15, 15, 20, 12, 40]):
        ws_faturas.column_dimensions[col].width = w

    # ABA 3: EXECUÇÕES
    ws_exec = wb.create_sheet("Execuções por UC")
    headers_exec = [
        "CNPJ", "UC", "Total", "Sucesso", "Erro",
        "Puladas", "Status", "Hora Início", "Hora Fim", "Duração",
    ]
    for col_num, header in enumerate(headers_exec, 1):
        cell = ws_exec.cell(row=1, column=col_num, value=header)
        cell.fill = header_fill
        cell.font = header_font
        cell.border = border
        cell.alignment = Alignment(horizontal="center", vertical="center")
    for row_num, ex in enumerate(execucoes, 2):
        ws_exec.cell(row=row_num, column=1, value=ex["cnpj_geradora"])
        ws_exec.cell(row=row_num, column=2, value=ex["nova_uc"])
        ws_exec.cell(row=row_num, column=3, value=ex["total_faturas"])
        ws_exec.cell(row=row_num, column=4, value=ex["faturas_sucesso"])
        ws_exec.cell(row=row_num, column=5, value=ex["faturas_erro"])
        ws_exec.cell(row=row_num, column=6, value=ex["faturas_puladas"])
        ws_exec.cell(row=row_num, column=7, value=ex["status_execucao"])
        ws_exec.cell(row=row_num, column=8, value=ex["data_hora_inicio"])
        ws_exec.cell(row=row_num, column=9, value=ex["data_hora_fim"] or "N/A")
        if ex["data_hora_fim"]:
            try:
                inicio = datetime.strptime(ex["data_hora_inicio"], "%Y-%m-%d %H:%M:%S.%f")
                fim = datetime.strptime(ex["data_hora_fim"], "%Y-%m-%d %H:%M:%S.%f")
                ws_exec.cell(row=row_num, column=10, value=str(fim - inicio).split(".")[0])
            except Exception:
                ws_exec.cell(row=row_num, column=10, value="N/A")
        else:
            ws_exec.cell(row=row_num, column=10, value="N/A")
        if ex["status_execucao"] == "completo":
            fill = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")
        elif ex["status_execucao"] == "parcial":
            fill = PatternFill(start_color="FFEB9C", end_color="FFEB9C", fill_type="solid")
        else:
            fill = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")
        for col_num in range(1, 11):
            ws_exec.cell(row=row_num, column=col_num).fill = fill
            ws_exec.cell(row=row_num, column=col_num).border = border
    for col, w in zip("ABCDEFGHIJ", [20, 15, 12, 12, 12, 12, 15, 20, 20, 15]):
        ws_exec.column_dimensions[col].width = w

    data_formatada = datetime.strptime(data_execucao, "%Y-%m-%d").strftime("%d%m%Y")
    nome_arquivo = f"relatorio_faturas_{data_formatada}.xlsx"
    wb.save(nome_arquivo)

    print(f"\n✅ Relatório gerado: {nome_arquivo}")
    print(f"📊 Total: {total_faturas} | ✅ {total_sucesso} | ❌ {total_erro}")
    if total_faturas > 0:
        print(f"📈 Taxa de sucesso: {(total_sucesso / total_faturas * 100):.1f}%")
    return nome_arquivo


def acao_relatorio_hoje(console: Console) -> None:
    data_hoje = date.today().strftime("%Y-%m-%d")
    console.print(f"\n[bold cyan]📅 Gerando relatório de hoje ({data_hoje})...[/bold cyan]")
    arquivo = gerar_relatorio_unico(data_hoje)
    if not arquivo:
        console.print("[yellow]⚠️ Nenhum dado encontrado para hoje.[/yellow]")
        return
    if input("\nDeseja abrir o arquivo agora? (s/n): ").strip().lower() == "s":
        try:
            os.startfile(arquivo)
        except Exception:
            console.print("[yellow]⚠️ Não foi possível abrir automaticamente.[/yellow]")


def acao_relatorio_intervalo(console: Console) -> None:
    console.print("\n[bold]Relatório por intervalo de datas[/bold]  (formato DD/MM/AAAA)")

    while True:
        ini = input("Data inicial: ").strip()
        try:
            data_inicial = datetime.strptime(ini, "%d/%m/%Y").date()
            break
        except ValueError:
            console.print("[red]❌ Formato inválido. Use DD/MM/AAAA.[/red]")

    while True:
        fim = input("Data final: ").strip()
        try:
            data_final = datetime.strptime(fim, "%d/%m/%Y").date()
            if data_final < data_inicial:
                console.print("[red]❌ Data final deve ser ≥ data inicial.[/red]")
                continue
            break
        except ValueError:
            console.print("[red]❌ Formato inválido. Use DD/MM/AAAA.[/red]")

    # Gera 1 arquivo por dia do intervalo (reuso de gerar_relatorio_unico)
    arquivos = []
    atual = data_inicial
    while atual <= data_final:
        nome = gerar_relatorio_unico(atual.strftime("%Y-%m-%d"))
        if nome:
            arquivos.append(nome)
        atual += timedelta(days=1)

    if not arquivos:
        console.print("[yellow]⚠️ Nenhum dado encontrado no intervalo.[/yellow]")
        return
    console.print(f"\n[green]✅ {len(arquivos)} arquivo(s) gerado(s):[/green]")
    for a in arquivos:
        console.print(f"   • {a}")


# ==================== MAIN LOOP ====================

ACOES = {
    "1":  acao_ativar_scheduler,
    "2":  acao_rodar_robo,
    "3":  acao_rodar_robo_force,
    "4":  acao_rodar_geradora_especifica,
    "5":  acao_coletar_aneel,
    "6":  acao_testar_webhook_aneel,
    "7":  acao_status_banco,
    "8":  acao_execucoes_dia,
    "9":  acao_listar_geradoras,
    "10": acao_relatorio_hoje,
    "11": acao_relatorio_intervalo,
    "12": acao_resetar_erros,
}


def main() -> None:
    console = Console()
    while True:
        renderizar_painel(console)
        try:
            opcao = input("\nEscolha uma opção: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if opcao == "0":
            console.print("\n[bold]👋 Até logo![/bold]")
            break

        acao = ACOES.get(opcao)
        if acao is None:
            console.print("\n[red]❌ Opção inválida.[/red]")
        else:
            try:
                acao(console)
            except KeyboardInterrupt:
                console.print("\n[yellow]⏹  Ação interrompida.[/yellow]")
            except Exception as e:
                console.print(f"\n[red]❌ Erro ao executar a ação: {e}[/red]")

        input("\nPressione ENTER para voltar ao menu...")


if __name__ == "__main__":
    main()
