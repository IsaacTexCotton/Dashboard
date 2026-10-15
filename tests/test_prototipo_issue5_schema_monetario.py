"""Protótipo SQLite descartável da Issue #5; não importa o código operacional."""
import sqlite3
import unittest

FATOS = (
    ("deposito_valor_centavos", "deposito", True),
    ("acordo_valor_centavos", "acordo", False),
    ("acordo_pago_centavos", "acordo", False),
    ("acordo_pendente_centavos", "acordo", True),
    ("promessa_prometido_centavos", "promessa", False),
    ("promessa_cumprido_centavos", "promessa", False),
    ("promessa_em_aberto_centavos", "promessa", True),
    ("promessa_quebrado_centavos", "promessa", False),
)
POSICAO = (
    ("recebido_periodo_centavos", True),
    ("a_vencer_centavos", False),
    ("vencido_centavos", False),
)
TIPOS = ("deposito", "acordo", "promessa", "contato")


def colunas(db, tabela):
    return {linha[1] for linha in db.execute(f"PRAGMA table_info({tabela})")}


def preparar_banco_descartavel():
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE fatos (id INTEGER PRIMARY KEY, tipo TEXT NOT NULL, valor REAL, valor_pago REAL, valor_aberto REAL, valor_quebrado REAL)")
    db.execute("CREATE TABLE acordos_posicao (id INTEGER PRIMARY KEY, capturado_em TEXT NOT NULL, recebido_periodo REAL, a_vencer REAL, vencido REAL)")
    db.executemany(
        "INSERT INTO fatos(id,tipo,valor,valor_pago,valor_aberto,valor_quebrado) VALUES(?,?,?,?,?,?)",
        [(1,"deposito",-12.34,None,None,None),(2,"acordo",100.0,25.0,75.0,None),(3,"promessa",50.0,20.0,30.0,5.0),(4,"contato",None,None,None,None)],
    )
    db.execute("INSERT INTO acordos_posicao(id,capturado_em,recebido_periodo,a_vencer,vencido) VALUES(1,'2026-01-01T10:00:00',-2.5,10.0,20.0)")
    return db


def adicionar_esquema_prototipo(db):
    """Simula ADD COLUMN e checagem de existência; não chama migrador real."""
    defs = {
        "fatos": [("monetario_fase", "TEXT NOT NULL DEFAULT 'legado' CHECK (monetario_fase IN ('legado','dual','conciliado'))")],
        "acordos_posicao": [("monetario_fase", "TEXT NOT NULL DEFAULT 'legado' CHECK (monetario_fase IN ('legado','dual','conciliado'))")],
    }
    for nome, tipo, negativo in FATOS:
        d = f"INTEGER CHECK ({nome} IS NULL OR typeof({nome})='integer') CHECK ({nome} IS NULL OR tipo='{tipo}')"
        if not negativo:
            d += f" CHECK ({nome} IS NULL OR {nome}>=0)"
        defs["fatos"].append((nome, d))
    for nome, negativo in POSICAO:
        d = f"INTEGER CHECK ({nome} IS NULL OR typeof({nome})='integer')"
        if not negativo:
            d += f" CHECK ({nome} IS NULL OR {nome}>=0)"
        defs["acordos_posicao"].append((nome, d))
    for tabela, itens in defs.items():
        existentes = colunas(db, tabela)
        for nome, definicao in itens:
            if nome not in existentes:
                db.execute(f"ALTER TABLE {tabela} ADD COLUMN {nome} {definicao}")
                existentes.add(nome)


def instalar_triggers_pos_conciliacao(db):
    ausentes = " OR ".join(f"(NEW.tipo='{tipo}' AND NEW.{nome} IS NULL)" for nome,tipo,_ in FATOS)
    for evento in ("INSERT", "UPDATE"):
        db.execute(
            f"CREATE TRIGGER fatos_obrigatorios_{evento.lower()} BEFORE {evento} ON fatos "
            f"WHEN NEW.monetario_fase IN ('dual','conciliado') AND ({ausentes}) "
            "BEGIN SELECT RAISE(ABORT,'metrica monetaria obrigatoria'); END"
        )
    ausentes_snapshot = " OR ".join(f"NEW.{nome} IS NULL" for nome,_ in POSICAO)
    for evento in ("INSERT", "UPDATE"):
        db.execute(
            f"CREATE TRIGGER posicao_obrigatoria_{evento.lower()} BEFORE {evento} ON acordos_posicao "
            f"WHEN NEW.monetario_fase IN ('dual','conciliado') AND ({ausentes_snapshot}) "
            "BEGIN SELECT RAISE(ABORT,'metrica de snapshot obrigatoria'); END"
        )


class TestPrototipoIssue5(unittest.TestCase):
    def setUp(self):
        self.db = preparar_banco_descartavel()
        self.real_antes = self.db.execute("SELECT id,valor,valor_pago,valor_aberto,valor_quebrado FROM fatos ORDER BY id").fetchall()
        self.snapshot_antes = self.db.execute("SELECT id,recebido_periodo,a_vencer,vencido FROM acordos_posicao ORDER BY id").fetchall()
        adicionar_esquema_prototipo(self.db)

    def tearDown(self):
        self.db.close()

    def test_add_column_aplicabilidade_historico_e_real_inalterado(self):
        self.assertEqual(self.db.execute("SELECT id,monetario_fase FROM fatos ORDER BY id").fetchall(), [(1,"legado"),(2,"legado"),(3,"legado"),(4,"legado")])
        for nome,_,_ in FATOS:
            self.assertTrue(all(r[0] is None for r in self.db.execute(f"SELECT {nome} FROM fatos")))
        self.assertEqual(self.db.execute("SELECT id,valor,valor_pago,valor_aberto,valor_quebrado FROM fatos ORDER BY id").fetchall(), self.real_antes)
        self.assertEqual(self.db.execute("SELECT id,recebido_periodo,a_vencer,vencido FROM acordos_posicao ORDER BY id").fetchall(), self.snapshot_antes)
        self.assertEqual(self.db.execute("SELECT id,monetario_fase FROM acordos_posicao").fetchall(), [(1,"legado")])

    def test_cada_metrica_aplica_so_ao_tipo_correspondente_e_zero_nao_e_null(self):
        for nome,tipo,_ in FATOS:
            with self.subTest(metrica=nome):
                self.db.execute(f"INSERT INTO fatos(tipo,{nome}) VALUES(?,0)", (tipo,))
                self.assertEqual(self.db.execute(f"SELECT {nome} FROM fatos WHERE id=last_insert_rowid()").fetchone()[0], 0)
                outro = next(t for t in TIPOS if t != tipo)
                with self.assertRaises(sqlite3.IntegrityError):
                    self.db.execute(f"INSERT INTO fatos(tipo,{nome}) VALUES(?,1)", (outro,))
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM fatos WHERE tipo='contato' AND " + " AND ".join(f"{c} IS NULL" for c,_,_ in FATOS)).fetchone()[0], 1)
        self.db.execute("INSERT INTO fatos(tipo,acordo_valor_centavos,monetario_fase) VALUES('acordo',NULL,'legado')")
        self.assertIsNone(self.db.execute("SELECT acordo_valor_centavos FROM fatos WHERE id=last_insert_rowid()").fetchone()[0])

    def test_tipo_estrito_e_limite_da_afinidade_de_texto(self):
        for valor in (12.5, "abc"):
            with self.subTest(valor=valor), self.assertRaises(sqlite3.IntegrityError):
                self.db.execute("INSERT INTO fatos(tipo,acordo_valor_centavos) VALUES('acordo',?)", (valor,))
        # SQLite converte '123' para INTEGER antes do CHECK. O parser deve validar o token original.
        self.db.execute("INSERT INTO fatos(tipo,acordo_valor_centavos) VALUES('acordo','123')")
        self.assertEqual(self.db.execute("SELECT acordo_valor_centavos,typeof(acordo_valor_centavos) FROM fatos WHERE id=last_insert_rowid()").fetchone(), (123,"integer"))
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute("INSERT INTO fatos(tipo,monetario_fase) VALUES('contato','fase-invalida')")

    def test_sinais_provisorios_por_metrica(self):
        for nome,tipo,negativo in FATOS:
            with self.subTest(metrica=nome):
                if negativo:
                    self.db.execute(f"INSERT INTO fatos(tipo,{nome}) VALUES(?,-1)", (tipo,))
                else:
                    with self.assertRaises(sqlite3.IntegrityError):
                        self.db.execute(f"INSERT INTO fatos(tipo,{nome}) VALUES(?,-1)", (tipo,))
        for nome,negativo in POSICAO:
            with self.subTest(metrica=nome):
                sql = f"INSERT INTO acordos_posicao(capturado_em,{nome}) VALUES('2026-02-01T10:00:00',-1)"
                if negativo:
                    self.db.execute(sql)
                else:
                    with self.assertRaises(sqlite3.IntegrityError):
                        self.db.execute(sql)

    def test_esquema_idempotente(self):
        before = {t: colunas(self.db,t) for t in ("fatos","acordos_posicao")}
        adicionar_esquema_prototipo(self.db)
        self.assertEqual(before, {t: colunas(self.db,t) for t in before})

    def test_falha_no_meio_reverte_ddl_e_preserva_real(self):
        before = colunas(self.db,"fatos")
        self.db.commit()
        self.db.execute("BEGIN")
        self.db.execute("ALTER TABLE fatos ADD COLUMN temporaria_prototipo INTEGER CHECK(temporaria_prototipo IS NULL OR typeof(temporaria_prototipo)='integer')")
        with self.assertRaises(sqlite3.DatabaseError):
            self.db.execute("ALTER TABLE fatos ADD COLUMN forcar_falha INTEGER NOT NULL DEFAULT 0 CHECK(forcar_falha>0)")
        self.db.rollback()
        self.assertEqual(colunas(self.db,"fatos"), before)
        self.assertEqual(self.db.execute("SELECT id,valor,valor_pago,valor_aberto,valor_quebrado FROM fatos ORDER BY id").fetchall(), self.real_antes)

    def test_triggers_obrigatorios_instalados_somente_apos_fixture_conciliada(self):
        por_tipo = {
            "deposito": {"deposito_valor_centavos":0},
            "acordo": {"acordo_valor_centavos":0,"acordo_pago_centavos":0,"acordo_pendente_centavos":0},
            "promessa": {"promessa_prometido_centavos":0,"promessa_cumprido_centavos":0,"promessa_em_aberto_centavos":0,"promessa_quebrado_centavos":0},
            "contato": {},
        }
        for tipo, valores in por_tipo.items():
            assignments = [f"{nome}=?" for nome in valores] + ["monetario_fase='conciliado'"]
            self.db.execute(f"UPDATE fatos SET {','.join(assignments)} WHERE tipo=?", [*valores.values(),tipo])
        self.db.execute("UPDATE acordos_posicao SET recebido_periodo_centavos=0,a_vencer_centavos=0,vencido_centavos=0,monetario_fase='conciliado'")
        instalar_triggers_pos_conciliacao(self.db)
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute("INSERT INTO fatos(tipo,monetario_fase,acordo_valor_centavos) VALUES('acordo','dual',NULL)")
        self.db.execute("INSERT INTO fatos(tipo,monetario_fase) VALUES('contato','dual')")
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute("INSERT INTO acordos_posicao(capturado_em,monetario_fase,recebido_periodo_centavos,a_vencer_centavos) VALUES('2026-03-01T10:00:00','dual',0,0)")


if __name__ == "__main__":
    unittest.main(verbosity=2)
