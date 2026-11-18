"""Exporta a escala para Excel no layout da 'Escala do Louvor Geral'."""
import io, datetime as dt
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill, Border, Side
from openpyxl.utils import get_column_letter

WD = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]
MES = ["", "janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto",
       "setembro", "outubro", "novembro", "dezembro"]
ROWS = [("Pregador", "pregador"), ("Ministro", "Ministro"), ("Soprano", "Soprano"), ("Contralto", "Contralto"),
        ("Tenor", "Tenor"), None, ("Guitarra", "Guitarra"), ("Bateria", "Bateria"), ("Baixo", "Baixo"),
        ("Teclado", "Teclado"), ("Violão", "Violão"), None,
        ("Kids (instrumento)", "Kids (instrumento)"), ("Kids (voz)", "Kids (voz)"),
        ("Intercessor", "Intercessor 1"), ("Intercessor", "Intercessor 2")]

def build(title, services, grid, names, igreja="Escala do Louvor", extra_roles=()):
    """services: lista de dict; grid: {(service_id, role): person_id}; names: {id: nome}
    extra_roles: funções criadas pelo responsável (entram depois de Violão, nos cultos que as usam)"""
    rows = list(ROWS)
    used = [r for r in extra_roles if any(r in s["roles"] for s in services)]
    i = rows.index(("Violão", "Violão")) + 1
    rows[i:i] = [(r, r) for r in used]
    block = 4 + len(rows)          # cabeçalho (3 linhas) + linhas + 1 de folga entre blocos
    wb = Workbook()
    ws = wb.active
    ws.title = "escalas"
    thin = Side(style="thin", color="999999")
    ws["A1"] = f"{igreja.upper()} - {title}"
    ws["A1"].font = Font(name="Arial", bold=True, size=14)
    ws.merge_cells("A1:K1")
    r0 = 3
    per_row = 4
    for i, s in enumerate(services):
        band, col = divmod(i, per_row)
        c0 = 1 + col * 3
        r = r0 + band * block
        d = s["date"]
        head = f"{WD[d.weekday()].capitalize()} - {s['turn']}"
        ws.cell(r, c0, head).font = Font(name="Arial", bold=True, color="FFFFFF")
        for cc in range(c0, c0 + 2):
            ws.cell(r, cc).fill = PatternFill("solid", fgColor="2F5597")
        ws.cell(r + 1, c0, f"Tema: {s['tema']}" if s["tema"] else "").font = Font(name="Arial", italic=True)
        ws.cell(r + 2, c0, f"{d.day}/{MES[d.month][:3]}.").font = Font(name="Arial", bold=True)
        ws.cell(r + 2, c0 + 1, s["turn"]).font = Font(name="Arial", bold=True)
        rr = r + 3
        for item in rows:
            if item is None:
                rr += 1
                continue
            label, key = item
            if key == "pregador":
                val = s[key]
            else:
                if key not in s["roles"]:
                    continue
                val = names.get(grid.get((s["id"], key)), "") if grid.get((s["id"], key)) else "— VAGA —"
            ws.cell(rr, c0, label).font = Font(name="Arial", bold=True)
            cell = ws.cell(rr, c0 + 1, val)
            cell.font = Font(name="Arial", color="C00000" if val == "— VAGA —" else "000000")
            for cc in (c0, c0 + 1):
                ws.cell(rr, cc).border = Border(top=thin, bottom=thin, left=thin, right=thin)
            rr += 1
    for col in range(1, per_row * 3 + 1):
        ws.column_dimensions[get_column_letter(col)].width = 15 if col % 3 == 1 else (26 if col % 3 == 2 else 3)

    # carga
    wl = wb.create_sheet("carga por pessoa")
    wl.append(["Nome", "qtd de cultos"])
    cnt = {}
    for (sid, role), pid in grid.items():
        cnt[pid] = cnt.get(pid, 0) + 1
    for pid, n in sorted(cnt.items(), key=lambda kv: (-kv[1], names.get(kv[0], ""))):
        wl.append([names.get(pid, "?"), n])
    for c in wl[1]:
        c.font = Font(name="Arial", bold=True)
    wl.column_dimensions["A"].width = 24
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf
