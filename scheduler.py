"""Otimizador da escala (OR-Tools CP-SAT).

Regras DURAS (nunca violadas):
  - indisponibilidades informadas / dias da semana bloqueados / "só domingos"
  - acúmulo no mesmo culto: a pessoa pode ministrar, cantar e tocar juntos, mas no máximo 1 instrumento
    e 1 voz; Kids, Intercessão e funções criadas do tipo "outro" não acumulam (db.combo_problem)
  - máximo de dias diferentes por semana
  - (fixa) quem toca/canta no domingo de manhã não toca/canta à noite, exceto culto "banda fixa"
  - "descanso de fim de semana": não toca em dois fins de semana seguidos
  - limite mensal individual (se definido)
Regras SUAVES (o otimizador tenta, por ordem de importância):
  - nenhuma vaga em aberto
  - não sobrecarregar ninguém (penalidade crescente acima do limite confortável)
  - quem tocou muito no mês anterior tem o limite reduzido
  - evitar a mesma pessoa em dias seguidos / mais de 2 dias na semana
  - manter duplas juntas (cada dupla = 2 pessoas; um trio vira 3 duplas); no Louvor Kids, o casal
    fica junto no Kids (um toca, o outro canta)
  - Intercessão em rodízio: espalhar entre todos, evitando repetir a mesma pessoa
Funções AUTOMÁTICAS (db.AUTO_ROLES): Louvor Kids (domingos: 1 instrumento — Guitarra/Violão/Teclado —
  e 1 voz) conta como participação; Intercessão (2 por culto, qualquer pessoa) NÃO conta na carga,
  nos dias por semana, na regra do domingo nem no descanso de fim de semana. Continua valendo
  exclusivas (quem está na Intercessão ou no Kids não está na banda daquele culto).
Carga: estar em várias funções no MESMO culto conta como 1 culto.
Regras PERSONALIZADAS (tela Regras, ver rules.py), parâmetro `rules`:
  - "nunca juntos" e "bloquear dia+turno": obrigatória = restrição dura; preferência = penalidade
  - "fixar" e "mínimo de cultos": obrigatória = prioridade máxima (acima de preencher vagas), mas
    nunca torna a escala impossível; se não der para cumprir, conflicts() avisa; preferência = penalidade
"""
import collections, datetime as dt, itertools, os
from ortools.sat.python import cp_model
import db


def eligible(p, s, unav):
    d = s["date"]
    if (p["id"], d, "") in unav or (p["id"], d, s["turn"]) in unav:
        return False
    w = d.weekday()
    if w in p["blocked_wd"]:
        return False
    if p["sunday_only"] and w != 6:
        return False
    return True


W_RULE_HARD = 5000   # regra obrigatória do tipo "exigir" (acima de uma vaga em aberto = 1000)
W_RULE_SOFT = 40     # regra de preferência


def _matches(rule, s):
    return s["date"].weekday() == rule["weekday"] and (not rule.get("turn") or rule["turn"] == s["turn"])


def solve(people, services, unav, locked, pairs, prev_load, cfg, time_limit=None, seed=7, rules=None,
          kinds=None):
    """people: lista de dicts (id,name,roles,blocked_wd,sunday_only,rest_weekend,max_month,active)
    services: lista de dicts (id,date,turn,roles(list),exempt)
    unav: set de (person_id, date, turn|'')
    locked: {(service_id, role): person_id}
    pairs: [(a, b, weight)]   prev_load: {person_id: cultos no mês anterior}
    rules: regras personalizadas ativas (rules.load(c, only_active=True)); None = nenhuma
    kinds: {função: 'ministro'|'voz'|'instrumento'|'exclusiva'} (db.role_kinds); None = só as fixas"""
    time_limit = time_limit or int(cfg.get("tempo_calculo", 40))
    L0 = int(cfg.get("limite_confortavel", 5))
    maxwk = int(cfg.get("max_dias_semana", 3))
    # Regra FIXA do domingo (sempre ativa): quem toca/canta de manhã não toca/canta à noite no mesmo
    # domingo, exceto se algum dos dois cultos estiver marcado como "banda fixa". Louvor Kids conta;
    # Intercessão não conta. A chave "regra_domingo" em settings é ignorada desde que virou fixa.
    sun_rule = True

    P = {p["id"]: p for p in people if p["active"]}
    S = sorted(services, key=lambda s: (s["date"], 0 if s["turn"] == "Manhã" else 1, s["id"]))
    byid = {s["id"]: s for s in S}
    dates = sorted({s["date"] for s in S})

    NL = db.NO_LOAD_ROLES
    if kinds is None:
        kinds = {"Ministro": "ministro", **{r: "voz" for r in db.VOICE_PARTS},
                 **{r: "instrumento" for r in db.INSTRUMENTS}}
    kind = lambda r: kinds.get(db.base_of(r), kinds.get(r, "exclusiva"))   # 'Tecnico de Som (2)' -> tipo da função
    fixed_roles = collections.defaultdict(list)    # (pessoa, culto) -> funções travadas
    fixed_in = collections.defaultdict(set)        # travados em qualquer função
    fixed_in_load = collections.defaultdict(set)   # travados em função que conta como participação
    fixed_interc = collections.Counter()
    for (si, r), pid in locked.items():
        if si in byid and pid in P:
            fixed_roles[pid, si].append(r)
            fixed_in[si].add(pid)
            if r in NL:
                fixed_interc[pid] += 1
            else:
                fixed_in_load[si].add(pid)

    def fits_locked(pid, si, r):
        """A função r ainda cabe para a pessoa neste culto, junto do que já está travado?"""
        fr = fixed_roles.get((pid, si))
        return not fr or db.combo_problem(fr + [r], kinds) is None

    slots = [(s["id"], r) for s in S for r in s["roles"] if (s["id"], r) not in locked]
    m = cp_model.CpModel()
    x = {}
    for si, r in slots:
        for pid, p in P.items():
            if db.can_take(p["roles"], r) and fits_locked(pid, si, r) and eligible(p, byid[si], unav):
                x[pid, si, r] = m.NewBoolVar(f"x{pid}_{si}_{r}")

    vac = {}
    for si, r in slots:
        vs = [x[pid, si, r] for pid in P if (pid, si, r) in x]
        vac[si, r] = m.NewBoolVar(f"v{si}_{r}")
        m.Add(sum(vs) + vac[si, r] == 1)

    by_ps = collections.defaultdict(list)       # todas as funções da pessoa no culto
    by_ps_load = collections.defaultdict(list)  # só as que contam como participação (sem Intercessão)
    by_kind = collections.defaultdict(list)     # (pessoa, culto, tipo) -> variáveis
    by_ps_music = collections.defaultdict(list) # toca/canta/Kids: o que vale para a regra do domingo
    music = lambda r: r in (db.KIDS_INST, db.KIDS_VOZ) or kind(r) in ("ministro", "voz", "instrumento")
    for (pid, si, r), v in x.items():
        by_ps[pid, si].append(v)
        if r not in NL:
            by_ps_load[pid, si].append(v)
        if music(r):
            by_ps_music[pid, si].append(v)
        by_kind[pid, si, kind(r)].append(v)
    fixed_in_music = collections.defaultdict(set)
    for (pid, si), rs in fixed_roles.items():
        if any(music(r) for r in rs):
            fixed_in_music[si].add(pid)
    # acúmulo no mesmo culto: no máx. 1 instrumento, 1 voz (Ministro acumula); exclusiva não acumula
    for (pid, si), vs in by_ps.items():
        fk = [kind(r) for r in fixed_roles.get((pid, si), [])]
        inst, voz, exc = (by_kind.get((pid, si, k), []) for k in ("instrumento", "voz", "exclusiva"))
        if len(inst) > 1:
            m.Add(sum(inst) <= 1)
        if len(voz) > 1:
            m.Add(sum(voz) <= 1)
        if exc:
            others = [v for v in vs if all(v is not e for e in exc)]   # (identidade: == de variável vira restrição)
            m.Add(sum(exc) <= 1)
            if others:
                m.Add(sum(others) <= len(others) * (1 - sum(exc)))

    presence, presence_load, presence_music = {}, {}, {}

    def _any(vs, name):
        if len(vs) == 1:
            return vs[0]
        b = m.NewBoolVar(name)
        m.AddMaxEquality(b, vs)
        return b

    def PB(pid, si):
        """Está no culto em qualquer função (inclusive Intercessão)? 0/1 (várias funções = 1)."""
        if pid in fixed_in[si]:
            return 1
        vs = by_ps.get((pid, si))
        if not vs:
            return 0
        if (pid, si) not in presence:
            presence[pid, si] = _any(vs, "pb")
        return presence[pid, si]

    def PL(pid, si):
        """Toca/canta no culto (banda ou Kids) — conta como participação, uma vez por culto."""
        if pid in fixed_in_load[si]:
            return 1
        vs = by_ps_load.get((pid, si))
        if not vs:
            return 0
        if (pid, si) not in presence_load:
            presence_load[pid, si] = _any(vs, "pl")
        return presence_load[pid, si]

    def PM(pid, si):
        """Toca, canta ou faz o Kids no culto (regra do domingo). Som/mídia/luz e Intercessão não contam."""
        if pid in fixed_in_music[si]:
            return 1
        vs = by_ps_music.get((pid, si))
        if not vs:
            return 0
        if (pid, si) not in presence_music:
            presence_music[pid, si] = _any(vs, "pm")
        return presence_music[pid, si]

    obj = [1000 * v for v in vac.values()]

    # regra: domingo de manhã x domingo à noite
    if sun_rule:
        for d in dates:
            if d.weekday() != 6:
                continue
            km = [s for s in S if s["date"] == d and s["turn"] == "Manhã"]
            kn = [s for s in S if s["date"] == d and s["turn"] == "Noite"]
            if not km or not kn or any(s["exempt"] for s in km + kn):
                continue
            for pid in P:
                a, b = PM(pid, km[0]["id"]), PM(pid, kn[0]["id"])
                if isinstance(a, int) and isinstance(b, int):
                    continue
                m.Add(a + b <= 1)

    # carga por pessoa
    L = {}
    for pid, p in P.items():
        L[pid] = m.NewIntVar(0, 60, f"L{pid}")
        m.Add(L[pid] == sum(PL(pid, s["id"]) for s in S))   # um culto conta 1, mesmo com várias funções
        if p.get("max_month"):
            m.Add(L[pid] <= int(p["max_month"]))
        shift = 1 if prev_load.get(pid, 0) > L0 else 0
        for i, w in enumerate([1, 1, 2, 3, 12, 25, 80, 150]):
            t = L0 - 3 + i - shift
            o = m.NewIntVar(0, 60, "o")
            m.Add(o >= L[pid] - t)
            obj.append(w * o)

    # dias (por dia, a pessoa conta uma vez)
    day = {}
    for pid in P:
        for d in dates:
            ks = [s["id"] for s in S if s["date"] == d]
            if any(pid in fixed_in_load[k] for k in ks):
                day[pid, d] = 1
                continue
            vs = [v for k in ks for v in by_ps_load.get((pid, k), [])]
            if not vs:
                day[pid, d] = 0
                continue
            dv = m.NewBoolVar("d")
            m.AddMaxEquality(dv, vs)
            day[pid, d] = dv
        for d1, d2 in itertools.combinations(dates, 2):
            g = (d2 - d1).days
            a, b = day[pid, d1], day[pid, d2]
            if g <= 2 and not (isinstance(a, int) and a == 0) and not (isinstance(b, int) and b == 0):
                y = m.NewBoolVar("y")
                m.Add(y >= a + b - 1)
                obj.append((4 if g == 1 else 3) * y)
        wk = collections.defaultdict(list)
        for d in dates:
            wk[(d - dt.timedelta(days=d.weekday())).toordinal()].append(day[pid, d])
        for vs in wk.values():
            e = m.NewIntVar(0, 7, "e")
            m.Add(e >= sum(vs) - 2)
            obj.append(10 * e)
            m.Add(sum(vs) <= maxwk)

    # descanso de fim de semana
    for pid, p in P.items():
        if not p["rest_weekend"]:
            continue
        W = collections.defaultdict(list)
        for s in S:
            if s["date"].weekday() >= 5:
                W[(s["date"] - dt.timedelta(days=s["date"].weekday())).toordinal()].append(PL(pid, s["id"]))
        wv = {}
        for w, vs in W.items():
            if any(isinstance(v, int) and v == 1 for v in vs):
                wv[w] = 1
            else:
                vs = [v for v in vs if not isinstance(v, int)]
                if vs:
                    b = m.NewBoolVar("w")
                    for v in vs:
                        m.Add(b >= v)
                    wv[w] = b
        for w in wv:
            if w + 7 in wv:
                m.Add(wv[w] + wv[w + 7] <= 1)

    # duplas juntas
    for a, b, w in pairs:
        if a not in P or b not in P:
            continue
        for s in S:
            pa, pb = PB(a, s["id"]), PB(b, s["id"])
            if isinstance(pa, int) and isinstance(pb, int):
                continue
            dv = m.NewIntVar(0, 1, "df")
            m.Add(dv >= pa - pb)
            m.Add(dv >= pb - pa)
            obj.append(w * dv)
            # Louvor Kids: se um do casal está no Kids, o outro também (um toca, o outro canta)
            if db.KIDS_INST in s["roles"]:
                kr = (db.KIDS_INST, db.KIDS_VOZ)
                ka = sum(x[a, s["id"], r] for r in kr if (a, s["id"], r) in x) + sum(
                    1 for r in kr if locked.get((s["id"], r)) == a)
                kb = sum(x[b, s["id"], r] for r in kr if (b, s["id"], r) in x) + sum(
                    1 for r in kr if locked.get((s["id"], r)) == b)
                if not (isinstance(ka, int) and isinstance(kb, int)):
                    dk = m.NewIntVar(0, 1, "dk")
                    m.Add(dk >= ka - kb)
                    m.Add(dk >= kb - ka)
                    obj.append(3 * w * dk)

    # Intercessão em rodízio: penaliza repetir a mesma pessoa (1ª vez sai de graça)
    for pid in P:
        vs = [v for (q, si, r), v in x.items() if q == pid and r in NL]
        if not vs:
            continue
        ic = fixed_interc[pid] + sum(vs)
        for t, w in ((1, 30), (2, 80)):
            o = m.NewIntVar(0, 60, "ic")
            m.Add(o >= ic - t)
            obj.append(w * o)

    # regras personalizadas
    for r in rules or ():
        a = r["person_a"]
        if a not in P:
            continue
        hard = bool(r["hard"])
        k = r["kind"]
        if k == "nunca_juntos":
            b = r.get("person_b")
            if b not in P:
                continue
            for s in S:
                pa, pb = PB(a, s["id"]), PB(b, s["id"])
                if isinstance(pa, int) and isinstance(pb, int):
                    continue  # ambos travados/ausentes: nada a decidir (conflicts() avisa)
                if hard:
                    m.Add(pa + pb <= 1)
                else:
                    y = m.NewBoolVar("rj")
                    m.Add(y >= pa + pb - 1)
                    obj.append(W_RULE_SOFT * y)
        elif k == "bloquear_turno":
            for s in S:
                if not _matches(r, s):
                    continue
                for v in by_ps.get((a, s["id"]), []):
                    if hard:
                        m.Add(v == 0)
                    else:
                        obj.append(W_RULE_SOFT * v)
        elif k == "fixar":
            for s in S:
                if not _matches(r, s) or r["role"] not in s["roles"] or (s["id"], r["role"]) in locked:
                    continue
                v = x.get((a, s["id"], r["role"]))
                if v is None:
                    continue  # pessoa indisponível/sem a função/travada em outra: não se aplica
                obj.append((W_RULE_HARD if hard else W_RULE_SOFT) * (1 - v))
        elif k == "minimo":
            short = m.NewIntVar(0, 60, "rm")
            m.Add(short >= int(r["n"]) - L[a])
            obj.append((W_RULE_HARD if hard else W_RULE_SOFT) * short)

    m.Minimize(sum(obj))
    sv = cp_model.CpSolver()
    sv.parameters.max_time_in_seconds = time_limit
    sv.parameters.num_workers = min(8, os.cpu_count() or 4)
    sv.parameters.random_seed = seed
    st = sv.Solve(m)
    status = sv.StatusName(st)
    if st not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return {"status": status, "assign": {}, "vacancies": [], "loads": {}}
    assign = {(si, r): pid for (pid, si, r), v in x.items() if sv.Value(v)}
    vacancies = [(si, r) for (si, r), v in vac.items() if sv.Value(v)]
    loads = {pid: sv.Value(L[pid]) for pid in P}
    return {"status": status, "assign": assign, "vacancies": vacancies, "loads": loads,
            "objective": sv.ObjectiveValue()}
