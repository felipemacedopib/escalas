"""Cadastro inicial da equipe (baseado nas escalas de nov/dez 2026). Edite tudo pelo painel depois."""
import db

CAP = {
 'Bateria': ['Isack','Kawan','Jan','Juninho'],
 'Baixo': ['Gabriel','Vitor','Edon','Kawan'],
 'Guitarra': ['Felipe Carneiro','Lucas Weretick','Ian','Alan','Aguinaldo'],
 'Violão': ['Elias','Everson','Felipe Macedo','Jean','Guilherme'],
 'Teclado': ['Juninho','Paulinho','Márcio','Kessy','Izilbert','Mateus'],
 'Soprano': ['Gisseli','Bruna','Vanusa','Cris','Cida','Dani','Aline'],
 'Contralto': ['Jeise','Vitória','Rafaela','Caroline','Márcia','Brenda'],
 'Tenor': ['Beethoven','Felipe Macedo','Ozias','Lucas Luan','Danilo','Beto'],
 'Ministro': ['Bluma','Gisseli','Beethoven','Bruna','Jeise','Brenda','Alicia','Felipe Macedo'],
}
NOT_TUE_FRI = ['Danilo','Vitor','Izilbert','Ian','Beethoven','Isack','Vitória','Jeise','Elias','Bluma',
               'Mateus','Alicia','Kessy','Aline','Dani']
NOT_SAT = ['Kessy','Aline','Alicia','Mateus']
NOT_FRI = ['Isack','Vitor','Gabriel','Ian','Lucas Weretick','Vitória']
NOT_THU = ['Gisseli']
SUNDAY_ONLY = ['Jeise','Elias','Jan']
REST_WEEKEND = ['Vitor','Gabriel','Kawan']
PAIRS = [('Rafaela','Vanusa',1),('Vanusa','Lucas Weretick',2),('Rafaela','Lucas Weretick',1),
         ('Felipe Carneiro','Brenda',3),('Alicia','Mateus',3),('Izilbert','Ian',3),('Isack','Vitória',3),
         ('Kessy','Aline',3),('Bluma','Ozias',3),('Felipe Macedo','Cris',3),('Juninho','Cida',3),
         ('Jeise','Elias',3)]
EXTRA = ['Cida']   # já em Soprano

def run(path=None):
    c = db.init(path)
    names = sorted({n for v in CAP.values() for n in v})
    for n in names:
        wd = set()
        if n in NOT_TUE_FRI: wd |= {1, 4}
        if n in NOT_SAT: wd.add(5)
        if n in NOT_FRI: wd.add(4)
        if n in NOT_THU: wd.add(3)
        c.execute("INSERT OR IGNORE INTO person(name,token,sunday_only,rest_weekend,blocked_wd) VALUES(?,?,?,?,?)",
                  (n, db.new_token(), int(n in SUNDAY_ONLY), int(n in REST_WEEKEND),
                   ",".join(map(str, sorted(wd)))))
    ids = {r["name"]: r["id"] for r in c.execute("SELECT id,name FROM person")}
    for role, ns in CAP.items():
        for n in ns:
            c.execute("INSERT OR IGNORE INTO person_role VALUES(?,?)", (ids[n], role))
    for a, b, w in PAIRS:
        if not c.execute("SELECT 1 FROM pair WHERE a=? AND b=?", (ids[a], ids[b])).fetchone():
            c.execute("INSERT INTO pair(a,b,weight) VALUES(?,?,?)", (ids[a], ids[b], w))
    c.commit()
    return c

if __name__ == "__main__":
    run()
    print("Equipe cadastrada.")
