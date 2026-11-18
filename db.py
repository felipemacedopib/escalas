"""Banco de dados (SQLite) do sistema de escalas."""
import os, sqlite3, secrets

BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("ESCALAS_DB", os.path.join(BASE, "data", "escalas.db"))

BAND_ROLES = ["Ministro", "Soprano", "Contralto", "Tenor",
              "Guitarra", "Bateria", "Baixo", "Teclado", "Violão"]

# Funções AUTOMÁTICAS: o sistema coloca nos cultos sozinho e escolhe quem pode, sem marcar na pessoa.
#   Louvor Kids: todo domingo (manhã e noite) — 1 pessoa que toca + 1 que canta. Conta como participação.
#   Intercessão: todo culto — 2 pessoas; qualquer pessoa ativa. NÃO conta na carga nem na regra do domingo.
KIDS_INST = "Kids (instrumento)"
KIDS_VOZ = "Kids (voz)"
INTERC_ROLES = ["Intercessor 1", "Intercessor 2"]
AUTO_ROLES = [KIDS_INST, KIDS_VOZ] + INTERC_ROLES
KIDS_INSTRUMENTS = {"Guitarra", "Violão", "Teclado"}
VOICES = {"Ministro", "Soprano", "Contralto", "Tenor"}
NO_LOAD_ROLES = set(INTERC_ROLES)      # não contam como culto tocado (carga, dias, domingo, descanso)

# Acúmulo de funções NO MESMO CULTO (regra): a pessoa pode ministrar, cantar e tocar juntos, mas
#   no máximo 1 instrumento e no máximo 1 voz; Ministro acumula com os dois.
#   "exclusiva" (Kids, Intercessão e funções criadas do tipo "outro", ex.: Técnico de Som) não acumula com nada.
INSTRUMENTS = {"Guitarra", "Bateria", "Baixo", "Teclado", "Violão"}
VOICE_PARTS = {"Soprano", "Contralto", "Tenor"}
ROLE_TYPES = {"instrumento": "Instrumento", "voz": "Voz", "outro": "Outra (não acumula)"}


import re as _re
_SLOT = _re.compile(r"^(.*) \((\d)\)$")


def slots(base, qtd):
    """Vagas de uma função no culto: 'Tecnico de Som' com 2 pessoas -> ['Tecnico de Som (1)', '... (2)']."""
    qtd = max(1, int(qtd or 1))
    return [base] if qtd == 1 else [f"{base} ({i})" for i in range(1, qtd + 1)]


def base_of(role):
    """Função de uma vaga: 'Tecnico de Som (2)' -> 'Tecnico de Som'. (Intercessor 1/2 são próprias.)"""
    m = _SLOT.match(role or "")
    return m.group(1) if m else role


def role_qtd(c):
    """{função criada: pessoas por culto}"""
    return {n: q for n, q in c.execute("SELECT name, qtd FROM funcao")}


def default_roles(c):
    """Funções que já vêm marcadas num culto novo: as fixas + as criadas com 'entra em todos os cultos'."""
    return BAND_ROLES + [n for (n,) in c.execute("SELECT name FROM funcao WHERE padrao=1 ORDER BY created, rowid")]


def all_slots(c):
    """Todas as vagas possíveis, na ordem de exibição (linhas da Escala / Excel)."""
    q = role_qtd(c)
    return [s for r in all_roles(c) for s in slots(r, q.get(r, 1))] + AUTO_ROLES


def role_kinds(c):
    """{função: 'ministro'|'voz'|'instrumento'|'exclusiva'} para todas as funções conhecidas."""
    k = {"Ministro": "ministro"}
    k.update({r: "voz" for r in VOICE_PARTS})
    k.update({r: "instrumento" for r in INSTRUMENTS})
    k.update({r: "exclusiva" for r in AUTO_ROLES})
    for name, tipo in c.execute("SELECT name, tipo FROM funcao"):
        k[name] = tipo if tipo in ("instrumento", "voz") else "exclusiva"
    return k


def combo_problem(roles, kinds):
    """Se esta combinação de funções de uma pessoa no MESMO culto quebra a regra, devolve o motivo."""
    ks = [kinds.get(base_of(r), kinds.get(r, "exclusiva")) for r in roles]
    if len(roles) > 1 and "exclusiva" in ks:
        r = next(r for r, k in zip(roles, ks) if k == "exclusiva")
        return f"{r} não acumula com outra função"
    if ks.count("instrumento") > 1:
        return "mais de um instrumento (" + ", ".join(r for r, k in zip(roles, ks) if k == "instrumento") + ")"
    if ks.count("voz") > 1:
        return "mais de uma voz (" + ", ".join(r for r, k in zip(roles, ks) if k == "voz") + ")"
    return None


def auto_roles_for(date):
    """Funções automáticas de um culto nesta data."""
    return ([KIDS_INST, KIDS_VOZ] if date.weekday() == 6 else []) + INTERC_ROLES


def can_take(person_roles, role):
    """A pessoa (com estas funções marcadas) pode assumir esta função/vaga?"""
    role = base_of(role)
    if role == KIDS_INST:
        return bool(KIDS_INSTRUMENTS & set(person_roles))
    if role == KIDS_VOZ:
        return bool(VOICES & set(person_roles))
    if role in INTERC_ROLES:
        return True
    return role in person_roles

DEFAULT_SETTINGS = {
    "limite_confortavel": "5",     # cultos/mês que a pessoa faz sem se sentir sobrecarregada
    "max_dias_semana": "3",        # máximo de dias diferentes por semana (regra dura)
    "regra_domingo": "1",          # 1 = quem toca no domingo de manhã não toca à noite
    "tempo_calculo": "40",         # segundos que o otimizador pode usar
    "igreja": "Escala do Louvor",
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS person(
  id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL, token TEXT UNIQUE NOT NULL,
  phone TEXT DEFAULT '', active INTEGER DEFAULT 1,
  sunday_only INTEGER DEFAULT 0, rest_weekend INTEGER DEFAULT 0,
  max_month INTEGER, blocked_wd TEXT DEFAULT '', notes TEXT DEFAULT '',
  foto TEXT DEFAULT '');   -- nome (aleatório) do arquivo da foto em data/fotos/<foto>.jpg
CREATE TABLE IF NOT EXISTS person_role(
  person_id INTEGER REFERENCES person(id) ON DELETE CASCADE, role TEXT,
  PRIMARY KEY(person_id, role));
CREATE TABLE IF NOT EXISTS pair(
  id INTEGER PRIMARY KEY, a INTEGER REFERENCES person(id) ON DELETE CASCADE,
  b INTEGER REFERENCES person(id) ON DELETE CASCADE, weight INTEGER DEFAULT 3);
CREATE TABLE IF NOT EXISTS month(
  id INTEGER PRIMARY KEY, ym TEXT UNIQUE NOT NULL, status TEXT DEFAULT 'coleta',
  title TEXT DEFAULT '', deadline TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS service(
  id INTEGER PRIMARY KEY, month_id INTEGER REFERENCES month(id) ON DELETE CASCADE,
  date TEXT NOT NULL, turn TEXT NOT NULL, roles TEXT DEFAULT '',
  pregador TEXT DEFAULT '', tema TEXT DEFAULT '', kids TEXT DEFAULT '',
  interc TEXT DEFAULT '', exempt INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS unavail(
  person_id INTEGER REFERENCES person(id) ON DELETE CASCADE, date TEXT, turn TEXT DEFAULT '',
  PRIMARY KEY(person_id, date, turn));
CREATE TABLE IF NOT EXISTS responded(
  person_id INTEGER REFERENCES person(id) ON DELETE CASCADE,
  month_id INTEGER REFERENCES month(id) ON DELETE CASCADE, at TEXT,
  PRIMARY KEY(person_id, month_id));
CREATE TABLE IF NOT EXISTS assignment(
  service_id INTEGER REFERENCES service(id) ON DELETE CASCADE, role TEXT,
  person_id INTEGER REFERENCES person(id) ON DELETE CASCADE, locked INTEGER DEFAULT 0,
  PRIMARY KEY(service_id, role));
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS outbox(
  id INTEGER PRIMARY KEY, person_id INTEGER, text TEXT, created TEXT DEFAULT CURRENT_TIMESTAMP,
  sent INTEGER DEFAULT 0);
-- motivo informado pela pessoa para as indisponibilidades de um mês
CREATE TABLE IF NOT EXISTS justificativa(
  person_id INTEGER REFERENCES person(id) ON DELETE CASCADE,
  month_id INTEGER REFERENCES month(id) ON DELETE CASCADE,
  texto TEXT NOT NULL, at TEXT,
  PRIMARY KEY(person_id, month_id));
-- regras criadas pelo responsável na tela Regras (ver rules.py)
CREATE TABLE IF NOT EXISTS regra_custom(
  id INTEGER PRIMARY KEY, kind TEXT NOT NULL, hard INTEGER DEFAULT 1, active INTEGER DEFAULT 1,
  person_a INTEGER REFERENCES person(id) ON DELETE CASCADE,
  person_b INTEGER REFERENCES person(id) ON DELETE CASCADE,
  weekday INTEGER, turn TEXT DEFAULT '', role TEXT DEFAULT '', n INTEGER,
  note TEXT DEFAULT '', created TEXT DEFAULT CURRENT_TIMESTAMP);
-- funções criadas pelo responsável (além das fixas em BAND_ROLES); só entram nos cultos marcados
CREATE TABLE IF NOT EXISTS funcao(
  name TEXT PRIMARY KEY COLLATE NOCASE, created TEXT DEFAULT CURRENT_TIMESTAMP,
  tipo TEXT NOT NULL DEFAULT 'outro',    -- instrumento | voz | outro (ver role_kinds)
  qtd INTEGER NOT NULL DEFAULT 1,        -- pessoas por culto (2 = vagas "Função (1)" e "Função (2)")
  padrao INTEGER NOT NULL DEFAULT 0);    -- 1 = já vem marcada nos cultos novos
-- trocas feitas pelo ministro do culto no link pessoal (histórico para o responsável)
CREATE TABLE IF NOT EXISTS troca(
  id INTEGER PRIMARY KEY,
  service_id INTEGER REFERENCES service(id) ON DELETE CASCADE,
  role TEXT NOT NULL,
  old_id INTEGER REFERENCES person(id) ON DELETE SET NULL,
  new_id INTEGER REFERENCES person(id) ON DELETE SET NULL,
  by_id INTEGER REFERENCES person(id) ON DELETE SET NULL,
  old_name TEXT, new_name TEXT, by_name TEXT, at TEXT);
-- avaliação entre colegas da banda de um culto (1 a 5 estrelas), por FUNÇÃO: quem ministrou e tocou
-- recebe uma nota para cada função. Só o responsável vê.
CREATE TABLE IF NOT EXISTS avaliacao(
  service_id INTEGER REFERENCES service(id) ON DELETE CASCADE,
  rater_id INTEGER REFERENCES person(id) ON DELETE CASCADE,
  rated_id INTEGER REFERENCES person(id) ON DELETE CASCADE,
  role TEXT NOT NULL DEFAULT '',
  stars INTEGER NOT NULL CHECK (stars BETWEEN 1 AND 5), at TEXT,
  PRIMARY KEY(service_id, rater_id, rated_id, role), CHECK (rater_id <> rated_id));
"""

def connect(path=None):
    path = path or DB_PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)
    c = sqlite3.connect(path)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    return c

def _migrate_avaliacao(c):
    """Versão antiga (uma nota por pessoa, sem função) -> uma nota por pessoa e função.
    A nota antiga vai para a primeira função da pessoa na banda daquele culto."""
    cols = [r[1] for r in c.execute("PRAGMA table_info(avaliacao)")]
    if not cols or "role" in cols:
        return
    c.executescript("""
      ALTER TABLE avaliacao RENAME TO avaliacao_v1;
      CREATE TABLE avaliacao(
        service_id INTEGER REFERENCES service(id) ON DELETE CASCADE,
        rater_id INTEGER REFERENCES person(id) ON DELETE CASCADE,
        rated_id INTEGER REFERENCES person(id) ON DELETE CASCADE,
        role TEXT NOT NULL DEFAULT '',
        stars INTEGER NOT NULL CHECK (stars BETWEEN 1 AND 5), at TEXT,
        PRIMARY KEY(service_id, rater_id, rated_id, role), CHECK (rater_id <> rated_id));""")
    order = {r: i for i, r in enumerate(BAND_ROLES)}
    for r in c.execute("SELECT * FROM avaliacao_v1").fetchall():
        roles = [x[0] for x in c.execute("SELECT role FROM assignment WHERE service_id=? AND person_id=?",
                                          (r["service_id"], r["rated_id"])) if x[0] not in AUTO_ROLES]
        roles.sort(key=lambda x: order.get(x, 99))
        c.execute("INSERT OR IGNORE INTO avaliacao VALUES(?,?,?,?,?,?)",
                  (r["service_id"], r["rater_id"], r["rated_id"], roles[0] if roles else "", r["stars"], r["at"]))
    c.execute("DROP TABLE avaliacao_v1")
    c.commit()

def _migrate_funcao(c):
    """Funções criadas antes de existir o tipo: sax/flauta/violino… = instrumento; o resto = outro."""
    cols = [r[1] for r in c.execute("PRAGMA table_info(funcao)")]
    if not cols or "tipo" in cols:
        return
    c.execute("ALTER TABLE funcao ADD COLUMN tipo TEXT NOT NULL DEFAULT 'outro'")
    for (name,) in c.execute("SELECT name FROM funcao").fetchall():
        n = name.lower()
        if any(w in n for w in ("sax", "flaut", "violin", "trompet", "trombon", "piano", "cello", "percuss", "gaita", "cajon")):
            c.execute("UPDATE funcao SET tipo='instrumento' WHERE name=?", (name,))
        elif any(w in n for w in ("vocal", "voz", "coral", "back")):
            c.execute("UPDATE funcao SET tipo='voz' WHERE name=?", (name,))
    c.commit()

def _migrate_funcao_qtd(c):
    cols = [r[1] for r in c.execute("PRAGMA table_info(funcao)")]
    if cols and "qtd" not in cols:
        c.execute("ALTER TABLE funcao ADD COLUMN qtd INTEGER NOT NULL DEFAULT 1")
    if cols and "padrao" not in cols:
        c.execute("ALTER TABLE funcao ADD COLUMN padrao INTEGER NOT NULL DEFAULT 0")
    c.commit()

def _migrate_foto(c):
    cols = [r[1] for r in c.execute("PRAGMA table_info(person)")]
    if cols and "foto" not in cols:
        c.execute("ALTER TABLE person ADD COLUMN foto TEXT DEFAULT ''")
        c.commit()

def init(path=None):
    c = connect(path)
    c.execute("PRAGMA foreign_keys=OFF")
    _migrate_avaliacao(c)
    _migrate_funcao(c)
    _migrate_funcao_qtd(c)
    _migrate_foto(c)
    c.execute("PRAGMA foreign_keys=ON")
    c.executescript(SCHEMA)
    for k, v in DEFAULT_SETTINGS.items():
        c.execute("INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)", (k, v))
    c.commit()
    return c

def custom_roles(c):
    """Funções criadas pelo responsável, na ordem em que foram criadas."""
    return [r[0] for r in c.execute("SELECT name FROM funcao ORDER BY created, rowid")]

def all_roles(c):
    """Todas as funções: as fixas (BAND_ROLES) e depois as criadas."""
    return BAND_ROLES + [r for r in custom_roles(c) if r not in BAND_ROLES]

ROLE_MAX = 30

def clean_role(name):
    """Normaliza o nome de uma função nova. Devolve (nome, erro)."""
    name = " ".join((name or "").replace(",", " ").replace("|", " ").split())
    if not name:
        return None, "Escreva o nome da função."
    if _SLOT.match(name):
        return None, "O nome não pode terminar com número entre parênteses, ex.: (2). Use “pessoas por culto”."
    if name.lower() in {r.lower() for r in AUTO_ROLES} or name.lower().startswith(("kids", "intercess")):
        return None, "Louvor Kids e Intercessão já são automáticos (não precisam ser criados)."
    if len(name) > ROLE_MAX:
        return None, f"O nome da função pode ter no máximo {ROLE_MAX} letras."
    return name[0].upper() + name[1:], None

def new_token():
    return secrets.token_urlsafe(9)

def get_settings(c):
    return {r["key"]: r["value"] for r in c.execute("SELECT * FROM settings")}
