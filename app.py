"""Sistema de escalas do louvor - aplicação web (Flask)."""
import calendar, collections, datetime as dt, os, secrets
from functools import wraps
from flask import (Flask, abort, flash, g, redirect, render_template, request,
                   send_file, send_from_directory, session, url_for)
import db, exporter, notify, scheduler, seed
import rules as custom_rules

app = Flask(__name__)
SECRET_FILE = os.path.join(db.BASE, "data", "secret.key")
os.makedirs(os.path.dirname(SECRET_FILE), exist_ok=True)
if not os.path.exists(SECRET_FILE):
    open(SECRET_FILE, "w").write(secrets.token_hex(32))
app.secret_key = open(SECRET_FILE).read().strip()


@app.url_defaults
def static_version(endpoint, values):
    """Acrescenta ?v=<data do arquivo> aos arquivos estáticos (CSS, JS, ícones).
    O nginx manda o navegador guardar esses arquivos por 7 dias; com a versão no endereço,
    qualquer mudança publicada é baixada na hora, sem precisar limpar o cache."""
    if endpoint == "static" and "filename" in values and "v" not in values:
        try:
            values["v"] = int(os.stat(os.path.join(app.static_folder, values["filename"])).st_mtime)
        except OSError:
            pass
ADMIN_PASSWORD = os.environ.get("ESCALAS_ADMIN_PASSWORD", "louvor123")

WD = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]
WDS = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
MES = ["", "janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto",
       "setembro", "outubro", "novembro", "dezembro"]


db.init().close()


def conn():
    if "db" not in g:
        g.db = db.connect()
    return g.db


@app.teardown_appcontext
def close(_):
    c = g.pop("db", None)
    if c:
        c.close()


@app.template_filter("dmy")
def dmy(d):
    return f"{d.day:02d}/{d.month:02d}"


@app.context_processor
def ctx():
    return dict(WD=WD, WDS=WDS, MES=MES, BAND=db.all_roles(conn()), AUTO=db.AUTO_ROLES, ROLE_TYPES=db.ROLE_TYPES,
                ROLES_ALL=db.all_slots(conn()),
                igreja=db.get_settings(conn())["igreja"])


def admin_required(f):
    @wraps(f)
    def w(*a, **k):
        if not session.get("admin"):
            return redirect(url_for("login", next=request.path))
        return f(*a, **k)
    return w


def lan_ip():
    """IP deste computador na rede local (ex.: 192.168.0.6). Não envia nada pela rede:
    o connect() de UDP só escolhe a interface de saída."""
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
        s.close()
        return ip if not ip.startswith("127.") else None
    except OSError:
        return None


def base_url():
    """Endereço usado nos links enviados (WhatsApp). Prioridade: ESCALAS_BASE_URL; senão o endereço
    em que o painel foi aberto — trocando 'localhost' pelo IP da rede, porque 'localhost' não funciona
    no celular e o WhatsApp não o transforma em link clicável."""
    env = os.environ.get("ESCALAS_BASE_URL")
    if env:
        return env.rstrip("/")
    host, _, port = request.host.partition(":")
    if host in ("localhost", "127.0.0.1", "::1", "[::1]"):
        ip = lan_ip()
        if ip:
            return f"{request.scheme}://{ip}{':' + port if port else ''}"
    return request.host_url.rstrip("/")


def month_title(ym):
    y, m = map(int, ym.split("-"))
    return f"{MES[m].capitalize()}/{y}"


MOTIVO_MAX = 1000


def parse_deadline(text, ym):
    """Prazo de resposta -> date (ou None se vazio/irreconhecível).
    Aceita 'AAAA-MM-DD' (campo de data), 'DD/MM/AAAA', 'DD/MM/AA' e 'DD/MM'
    (sem ano: o prazo é antes do mês da escala, ex. 20/12 para janeiro = dezembro do ano anterior)."""
    t = (text or "").strip()
    if not t:
        return None
    try:
        if "-" in t:
            return dt.date.fromisoformat(t)
        parts = [int(x) for x in t.split("/")]
        if len(parts) == 3:
            d, mo, y = parts
            return dt.date(y + 2000 if y < 100 else y, mo, d)
        if len(parts) == 2:
            d, mo = parts
            y, m = map(int, ym.split("-"))
            return dt.date(y - 1 if mo > m else y, mo, d)
    except ValueError:
        return None
    return None


def deadline_info(m):
    """{'date': date|None, 'label': texto para exibir, 'closed': True se o prazo já passou}.
    O prazo vale até o fim do dia informado."""
    d = parse_deadline(m["deadline"], m["ym"])
    label = d.strftime("%d/%m/%Y") if d else (m["deadline"] or "")
    return {"date": d, "label": label, "closed": bool(d and dt.date.today() > d), "iso": d.isoformat() if d else ""}


app.jinja_env.globals["deadline_info"] = deadline_info


# ---------------------------------------------------------------- dados
def load_people(c):
    roles = {}
    for r in c.execute("SELECT * FROM person_role"):
        roles.setdefault(r["person_id"], set()).add(r["role"])
    out = []
    for p in c.execute("SELECT * FROM person ORDER BY name"):
        d = dict(p)
        d["roles"] = roles.get(p["id"], set())
        d["blocked_wd"] = {int(x) for x in p["blocked_wd"].split(",") if x != ""}
        out.append(d)
    return out


def load_services(c, mid):
    out = []
    qtd = db.role_qtd(c)
    for s in c.execute("SELECT * FROM service WHERE month_id=? ORDER BY date, CASE turn WHEN 'Manhã' THEN 0 ELSE 1 END, id", (mid,)):
        d = dict(s)
        d["date"] = dt.date.fromisoformat(s["date"])
        auto = db.auto_roles_for(d["date"])   # Louvor Kids (domingo) e Intercessão: automáticos
        d["base_roles"] = [r for r in s["roles"].split(",") if r and r not in db.AUTO_ROLES]   # marcadas no culto
        # vagas: função com 2+ pessoas por culto vira "Função (1)", "Função (2)"…
        d["roles"] = [x for r in d["base_roles"] for x in db.slots(r, qtd.get(r, 1))] + auto
        out.append(d)
    return out


def load_unav(c):
    return {(r["person_id"], dt.date.fromisoformat(r["date"]), r["turn"])
            for r in c.execute("SELECT * FROM unavail")}


def prev_ym(ym):
    y, m = map(int, ym.split("-"))
    return f"{y - 1}-12" if m == 1 else f"{y}-{m - 1:02d}"


def prev_loads(c, ym):
    nl = tuple(db.NO_LOAD_ROLES)   # Intercessão não conta como culto tocado
    rows = c.execute(f"""SELECT a.person_id, COUNT(DISTINCT a.service_id) n FROM assignment a
        JOIN service s ON s.id=a.service_id JOIN month m ON m.id=s.month_id
        WHERE m.ym=? AND a.role NOT IN ({",".join("?" * len(nl))}) GROUP BY a.person_id""", (prev_ym(ym), *nl))
    return {r["person_id"]: r["n"] for r in rows}


def get_month(c, mid):
    m = c.execute("SELECT * FROM month WHERE id=?", (mid,)).fetchone()
    if not m:
        abort(404)
    return m


def grid_of(c, mid):
    return {(r["service_id"], r["role"]): r["person_id"] for r in c.execute(
        "SELECT a.* FROM assignment a JOIN service s ON s.id=a.service_id WHERE s.month_id=?", (mid,))}


def conflicts(c, mid):
    """Confere a escala atual (inclusive ajustes manuais) contra as regras."""
    people = {p["id"]: p for p in load_people(c)}
    S = load_services(c, mid)
    grid = grid_of(c, mid)
    cfg = db.get_settings(c)
    unav = load_unav(c)
    out = []
    per_service = {}
    for (sid, role), pid in grid.items():
        per_service.setdefault(sid, {}).setdefault(pid, []).append(role)
    byid = {s["id"]: s for s in S}
    kinds = db.role_kinds(c)
    # trocas feitas pelo ministro (link pessoal): pode ser qualquer pessoa, sem as regras de função
    by_minister = {(t["service_id"], t["role"], t["new_id"]) for t in c.execute("SELECT * FROM troca")}
    for sid, pp in per_service.items():
        s = byid[sid]
        for pid, roles in pp.items():
            p = people[pid]
            tag = f"{dmy(s['date'])} {s['turn']}"
            prob = db.combo_problem(roles, kinds)
            if prob:
                out.append(f"{p['name']} em {tag}: {prob}")
            if not scheduler.eligible(p, s, unav):
                out.append(f"{p['name']} está escalado(a) em {tag}, mas tem restrição/indisponibilidade nesse dia")
            for r in roles:
                if not db.can_take(p["roles"], r) and (sid, r, pid) not in by_minister:
                    out.append(f"{p['name']} está como {r} em {tag}, mas não tem essa função")
    # o que conta como participação (banda, Kids, som/mídia/luz; Intercessão não conta)
    playing = {sid: {pid for pid, rs in pp.items() if any(r not in db.NO_LOAD_ROLES for r in rs)}
               for sid, pp in per_service.items()}
    # regra do domingo: só quem toca, canta ou faz o Kids
    music = lambda r: r in (db.KIDS_INST, db.KIDS_VOZ) or kinds.get(db.base_of(r)) in ("ministro", "voz", "instrumento")
    musical = {sid: {pid for pid, rs in pp.items() if any(music(r) for r in rs)} for sid, pp in per_service.items()}
    if True:  # regra fixa do domingo (sempre ativa; ver scheduler.solve)
        for d in sorted({s["date"] for s in S if s["date"].weekday() == 6}):
            ms = [s for s in S if s["date"] == d and s["turn"] == "Manhã"]
            ns = [s for s in S if s["date"] == d and s["turn"] == "Noite"]
            if ms and ns and not (ms[0]["exempt"] or ns[0]["exempt"]):
                for pid in musical.get(ms[0]["id"], set()) & musical.get(ns[0]["id"], set()):
                    out.append(f"{people[pid]['name']} está no domingo {dmy(d)} de manhã e à noite")
    wk = {}
    for sid, pids in playing.items():
        d = byid[sid]["date"]
        for pid in pids:
            wk.setdefault((pid, (d - dt.timedelta(days=d.weekday())).toordinal()), set()).add(d)
    mx = int(cfg.get("max_dias_semana", 3))
    for (pid, _), ds in wk.items():
        if len(ds) > mx:
            out.append(f"{people[pid]['name']} tem {len(ds)} dias na mesma semana")
    out += custom_rules.check(custom_rules.load(c, only_active=True), people, S, grid, scheduler.eligible, unav)
    return out


# ---------------------------------------------------------------- foto pessoal
# A foto chega já recortada (quadrada, 512 px, JPG) pelo navegador (static/js/photo.js), que também tira
# os dados escondidos (EXIF/GPS). Fica em <pasta do banco>/fotos/<nome aleatório>.jpg; o nome aleatório
# evita adivinhar a foto de alguém e muda a cada envio (o navegador nunca mostra a foto velha).
FOTO_MAX = 2 * 1024 * 1024


def foto_dir():
    return os.path.join(os.path.dirname(db.DB_PATH), "fotos")


def foto_url(p):
    name = p["foto"] if p and "foto" in p.keys() else ""
    return url_for("foto", name=name) if name else None


app.jinja_env.globals["foto_url"] = foto_url


def foto_remove(name):
    if name:
        try:
            os.remove(os.path.join(foto_dir(), name + ".jpg"))
        except OSError:
            pass


@app.get("/foto/<name>.jpg")
def foto(name):
    if not all(ch.isalnum() or ch in "-_" for ch in name) or not 8 <= len(name) <= 40:
        abort(404)
    r = send_from_directory(foto_dir(), name + ".jpg", mimetype="image/jpeg", max_age=31536000)
    r.headers["X-Content-Type-Options"] = "nosniff"
    return r


@app.post("/p/<token>/foto")
def photo_upload(token):
    c = conn()
    p = c.execute("SELECT * FROM person WHERE token=? AND active=1", (token,)).fetchone()
    if not p:
        abort(404)
    back = redirect(url_for("person_page", token=token))
    if request.form.get("acao") == "remover":
        foto_remove(p["foto"])
        c.execute("UPDATE person SET foto='' WHERE id=?", (p["id"],))
        c.commit()
        flash("Foto removida.")
        return back
    f = request.files.get("foto")
    data = f.read(FOTO_MAX + 1) if f else b""
    if not data:
        flash("Não consegui enviar a foto: escolha uma imagem.")
        return back
    if len(data) > FOTO_MAX or not data.startswith(b"\xff\xd8\xff"):
        flash("Não consegui enviar a foto: use uma imagem JPG ou PNG (o navegador ajusta o tamanho sozinho).")
        return back
    os.makedirs(foto_dir(), exist_ok=True)
    name = secrets.token_urlsafe(12)
    with open(os.path.join(foto_dir(), name + ".jpg"), "wb") as out:
        out.write(data)
    foto_remove(p["foto"])
    c.execute("UPDATE person SET foto=? WHERE id=?", (name, p["id"]))
    c.commit()
    flash("Foto atualizada.")
    return back


# ---------------------------------------------------------------- avaliações
RATE_DAYS = 3   # a avaliação abre no dia do culto e fica aberta por mais 3 dias


def _today():
    return dt.date.today()   # (função própria para os testes poderem simular outra data)


def rate_window(s, today=None):
    """Janela de avaliação de um culto: dict(state='antes'|'aberta'|'encerrada', start, end)."""
    today = today or _today()
    start, end = s["date"], s["date"] + dt.timedelta(days=RATE_DAYS)
    state = "antes" if today < start else ("aberta" if today <= end else "encerrada")
    return dict(state=state, start=start, end=end)


def band_of(grid, s):
    """[(pessoa, função)] da BANDA do culto, na ordem das funções. Kids e Intercessão não avaliam nem são
    avaliados. Quem está em mais de uma função (ex.: ministra e toca) aparece uma vez por função."""
    return [(grid[(s["id"], r)], r) for r in s["roles"]
            if r not in db.AUTO_ROLES and grid.get((s["id"], r))]


def rate_key(pid, role):
    """Nome do campo de estrelas de uma pessoa numa função ('|' não existe em nome de função)."""
    return f"nota_{pid}|{role}"


# ---------------------------------------------------------------- trocas pelo ministro
def can_swap(grid, s, pid, today=None):
    """O ministro do culto (quem está como Ministro) pode trocar a banda até o fim do dia do culto."""
    return grid.get((s["id"], "Ministro")) == pid and (today or _today()) <= s["date"]


def swap_candidates(c, s, grid, people=None, unav=None):
    """Quem pode entrar numa vaga deste culto: qualquer pessoa ativa, sem indisponibilidade no dia/turno
    e que ainda não está em NENHUMA função deste culto. (Regras de domingo/carga não se aplicam.)"""
    people = people or load_people(c)
    unav = unav if unav is not None else load_unav(c)
    inside = {pid for (sid, r), pid in grid.items() if sid == s["id"]}
    return [p for p in people if p["active"] and p["id"] not in inside and scheduler.eligible(p, s, unav)]


def swap_messages(c, t):
    """Links de WhatsApp para avisar quem entrou e quem saiu numa troca."""
    s = c.execute("SELECT * FROM service WHERE id=?", (t["service_id"],)).fetchone()
    d = dt.date.fromisoformat(s["date"])
    quando = f"{WD[d.weekday()]}, {dmy(d)} ({s['turn']})"
    out = []
    new = c.execute("SELECT * FROM person WHERE id=?", (t["new_id"],)).fetchone() if t["new_id"] else None
    old = c.execute("SELECT * FROM person WHERE id=?", (t["old_id"],)).fetchone() if t["old_id"] else None
    if new:
        lugar = f", no lugar de {t['old_name']}" if t["old_name"] else ""
        msg = (f"Oi {new['name']}! 🎶 Você foi escalado(a) como {t['role']} no culto de {quando}{lugar}. "
               f"Combinado? Veja a escala no seu link: {base_url()}/p/{new['token']}")
        out.append(dict(name=new["name"], who="quem entrou", wa=notify.whatsapp_link(new["phone"], msg)))
    if old:
        msg = (f"Oi {old['name']}! Tudo certo: {t['new_name']} vai te substituir como {t['role']} "
               f"no culto de {quando}. Qualquer coisa, fale comigo.")
        out.append(dict(name=old["name"], who="quem saiu", wa=notify.whatsapp_link(old["phone"], msg)))
    return out


@app.post("/p/<token>/trocar")
def swap(token):
    """O ministro do culto troca uma pessoa da banda (ou preenche uma vaga)."""
    c = conn()
    p = c.execute("SELECT * FROM person WHERE token=? AND active=1", (token,)).fetchone()
    if not p:
        abort(404)
    sid = request.form.get("service_id", type=int)
    row = c.execute("""SELECT s.month_id FROM service s JOIN month m ON m.id=s.month_id
                       WHERE s.id=? AND m.status='publicada'""", (sid,)).fetchone()
    if not row:
        abort(404)
    s = [x for x in load_services(c, row["month_id"]) if x["id"] == sid][0]
    grid = grid_of(c, row["month_id"])
    back = redirect(url_for("person_page", token=token, culto=sid) + f"#culto-{sid}")
    if grid.get((sid, "Ministro")) != p["id"]:
        abort(403)
    if _today() > s["date"]:
        flash("Não consegui fazer a troca: este culto já passou.")
        return back
    role = request.form.get("role", "")
    if role not in s["roles"] or role in db.AUTO_ROLES:
        flash("Não consegui fazer a troca: escolha uma função da banda.")
        return back
    new_id = request.form.get("new_id", type=int)
    ok = {x["id"]: x for x in swap_candidates(c, s, grid)}
    if new_id not in ok:
        flash("Não consegui fazer a troca: essa pessoa já está neste culto ou marcou indisponibilidade.")
        return back
    old_id = grid.get((sid, role))
    names = {r["id"]: r["name"] for r in c.execute("SELECT id, name FROM person")}
    c.execute("INSERT OR REPLACE INTO assignment(service_id, role, person_id, locked) VALUES(?,?,?,1)",
              (sid, role, new_id))
    cur = c.execute("""INSERT INTO troca(service_id, role, old_id, new_id, by_id, old_name, new_name, by_name, at)
                       VALUES(?,?,?,?,?,?,?,?,?)""",
                    (sid, role, old_id, new_id, p["id"], names.get(old_id), names[new_id], p["name"],
                     dt.datetime.now().isoformat(timespec="minutes")))
    c.commit()
    flash(f"Troca feita: {role} agora é {names[new_id]}" + (f" (no lugar de {names[old_id]})." if old_id else "."))
    return redirect(url_for("person_page", token=token, troca=cur.lastrowid))


# ---------------------------------------------------------------- público
@app.route("/")
def home():
    return render_template("home.html")


@app.route("/p/<token>", methods=["GET", "POST"])
def person_page(token):
    c = conn()
    p = c.execute("SELECT * FROM person WHERE token=? AND active=1", (token,)).fetchone()
    if not p:
        abort(404)
    open_months = c.execute("SELECT * FROM month WHERE status='coleta' ORDER BY ym").fetchall()
    pub_months = c.execute("SELECT * FROM month WHERE status='publicada' ORDER BY ym").fetchall()
    forms = []
    for m in open_months:
        forms.append((m, load_services(c, m["id"])))
    err = None  # (month_id, mensagem) quando o envio é recusado; a tela volta com o que a pessoa marcou
    un_override, motivo_override = None, None
    if request.method == "POST":
        mid = int(request.form["month_id"])
        m = get_month(c, mid)
        if m["status"] != "coleta":
            abort(400)
        info = deadline_info(m)
        if info["closed"]:
            flash(f"O prazo para responder terminou em {info['label']}. "
                  "Suas respostas não foram alteradas; para mudar algo, fale com o responsável.")
            return redirect(url_for("person_page", token=token))
        S = load_services(c, mid)
        marked = [s for s in S if request.form.get(f"nao_{s['id']}")]
        motivo = request.form.get("motivo", "").strip()[:MOTIVO_MAX]
        if marked and not motivo:
            err = (mid, "Conte o motivo da indisponibilidade para poder salvar.")
            un_override = {(s["date"].isoformat(), s["turn"]) for s in marked}
            motivo_override = ""
        else:
            dates = {s["date"].isoformat() for s in S}
            c.execute(f"DELETE FROM unavail WHERE person_id=? AND date IN ({','.join('?' * len(dates))})",
                      [p["id"], *dates])
            for s in marked:
                c.execute("INSERT OR IGNORE INTO unavail(person_id,date,turn) VALUES(?,?,?)",
                          (p["id"], s["date"].isoformat(), s["turn"]))
            now = dt.datetime.now().isoformat(timespec="seconds")
            if motivo:
                c.execute("INSERT OR REPLACE INTO justificativa VALUES(?,?,?,?)", (p["id"], mid, motivo, now))
            else:
                c.execute("DELETE FROM justificativa WHERE person_id=? AND month_id=?", (p["id"], mid))
            c.execute("INSERT OR REPLACE INTO responded VALUES(?,?,?)", (p["id"], mid, now))
            c.commit()
            flash("Pronto! Suas indisponibilidades foram salvas. Obrigado 🙏")
            return redirect(url_for("person_page", token=token))
    un = {(r["date"], r["turn"]) for r in c.execute("SELECT * FROM unavail WHERE person_id=?", (p["id"],))}
    if un_override is not None:
        dates_err = {s["date"].isoformat() for s in load_services(c, err[0])}
        un = {u for u in un if u[0] not in dates_err} | un_override
    motivos = {r["month_id"]: r["texto"] for r in c.execute(
        "SELECT month_id, texto FROM justificativa WHERE person_id=?", (p["id"],))}
    if err:
        motivos[err[0]] = motivo_override
    done = {r["month_id"] for r in c.execute("SELECT month_id FROM responded WHERE person_id=?", (p["id"],))}
    mine = []
    people_all, unav_all = load_people(c), load_unav(c)   # para a lista de substitutos (ministro)
    kinds_all = db.role_kinds(c)
    for m in pub_months:
        S = load_services(c, m["id"])
        g_ = grid_of(c, m["id"])
        names = {r["id"]: r["name"] for r in c.execute("SELECT id, name FROM person")}
        items = []
        for s in S:
            rs = [r for r in s["roles"] if g_.get((s["id"], r)) == p["id"]]
            if not rs:
                continue
            # equipe do culto, em grupos: banda, Louvor Kids, Intercessão (vaga = None)
            band = band_of(g_, s)
            i_rate = any(pid == p["id"] for pid, _ in band)    # só quem está na banda avalia
            given = {(r["rated_id"], r["role"]): r["stars"] for r in c.execute(
                "SELECT rated_id, role, stars FROM avaliacao WHERE service_id=? AND rater_id=?", (s["id"], p["id"]))}
            team = {"Banda": [], "Som, mídia e luz": [], "Louvor Kids": [], "Intercessão": []}
            for r in s["roles"]:
                grp = ("Louvor Kids" if r in (db.KIDS_INST, db.KIDS_VOZ)
                       else "Intercessão" if r in db.INTERC_ROLES
                       else "Som, mídia e luz" if kinds_all.get(db.base_of(r)) == "exclusiva" else "Banda")
                pid = g_.get((s["id"], r))
                team[grp].append(dict(role=r, name=names.get(pid), me=pid == p["id"], pid=pid,
                                      rateable=i_rate and grp == "Banda" and pid and pid != p["id"],
                                      stars=given.get((pid, r), 0), key=rate_key(pid, r)))
            n_rate = sum(1 for pid, _ in band if pid != p["id"])
            swap_ui = None
            if can_swap(g_, s, p["id"]):
                cands = swap_candidates(c, s, g_, people_all, unav_all)
                swap_ui = dict(rows=[dict(role=r, name=names.get(g_.get((s["id"], r))))
                                     for r in s["roles"] if r not in db.AUTO_ROLES],
                               cands=sorted(cands, key=lambda x: x["name"].lower()))
            rate = dict(rate_window(s), can=i_rate and n_rate > 0,
                        total=n_rate if i_rate else 0, done=len(given))
            items.append((s, rs, [(k, v) for k, v in team.items() if v], rate, swap_ui))
        mine.append((m, items))
    blocked = [WD[i] for i in sorted(int(x) for x in p["blocked_wd"].split(",") if x != "")]
    # troca recém-feita por este ministro: botões de WhatsApp para avisar quem entrou e quem saiu
    done_swap = None
    tid = request.args.get("troca", type=int)
    if tid:
        t = c.execute("SELECT * FROM troca WHERE id=? AND by_id=?", (tid, p["id"])).fetchone()
        if t:
            done_swap = dict(t=t, msgs=swap_messages(c, t))
    return render_template("person.html", p=p, forms=forms, un=un, done=done, mine=mine,
                           open_sid=request.args.get("culto", type=int), today=_today(),
                           done_swap=done_swap,
                           blocked=blocked, month_title=month_title, motivos=motivos, err=err,
                           motivo_max=MOTIVO_MAX), (400 if err else 200)


# ---------------------------------------------------------------- admin: login
@app.post("/p/<token>/avaliar")
def rate(token):
    """Salva as estrelas que a pessoa deu aos colegas da banda de um culto."""
    c = conn()
    p = c.execute("SELECT * FROM person WHERE token=? AND active=1", (token,)).fetchone()
    if not p:
        abort(404)
    sid = request.form.get("service_id", type=int)
    row = c.execute("""SELECT s.month_id FROM service s JOIN month m ON m.id=s.month_id
                       WHERE s.id=? AND m.status='publicada'""", (sid,)).fetchone()
    if not row:
        abort(404)
    s = [x for x in load_services(c, row["month_id"]) if x["id"] == sid][0]
    back = redirect(url_for("person_page", token=token, culto=sid) + f"#culto-{sid}")
    w = rate_window(s)
    if w["state"] != "aberta":
        flash("A avaliação deste culto não está aberta." if w["state"] == "antes"
              else "O prazo para avaliar este culto terminou.")
        return back
    band = band_of(grid_of(c, row["month_id"]), s)
    if not any(pid == p["id"] for pid, _ in band):
        abort(403)
    now = dt.datetime.now().isoformat(timespec="seconds")
    n = 0
    for pid, role in band:                            # uma nota por pessoa E por função
        if pid == p["id"]:
            continue                                  # ninguém se avalia
        v = request.form.get(rate_key(pid, role), "")
        if v in ("1", "2", "3", "4", "5"):
            c.execute("""INSERT INTO avaliacao(service_id, rater_id, rated_id, role, stars, at) VALUES(?,?,?,?,?,?)
                         ON CONFLICT(service_id, rater_id, rated_id, role)
                         DO UPDATE SET stars=excluded.stars, at=excluded.at""",
                      (sid, p["id"], pid, role, int(v), now))
            n += 1
        elif v == "0":
            c.execute("DELETE FROM avaliacao WHERE service_id=? AND rater_id=? AND rated_id=? AND role=?",
                      (sid, p["id"], pid, role))
    c.commit()
    flash("Avaliações salvas. Obrigado! 🙏" if n else "Nenhuma estrela marcada; nada foi salvo.")
    return back


@app.route("/admin/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form.get("senha") == ADMIN_PASSWORD:
            session["admin"] = True
            return redirect(request.args.get("next") or url_for("admin_index"))
        flash("Senha incorreta.")
    return render_template("admin_login.html")


@app.route("/admin/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))


@app.route("/admin")
@admin_required
def admin_index():
    c = conn()
    months = c.execute("SELECT * FROM month ORDER BY ym DESC").fetchall()
    stats = {}
    n = c.execute("SELECT COUNT(*) FROM person WHERE active=1").fetchone()[0]
    for m in months:
        r = c.execute("SELECT COUNT(*) FROM responded WHERE month_id=?", (m["id"],)).fetchone()[0]
        stats[m["id"]] = (r, n)
    nxt = dt.date.today().replace(day=1) + dt.timedelta(days=32)
    return render_template("admin_index.html", months=months, stats=stats,
                           suggest=f"{nxt.year}-{nxt.month:02d}", month_title=month_title)


@app.post("/admin/mes/novo")
@admin_required
def month_new():
    c = conn()
    ym = request.form["ym"]
    y, mo = map(int, ym.split("-"))
    if c.execute("SELECT 1 FROM month WHERE ym=?", (ym,)).fetchone():
        flash("Esse mês já existe.")
        return redirect(url_for("admin_index"))
    cur = c.execute("INSERT INTO month(ym,title) VALUES(?,?)", (ym, month_title(ym)))
    mid = cur.lastrowid
    wds = {int(x) for x in request.form.getlist("wd")}
    allroles = ",".join(db.default_roles(c))   # fixas + funções criadas com "entra em todos os cultos"
    for day in range(1, calendar.monthrange(y, mo)[1] + 1):
        d = dt.date(y, mo, day)
        if d.weekday() not in wds:
            continue
        turns = ["Manhã", "Noite"] if d.weekday() == 6 else ["Noite"]
        for t in turns:
            roles = "Teclado" if d.weekday() == 4 else allroles
            c.execute("INSERT INTO service(month_id,date,turn,roles) VALUES(?,?,?,?)",
                      (mid, d.isoformat(), t, roles))
    c.commit()
    return redirect(url_for("month_page", mid=mid))


# ---------------------------------------------------------------- admin: pessoas
@app.route("/admin/pessoas")
@admin_required
def people_page():
    c = conn()
    people = load_people(c)
    # mês de referência para a coluna "Disponibilidade": o que está em coleta; senão, o mais recente
    ref = (c.execute("SELECT * FROM month WHERE status='coleta' ORDER BY ym DESC LIMIT 1").fetchone()
           or c.execute("SELECT * FROM month ORDER BY ym DESC LIMIT 1").fetchone())
    resp = {}
    if ref:
        resp = {r["person_id"]: r["at"] for r in c.execute(
            "SELECT person_id, at FROM responded WHERE month_id=?", (ref["id"],))}
    # o que seria apagado junto, para a confirmação de exclusão
    impact = collections.defaultdict(lambda: dict(duplas=0, escalas=0, regras=0))
    for a, b in c.execute("SELECT a, b FROM pair"):
        impact[a]["duplas"] += 1
        impact[b]["duplas"] += 1
    for (x,) in c.execute("SELECT person_id FROM assignment"):
        impact[x]["escalas"] += 1
    for a, b in c.execute("SELECT person_a, person_b FROM regra_custom"):
        for x in {a, b} - {None}:
            impact[x]["regras"] += 1
    return render_template("admin_people.html", people=people, base=base_url(),
                           wa=notify.whatsapp_link, ref=ref, resp=resp, impact=impact,
                           ref_title=month_title(ref["ym"]) if ref else None)


@app.post("/admin/pessoa/<int:pid>/excluir")
@admin_required
def person_delete(pid):
    c = conn()
    p = c.execute("SELECT name FROM person WHERE id=?", (pid,)).fetchone()
    if not p:
        abort(404)
    # funções, duplas, indisponibilidades, respostas, justificativas, escalações e regras
    # saem junto (ON DELETE CASCADE); a fila de mensagens não tem chave estrangeira
    c.execute("DELETE FROM outbox WHERE person_id=?", (pid,))
    foto_remove(c.execute("SELECT foto FROM person WHERE id=?", (pid,)).fetchone()["foto"])
    c.execute("DELETE FROM person WHERE id=?", (pid,))
    c.commit()
    flash(f"{p['name']} foi excluído(a) da lista.")
    return redirect(url_for("people_page"))


@app.post("/admin/pessoas/nova")
@admin_required
def person_new():
    c = conn()
    name = request.form["name"].strip()
    if name:
        try:
            cur = c.execute("INSERT INTO person(name,token) VALUES(?,?)", (name, db.new_token()))
            c.commit()
            return redirect(url_for("person_edit", pid=cur.lastrowid))
        except Exception:
            flash("Já existe alguém com esse nome.")
    return redirect(url_for("people_page"))


@app.route("/admin/pessoa/<int:pid>", methods=["GET", "POST"])
@admin_required
def person_edit(pid):
    c = conn()
    p = c.execute("SELECT * FROM person WHERE id=?", (pid,)).fetchone()
    if not p:
        abort(404)
    if request.method == "POST":
        f = request.form
        act = f.get("acao", "salvar")
        if act == "token":
            c.execute("UPDATE person SET token=? WHERE id=?", (db.new_token(), pid))
        elif act == "par_add":
            err = pair_add(c, pid, f.get("outro"), f.get("peso"))
            if err:
                flash(err)
                return redirect(url_for("person_edit", pid=pid))
        elif act.startswith("par_del"):
            c.execute("DELETE FROM pair WHERE id=?", (int(act.split(":")[1]),))
        else:
            mm = f.get("max_month", "").strip()
            phone = f.get("phone", "").strip()
            if phone:
                phone = notify.br_mobile(phone)
                if not phone:
                    flash("Celular inválido: use DDD + número com 9 dígitos, ex.: (41) 99999-9999. Nada foi salvo.")
                    return redirect(url_for("person_edit", pid=pid))
            c.execute("""UPDATE person SET name=?, phone=?, active=?, sunday_only=?, rest_weekend=?,
                      max_month=?, blocked_wd=?, notes=? WHERE id=?""",
                      (f["name"].strip(), phone, int(bool(f.get("active"))),
                       int(bool(f.get("sunday_only"))), int(bool(f.get("rest_weekend"))),
                       int(mm) if mm.isdigit() else None,
                       ",".join(sorted(f.getlist("wd"))), f.get("notes", ""), pid))
            c.execute("DELETE FROM person_role WHERE person_id=?", (pid,))
            valid = set(db.all_roles(c))
            for r in f.getlist("role"):
                if r in valid:
                    c.execute("INSERT OR IGNORE INTO person_role VALUES(?,?)", (pid, r))
            if act == "funcao_nova" and f.get("nova_funcao", "").strip():
                role, err, existed = role_create(c, f["nova_funcao"], f.get("nova_funcao_tipo", "outro"))
                c.execute("INSERT OR IGNORE INTO person_role VALUES(?,?)", (pid, role)) if role else None
                c.commit()
                nome = f["name"].strip()
                if err:
                    flash("Não consegui criar a função: " + err + " Os outros dados foram salvos.")
                elif existed:
                    flash(f"A função {role} já existia e foi marcada para {nome}.")
                else:
                    flash(f"Função {role} criada e marcada para {nome}. Para ela entrar na escala, "
                          f"marque-a nos cultos em que é usada (Meses → Cultos).")
                return redirect(url_for("person_edit", pid=pid) + "#funcoes")
        c.commit()
        flash("Salvo.")
        return redirect(url_for("person_edit", pid=pid))
    p = [x for x in load_people(c) if x["id"] == pid][0]
    pairs = c.execute("""SELECT pair.id, pair.weight, o.name FROM pair
        JOIN person o ON o.id = CASE WHEN pair.a=? THEN pair.b ELSE pair.a END
        WHERE pair.a=? OR pair.b=?""", (pid, pid, pid)).fetchall()
    # só quem ainda não forma dupla com esta pessoa e ainda não chegou ao limite de duplas
    counts = pair_counts(c)
    others = [o for o in c.execute("""SELECT id,name FROM person WHERE id!=? AND id NOT IN
        (SELECT CASE WHEN a=? THEN b ELSE a END FROM pair WHERE a=? OR b=?) ORDER BY name""",
                                   (pid, pid, pid, pid)) if counts[o["id"]] < MAX_PAIRS]
    return render_template("admin_person.html", p=p, pairs=pairs, others=others, max_pairs=MAX_PAIRS,
                           link=f"{base_url()}/p/{p['token']}")


# ---------------------------------------------------------------- admin: funções
def role_create(c, raw, tipo="outro"):
    """Cria uma função nova (tipo: instrumento | voz | outro). Devolve (nome, erro, já_existia)."""
    name, err = db.clean_role(raw)
    if err:
        return None, err, False
    for r in db.all_roles(c):
        if r.lower() == name.lower():
            return r, None, True
    tipo = tipo if tipo in db.ROLE_TYPES else "outro"
    c.execute("INSERT INTO funcao(name, tipo) VALUES(?,?)", (name, tipo))
    return name, None, False


def role_usage(c):
    """{função criada: dict(tipo, pessoas, cultos, escalas, regras)}"""
    out = {}
    tipos = dict(c.execute("SELECT name, tipo FROM funcao").fetchall())
    for r in db.custom_roles(c):
        q, pd = c.execute("SELECT qtd, padrao FROM funcao WHERE name=?", (r,)).fetchone()
        out[r] = dict(
            tipo=tipos.get(r, "outro"), qtd=q, padrao=pd,
            pessoas=c.execute("SELECT count(*) FROM person_role WHERE role=?", (r,)).fetchone()[0],
            cultos=sum(1 for (roles,) in c.execute("SELECT roles FROM service") if r in (roles or "").split(",")),
            escalas=sum(1 for (x,) in c.execute("SELECT role FROM assignment") if db.base_of(x) == r),
            regras=c.execute("SELECT count(*) FROM regra_custom WHERE role=?", (r,)).fetchone()[0])
    return out


@app.post("/admin/funcoes/nova")
@admin_required
def role_new():
    c = conn()
    role, err, existed = role_create(c, request.form.get("nome"), request.form.get("tipo", "outro"))
    c.commit()
    if err:
        flash("Não consegui criar a função: " + err)
    elif existed:
        flash(f"Já existe a função {role}.")
    else:
        flash(f"Função {role} criada. Marque-a nas pessoas que a exercem e nos cultos em que é usada.")
    return redirect(url_for("config_page") + "#funcoes")


@app.post("/admin/funcoes/tipo")
@admin_required
def role_type():
    """Configurações de uma função criada: tipo, pessoas por culto e se entra em todos os cultos."""
    c = conn()
    f = request.form
    name = f.get("nome", "")
    if name not in db.custom_roles(c):
        abort(400)
    if f.get("acao") == "todos":           # marcar agora em todos os cultos já cadastrados
        n = 0
        for sid, roles in c.execute("SELECT id, roles FROM service").fetchall():
            rs = [r for r in (roles or "").split(",") if r]
            if name not in rs:
                c.execute("UPDATE service SET roles=? WHERE id=?", (",".join(rs + [name]), sid))
                n += 1
        c.commit()
        flash(f"{name} marcada em {n} culto(s). Gere a escala de novo para preencher as vagas.")
        return redirect(url_for("config_page") + "#funcoes")
    tipo = f.get("tipo", "")
    qtd = f.get("qtd", type=int) or 1
    if tipo not in db.ROLE_TYPES or not 1 <= qtd <= 5:
        abort(400)
    old = c.execute("SELECT qtd FROM funcao WHERE name=?", (name,)).fetchone()[0]
    if qtd != old:                          # renomeia/apaga as vagas já escaladas para o novo número
        new_slots = db.slots(name, qtd)
        for a in c.execute("SELECT rowid, service_id, role FROM assignment").fetchall():
            if db.base_of(a["role"]) != name:
                continue
            old_i = 1 if a["role"] == name else int(a["role"][-2])
            if old_i > qtd:
                c.execute("DELETE FROM assignment WHERE rowid=?", (a["rowid"],))
            else:
                c.execute("UPDATE OR REPLACE assignment SET role=? WHERE rowid=?", (new_slots[old_i - 1], a["rowid"]))
    c.execute("UPDATE funcao SET tipo=?, qtd=?, padrao=? WHERE name=?", (tipo, qtd, int(bool(f.get("padrao"))), name))
    c.commit()
    flash(f"{name}: {db.ROLE_TYPES[tipo].lower()}, {qtd} pessoa{'s' if qtd > 1 else ''} por culto"
          + (", entra nos cultos novos." if f.get("padrao") else "."))
    return redirect(url_for("config_page") + "#funcoes")


@app.post("/admin/funcoes/excluir")
@admin_required
def role_delete():
    c = conn()
    name = request.form.get("nome", "")
    if name in db.BAND_ROLES or name not in db.custom_roles(c):
        abort(400)
    c.execute("DELETE FROM person_role WHERE role=?", (name,))
    for (role,) in c.execute("SELECT DISTINCT role FROM assignment").fetchall():   # inclui as vagas "Nome (2)"
        if db.base_of(role) == name:
            c.execute("DELETE FROM assignment WHERE role=?", (role,))
    c.execute("DELETE FROM regra_custom WHERE role=?", (name,))
    for sid, roles in c.execute("SELECT id, roles FROM service").fetchall():
        rs = (roles or "").split(",")
        if name in rs:
            c.execute("UPDATE service SET roles=? WHERE id=?", (",".join(x for x in rs if x != name), sid))
    c.execute("DELETE FROM funcao WHERE name=?", (name,))
    c.commit()
    flash(f"Função {name} excluída.")
    return redirect(url_for("config_page") + "#funcoes")


# ---------------------------------------------------------------- admin: duplas
PAIR_WEIGHTS = {1: "fraca", 3: "normal", 6: "forte"}
MAX_PAIRS = 2   # cada pessoa pode estar em no máximo 2 duplas


def pair_counts(c):
    """{person_id: quantas duplas a pessoa tem}"""
    n = collections.Counter()
    for a, b in c.execute("SELECT a, b FROM pair"):
        n[a] += 1
        n[b] += 1
    return n


def pair_add(c, a, b, weight):
    """Cria uma dupla (sempre 2 pessoas). Devolve a mensagem de erro, ou None se criou."""
    try:
        a, b = int(a), int(b)
    except (TypeError, ValueError):
        return "Não consegui criar a dupla: escolha as duas pessoas."
    if a == b:
        return "Não consegui criar a dupla: escolha duas pessoas diferentes."
    names = dict(c.execute("SELECT id, name FROM person WHERE id IN (?,?)", (a, b)).fetchall())
    if len(names) != 2:
        return "Não consegui criar a dupla: pessoa não encontrada."
    if c.execute("SELECT 1 FROM pair WHERE (a=? AND b=?) OR (a=? AND b=?)", (a, b, b, a)).fetchone():
        return f"Já existe uma dupla entre {names[a]} e {names[b]}."
    counts = pair_counts(c)
    full = [names[x] for x in (a, b) if counts[x] >= MAX_PAIRS]
    if full:
        quem = " e ".join(full)
        return (f"Não consegui criar a dupla: {quem} já {'têm' if len(full) > 1 else 'tem'} "
                f"{MAX_PAIRS} duplas, o máximo por pessoa. Remova uma antes de criar outra.")
    w = int(weight) if str(weight).isdigit() and int(weight) in PAIR_WEIGHTS else 3
    c.execute("INSERT INTO pair(a,b,weight) VALUES(?,?,?)", (a, b, w))
    return None


@app.route("/admin/duplas", methods=["GET", "POST"])
@admin_required
def pairs_page():
    c = conn()
    if request.method == "POST":
        f = request.form
        act = f.get("acao", "")
        if act == "add":
            err = pair_add(c, f.get("pessoa_a"), f.get("pessoa_b"), f.get("peso"))
            if err:
                flash(err)
                return redirect(url_for("pairs_page"))
            flash("Dupla criada.")
        elif act.startswith("del:") and act[4:].isdigit():
            c.execute("DELETE FROM pair WHERE id=?", (int(act[4:]),))
            flash("Dupla removida.")
        else:
            abort(400)
        c.commit()
        return redirect(url_for("pairs_page"))

    people = {r["id"]: r for r in c.execute("SELECT id, name, active FROM person")}
    # cultos em que cada pessoa foi escalada (todos os meses) -> quantas vezes cada dupla tocou junta
    served = collections.defaultdict(set)
    for r in c.execute("SELECT DISTINCT person_id, service_id FROM assignment"):
        served[r[0]].add(r[1])
    pairs, links = [], collections.defaultdict(list)
    for r in c.execute("SELECT id, a, b, weight FROM pair"):
        if r["a"] not in people or r["b"] not in people:
            continue
        pa, pb = people[r["a"]], people[r["b"]]
        pairs.append(dict(id=r["id"], a=pa, b=pb, weight=r["weight"],
                          forca=PAIR_WEIGHTS.get(r["weight"], f"peso {r['weight']}"),
                          juntos=len(served[r["a"]] & served[r["b"]])))
        links[r["a"]].append(pb["name"])
        links[r["b"]].append(pa["name"])
    pairs.sort(key=lambda d: (d["a"]["name"].lower(), d["b"]["name"].lower()))
    ranking = sorted(((people[pid], sorted(ns, key=str.lower)) for pid, ns in links.items()),
                     key=lambda t: (-len(t[1]), t[0]["name"].lower()))
    n_active = sum(1 for p in people.values() if p["active"])
    n_alone = sum(1 for pid, p in people.items() if p["active"] and pid not in links)
    everyone = sorted(people.values(), key=lambda p: p["name"].lower())
    counts = {pid: len(ns) for pid, ns in links.items()}
    return render_template("admin_pairs.html", pairs=pairs, ranking=ranking, everyone=everyone,
                           n_active=n_active, n_alone=n_alone, weights=PAIR_WEIGHTS,
                           counts=counts, max_pairs=MAX_PAIRS)


# ---------------------------------------------------------------- admin: config
@app.route("/admin/config", methods=["GET", "POST"])
@admin_required
def config_page():
    c = conn()
    if request.method == "POST":
        for k in db.DEFAULT_SETTINGS:
            if k == "regra_domingo":
                c.execute("UPDATE settings SET value='1' WHERE key=?", (k,))  # regra fixa: sempre ativa
            elif k in request.form:
                c.execute("UPDATE settings SET value=? WHERE key=?", (request.form[k], k))
        c.commit()
        flash("Configurações salvas.")
        return redirect(url_for("config_page"))
    people = load_people(c)
    names = {p["id"]: p["name"] for p in people}
    regras = [dict(r, desc=custom_rules.describe(r, names)) for r in custom_rules.load(c)]
    return render_template("admin_config.html", s=db.get_settings(c), regras=regras,
                           kinds=custom_rules.KINDS, pessoas=[p for p in people if p["active"]],
                           fixed_roles=db.BAND_ROLES, role_usage=role_usage(c), role_types=db.ROLE_TYPES)


@app.post("/admin/regras/nova")
@admin_required
def rule_new():
    c = conn()
    people = {p["id"]: p for p in load_people(c) if p["active"]}
    r, err = custom_rules.parse_form(request.form, people, db.all_roles(c) + db.AUTO_ROLES)
    if err:
        flash("Não consegui criar a regra: " + err)
        return redirect(url_for("config_page") + "#nova-regra")
    c.execute("""INSERT INTO regra_custom(kind,hard,person_a,person_b,weekday,turn,role,n,note)
                 VALUES(:kind,:hard,:person_a,:person_b,:weekday,:turn,:role,:n,:note)""", r)
    c.commit()
    flash("Regra criada: " + custom_rules.describe(r, {k: v["name"] for k, v in people.items()}) + ".")
    return redirect(url_for("config_page") + "#regras-personalizadas")


@app.post("/admin/regras/<int:rid>")
@admin_required
def rule_action(rid):
    c = conn()
    act = request.form.get("acao")
    if act == "excluir":
        c.execute("DELETE FROM regra_custom WHERE id=?", (rid,))
        msg = "Regra excluída."
    elif act in ("ativar", "pausar"):
        c.execute("UPDATE regra_custom SET active=? WHERE id=?", (1 if act == "ativar" else 0, rid))
        msg = "Regra ativada." if act == "ativar" else "Regra pausada (não será aplicada até ser ativada)."
    else:
        abort(400)
    c.commit()
    flash(msg)
    return redirect(url_for("config_page") + "#regras-personalizadas")


# ---------------------------------------------------------------- admin: mês
@app.route("/admin/mes/<int:mid>")
@admin_required
def month_page(mid):
    c = conn()
    m = get_month(c, mid)
    S = load_services(c, mid)
    people = load_people(c)
    resp = {r["person_id"]: r["at"] for r in c.execute("SELECT * FROM responded WHERE month_id=?", (mid,))}
    mt = month_title(m["ym"])
    base = base_url()
    rows = []
    for p in people:
        if not p["active"]:
            continue
        link = f"{base}/p/{p['token']}"
        msg_ask = (f"Oi {p['name']}! 🎶 Já está aberta a coleta de indisponibilidades da escala do louvor de "
                   f"{mt}. Marque os dias em que você NÃO pode: {link}")
        rows.append(dict(p=p, at=resp.get(p["id"]), wa=notify.whatsapp_link(p["phone"], msg_ask)))
    # indisponibilidades marcadas (nº de cultos) e motivo de cada pessoa neste mês
    svc = {(s["date"].isoformat(), s["turn"]) for s in S}
    nmarked = {}
    for r in c.execute("SELECT person_id, date, turn FROM unavail"):
        if (r["date"], r["turn"]) in svc:
            nmarked[r["person_id"]] = nmarked.get(r["person_id"], 0) + 1
    just = {r["person_id"]: r["texto"] for r in c.execute(
        "SELECT person_id, texto FROM justificativa WHERE month_id=?", (mid,))}
    for row in rows:
        row["nmarked"] = nmarked.get(row["p"]["id"], 0)
        row["motivo"] = just.get(row["p"]["id"], "")
    return render_template("admin_month.html", m=m, S=S, rows=rows, mt=mt,
                           nresp=len(resp), n=len(rows), has_assign=bool(grid_of(c, mid)))


@app.get("/admin/mes/<int:mid>/cultos")
@admin_required
def services_page(mid):
    """Página "Cultos" do mês (o formulário é salvo por services_save, mesma URL via POST)."""
    c = conn()
    m = get_month(c, mid)
    return render_template("admin_services.html", m=m, S=load_services(c, mid), mt=month_title(m["ym"]))


@app.post("/admin/mes/<int:mid>/cultos")
@admin_required
def services_save(mid):
    c = conn()
    f = request.form
    get_month(c, mid)
    act = f.get("acao")
    if act == "novo":
        d = dt.date.fromisoformat(f["nova_data"])
        roles = "Teclado" if f.get("nova_tipo") == "sexta" else ",".join(db.default_roles(c))
        c.execute("INSERT INTO service(month_id,date,turn,roles) VALUES(?,?,?,?)",
                  (mid, d.isoformat(), f["nova_turno"], roles))
    else:
        for s in load_services(c, mid):
            i = s["id"]
            if f.get(f"del_{i}"):
                c.execute("DELETE FROM service WHERE id=?", (i,))
                continue
            c.execute("""UPDATE service SET tema=?, pregador=?, roles=?, exempt=? WHERE id=?""",
                      (f.get(f"tema_{i}", ""), f.get(f"preg_{i}", ""),
                       ",".join(r for r in f.getlist(f"roles_{i}") if r not in db.AUTO_ROLES),
                       int(bool(f.get(f"ex_{i}"))), i))
        c.execute("UPDATE month SET deadline=? WHERE id=?", (f.get("deadline", ""), mid))
    c.commit()
    flash("Cultos salvos.")
    return redirect(url_for("services_page", mid=mid))


@app.post("/admin/mes/<int:mid>/status")
@admin_required
def month_status(mid):
    c = conn()
    st = request.form["status"]
    if st in ("coleta", "rascunho", "publicada"):
        c.execute("UPDATE month SET status=? WHERE id=?", (st, mid))
        c.commit()
    return redirect(request.referrer or url_for("month_page", mid=mid))


@app.post("/admin/mes/<int:mid>/gerar")
@admin_required
def generate(mid):
    c = conn()
    m = get_month(c, mid)
    S = load_services(c, mid)
    locked = {(r["service_id"], r["role"]): r["person_id"] for r in c.execute(
        "SELECT a.* FROM assignment a JOIN service s ON s.id=a.service_id WHERE s.month_id=? AND a.locked=1", (mid,))}
    pairs = [(r["a"], r["b"], r["weight"]) for r in c.execute("SELECT * FROM pair")]
    res = scheduler.solve(load_people(c), S, load_unav(c), locked, pairs,
                          prev_loads(c, m["ym"]), db.get_settings(c),
                          rules=custom_rules.load(c, only_active=True), kinds=db.role_kinds(c))
    if not res["assign"] and res["status"] not in ("OPTIMAL", "FEASIBLE"):
        flash(f"Não consegui montar uma escala ({res['status']}). Revise restrições/bloqueios.")
        return redirect(url_for("month_page", mid=mid))
    c.execute("""DELETE FROM assignment WHERE locked=0 AND service_id IN
              (SELECT id FROM service WHERE month_id=?)""", (mid,))
    for (sid, role), pid in res["assign"].items():
        c.execute("INSERT OR REPLACE INTO assignment(service_id,role,person_id,locked) VALUES(?,?,?,0)",
                  (sid, role, pid))
    if m["status"] == "coleta":
        c.execute("UPDATE month SET status='rascunho' WHERE id=?", (mid,))
    c.commit()
    nv = len(res["vacancies"])
    flash("Escala gerada." + (f" Atenção: {nv} vaga(s) sem ninguém disponível." if nv else " Nenhuma vaga em aberto."))
    return redirect(url_for("schedule_page", mid=mid))


@app.route("/admin/mes/<int:mid>/escala", methods=["GET", "POST"])
@admin_required
def schedule_page(mid):
    c = conn()
    m = get_month(c, mid)
    S = load_services(c, mid)
    people = load_people(c)
    if request.method == "POST":
        old = {(r["service_id"], r["role"]): r for r in c.execute(
            "SELECT a.* FROM assignment a JOIN service s ON s.id=a.service_id WHERE s.month_id=?", (mid,))}
        for s in S:
            for role in s["roles"]:
                v = request.form.get(f"sel_{s['id']}_{role}", "")
                lk = int(bool(request.form.get(f"lock_{s['id']}_{role}")))
                o = old.get((s["id"], role))
                if not v:
                    c.execute("DELETE FROM assignment WHERE service_id=? AND role=?", (s["id"], role))
                    continue
                changed = (o is None) or o["person_id"] != int(v)
                c.execute("INSERT OR REPLACE INTO assignment(service_id,role,person_id,locked) VALUES(?,?,?,?)",
                          (s["id"], role, int(v), 1 if changed else lk))
        c.commit()
        flash("Escala salva. Células alteradas à mão ficam travadas 🔒 e são mantidas ao gerar de novo.")
        return redirect(url_for("schedule_page", mid=mid))
    grid = {(r["service_id"], r["role"]): r for r in c.execute(
        "SELECT a.* FROM assignment a JOIN service s ON s.id=a.service_id WHERE s.month_id=?", (mid,))}
    unav = load_unav(c)
    opts = {}
    for s in S:
        for role in s["roles"]:
            lst = []
            for p in people:
                if p["active"] and db.can_take(p["roles"], role):
                    lst.append((p["id"], p["name"], not scheduler.eligible(p, s, unav)))
            opts[s["id"], role] = lst
    names = {p["id"]: p["name"] for p in people}
    cnt = {}
    for (sid, role), r in grid.items():
        if role not in db.NO_LOAD_ROLES:   # gráfico/carga: Intercessão não conta
            cnt.setdefault(r["person_id"], set()).add(sid)
    loads = sorted(((len(v), names[k]) for k, v in cnt.items()), key=lambda t: (-t[0], t[1]))
    trocas = c.execute("""SELECT t.*, s.date, s.turn FROM troca t JOIN service s ON s.id=t.service_id
                          WHERE s.month_id=? ORDER BY t.at DESC, t.id DESC""", (mid,)).fetchall()
    trocas = [dict(t, date=dt.date.fromisoformat(t["date"])) for t in trocas]
    return render_template("admin_schedule.html", m=m, S=S, grid=grid, opts=opts, loads=loads, trocas=trocas,
                           warns=conflicts(c, mid), mt=month_title(m["ym"]))


@app.route("/admin/mes/<int:mid>/xlsx")
@admin_required
def export_xlsx(mid):
    c = conn()
    m = get_month(c, mid)
    names = {p["id"]: p["name"] for p in load_people(c)}
    buf = exporter.build(month_title(m["ym"]).upper(), load_services(c, mid), grid_of(c, mid), names,
                         db.get_settings(c)["igreja"],
                         extra_roles=[x for r in db.custom_roles(c) for x in db.slots(r, db.role_qtd(c).get(r, 1))])
    return send_file(buf, as_attachment=True, download_name=f"escala_louvor_{m['ym']}.xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@app.route("/admin/mes/<int:mid>/avaliacoes")
@admin_required
def ratings_page(mid):
    """Avaliações do mês: média por pessoa e cada nota com quem deu (só o responsável vê)."""
    c = conn()
    m = get_month(c, mid)
    S = {s["id"]: s for s in load_services(c, mid)}
    names = {r["id"]: r["name"] for r in c.execute("SELECT id, name FROM person")}
    per = collections.defaultdict(list)
    for r in c.execute("""SELECT a.* FROM avaliacao a JOIN service s ON s.id=a.service_id
                         WHERE s.month_id=? ORDER BY s.date, a.at""", (mid,)):
        per[r["rated_id"]].append(dict(s=S[r["service_id"]], by=names.get(r["rater_id"], "?"), stars=r["stars"],
                                       role=r["role"] or "—"))
    def by_role(v):   # média por função (ex.: Ministro 5,0 · Violão 1,0)
        g = collections.defaultdict(list)
        for x in v:
            g[x["role"]].append(x["stars"])
        return sorted(((r, sum(n) / len(n), len(n)) for r, n in g.items()), key=lambda t: t[0])
    people = sorted(((names.get(pid, "?"), sum(x["stars"] for x in v) / len(v), v, by_role(v)) for pid, v in per.items()),
                    key=lambda t: (-t[1], t[0].lower()))
    total = sum(len(v) for v in per.values())
    avg = (sum(x["stars"] for v in per.values() for x in v) / total) if total else 0
    raters = len({(r[0]) for r in c.execute("""SELECT DISTINCT a.rater_id FROM avaliacao a JOIN service s
                   ON s.id=a.service_id WHERE s.month_id=?""", (mid,))})
    return render_template("admin_ratings.html", m=m, mt=month_title(m["ym"]), people=people,
                           total=total, avg=avg, raters=raters, rate_days=RATE_DAYS)


@app.route("/admin/mes/<int:mid>/avisos")
@admin_required
def notices(mid):
    """Links de WhatsApp com a escala de cada pessoa (para enviar depois de publicar)."""
    c = conn()
    m = get_month(c, mid)
    S = load_services(c, mid)
    g_ = grid_of(c, mid)
    mt = month_title(m["ym"])
    out = []
    for p in load_people(c):
        items = [f"• {WDS[s['date'].weekday()]} {dmy(s['date'])} ({s['turn']}): "
                 + ", ".join(r for r in s["roles"] if g_.get((s["id"], r)) == p["id"])
                 for s in S if any(g_.get((s["id"], r)) == p["id"] for r in s["roles"])]
        if not items or not p["active"]:
            continue
        msg = f"Oi {p['name']}! 🎶 Sua escala do louvor de {mt}:\n" + "\n".join(items) + \
              f"\n\nVeja/ajuste no seu link: {base_url()}/p/{p['token']}"
        out.append((p, items, msg, notify.whatsapp_link(p["phone"], msg)))
    return render_template("admin_notices.html", m=m, out=out, mt=mt)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    conn_ = db.init()
    if not conn_.execute("SELECT 1 FROM person").fetchone():
        seed.run()
    try:
        from waitress import serve
        print(f"Servidor em http://0.0.0.0:{port}  (painel: /admin)")
        serve(app, host="0.0.0.0", port=port)
    except ImportError:
        app.run(host="0.0.0.0", port=port)
