"""Regras personalizadas (criadas na tela Regras).

Tipos:
  nunca_juntos     A e B nunca no mesmo culto                         (person_a, person_b)
  bloquear_turno   A não toca em <dia da semana> [+ turno]            (person_a, weekday, turn)
  fixar            A sempre na função F em <dia> [+ turno], se puder  (person_a, role, weekday, turn)
  minimo           A toca pelo menos N cultos no mês, se puder        (person_a, n)

Cada regra é "obrigatória" (hard=1) ou "preferência" (hard=0).
Como o otimizador aplica cada tipo está em scheduler.solve(..., rules=...).
"""
import db


KINDS = {
    "nunca_juntos": "Nunca juntos",
    "bloquear_turno": "Bloquear dia + turno",
    "fixar": "Fixar pessoa em culto",
    "minimo": "Mínimo de cultos",
}
TURNS = ("", "Manhã", "Noite")  # "" = qualquer turno
_WD_PLURAL = ["às segundas", "às terças", "às quartas", "às quintas", "às sextas", "aos sábados", "aos domingos"]
_TURN_TXT = {"": "", "Manhã": " de manhã", "Noite": " à noite"}


def load(c, only_active=False):
    sql = "SELECT * FROM regra_custom" + (" WHERE active=1" if only_active else "") + " ORDER BY id"
    return [dict(r) for r in c.execute(sql)]


def when(rule):
    """Ex.: 'aos domingos de manhã', 'às sextas'."""
    return _WD_PLURAL[rule["weekday"]] + _TURN_TXT.get(rule.get("turn") or "", "")


def describe(rule, names):
    a = names.get(rule["person_a"], "?")
    k = rule["kind"]
    if k == "nunca_juntos":
        return f"{a} e {names.get(rule['person_b'], '?')} nunca tocam no mesmo culto"
    if k == "bloquear_turno":
        return f"{a} não toca {when(rule)}"
    if k == "fixar":
        return f"{a} sempre como {rule['role']} {when(rule)} (quando disponível)"
    if k == "minimo":
        n = rule["n"]
        return f"{a} toca pelo menos {n} culto{'s' if n != 1 else ''} no mês (quando disponível)"
    return k


def parse_form(f, valid_people, valid_roles):
    """Valida o formulário de nova regra. Retorna (dict, None) ou (None, mensagem_de_erro)."""
    kind = f.get("kind", "")
    if kind not in KINDS:
        return None, "Escolha o tipo da regra."

    def pid(field):
        v = f.get(field, "")
        return int(v) if v.isdigit() and int(v) in valid_people else None

    r = dict(kind=kind, hard=1 if f.get("hard", "1") == "1" else 0, person_a=pid("person_a"),
             person_b=None, weekday=None, turn="", role="", n=None, note=f.get("note", "").strip()[:200])
    if r["person_a"] is None:
        return None, "Escolha a pessoa."
    if kind == "nunca_juntos":
        r["person_b"] = pid("person_b")
        if r["person_b"] is None:
            return None, "Escolha a segunda pessoa."
        if r["person_b"] == r["person_a"]:
            return None, "Escolha duas pessoas diferentes."
    if kind in ("bloquear_turno", "fixar"):
        wd = f.get("weekday", "")
        if not (wd.isdigit() and 0 <= int(wd) <= 6):
            return None, "Escolha o dia da semana."
        r["weekday"] = int(wd)
        r["turn"] = f.get("turn", "") if f.get("turn", "") in TURNS else ""
    if kind == "fixar":
        if f.get("role") not in valid_roles:
            return None, "Escolha a função."
        r["role"] = f["role"]
    if kind == "minimo":
        n = f.get("n", "")
        if not (n.isdigit() and 1 <= int(n) <= 31):
            return None, "Informe um número de cultos entre 1 e 31."
        r["n"] = int(n)
    return r, None


def matches(rule, service):
    """O culto cai no dia da semana (+ turno, se definido) da regra?"""
    return service["date"].weekday() == rule["weekday"] and (not rule.get("turn") or rule["turn"] == service["turn"])


def check(rules, people, services, grid, eligible_fn, unav):
    """Confere uma escala pronta contra as regras OBRIGATÓRIAS ativas. Retorna lista de avisos.
    people: {id: pessoa}; grid: {(service_id, role): person_id}"""
    from_service = {}
    for (sid, role), pid in grid.items():
        from_service.setdefault(sid, set()).add(pid)
    load = {}
    for sid, pids in from_service.items():
        for pid in pids:
            load[pid] = load.get(pid, 0) + 1
    names = {pid: p["name"] for pid, p in people.items()}
    out = []
    for r in rules:
        if not (r["active"] and r["hard"]):
            continue
        a = r["person_a"]
        if a not in people or not people[a]["active"]:
            continue
        txt = describe(r, names)
        tag = lambda s: f"{s['date'].day:02d}/{s['date'].month:02d} {s['turn']}"
        if r["kind"] == "nunca_juntos":
            b = r["person_b"]
            for s in services:
                if {a, b} <= from_service.get(s["id"], set()):
                    out.append(f"Regra “{txt}” não cumprida em {tag(s)}")
        elif r["kind"] == "bloquear_turno":
            for s in services:
                if matches(r, s) and a in from_service.get(s["id"], set()):
                    out.append(f"Regra “{txt}” não cumprida em {tag(s)}")
        elif r["kind"] == "fixar":
            p = people[a]
            for s in services:
                if (matches(r, s) and r["role"] in s["roles"] and db.can_take(p["roles"], r["role"])
                        and eligible_fn(p, s, unav) and grid.get((s["id"], r["role"])) != a):
                    out.append(f"Regra “{txt}” não cumprida em {tag(s)}")
        elif r["kind"] == "minimo":
            if load.get(a, 0) < r["n"]:
                out.append(f"Regra “{txt}” não cumprida: {load.get(a, 0)} culto(s) no mês")
    return out
