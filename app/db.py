"""Banco do Perfilaí: SQLite no volume /data. Hora em epoch (s)."""
from __future__ import annotations

import os
import sqlite3
import uuid
import threading
import time
from contextlib import contextmanager

ESQUEMA = """
CREATE TABLE IF NOT EXISTS usuarios (
  id INTEGER PRIMARY KEY, email TEXT UNIQUE NOT NULL, criado REAL NOT NULL,
  plano TEXT NOT NULL DEFAULT 'nenhum', ativo_ate REAL NOT NULL DEFAULT 0, pedido TEXT
);
CREATE TABLE IF NOT EXISTS codigos (email TEXT PRIMARY KEY, hash TEXT NOT NULL, expira REAL NOT NULL, tentativas INTEGER NOT NULL DEFAULT 0, enviado REAL NOT NULL);
CREATE TABLE IF NOT EXISTS sessoes (hash TEXT PRIMARY KEY, usuario INTEGER NOT NULL, expira REAL NOT NULL);
CREATE TABLE IF NOT EXISTS planos (
  id TEXT PRIMARY KEY, usuario INTEGER NOT NULL,
  entrada TEXT NOT NULL,                 -- JSON: arroba, objetivo, nicho, produto, cor, prints (nomes)
  estado TEXT NOT NULL DEFAULT 'fila',   -- fila | rodando | pronto | erro
  etapa TEXT NOT NULL DEFAULT '', progresso REAL NOT NULL DEFAULT 0,
  resultado TEXT, erro TEXT, criado REAL NOT NULL, fim REAL
);
CREATE INDEX IF NOT EXISTS planos_usuario ON planos(usuario, criado);
CREATE TABLE IF NOT EXISTS eventos_cakto (id TEXT PRIMARY KEY, recebido REAL NOT NULL, corpo TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS posts (id TEXT PRIMARY KEY, usuario INTEGER NOT NULL, plano TEXT NOT NULL, arroba TEXT, dia TEXT NOT NULL, gancho TEXT, legenda TEXT,
  arquivo TEXT NOT NULL, rota TEXT, criado REAL NOT NULL);
CREATE TABLE IF NOT EXISTS assinaturas (usuario INTEGER NOT NULL, marca TEXT NOT NULL, plano TEXT NOT NULL, ativo_ate REAL NOT NULL, pedido TEXT,
  PRIMARY KEY (usuario, marca));
CREATE TABLE IF NOT EXISTS imagens (id TEXT PRIMARY KEY, usuario INTEGER NOT NULL, tipo TEXT NOT NULL, arquivos TEXT NOT NULL, rota TEXT, criado REAL NOT NULL);
CREATE TABLE IF NOT EXISTS conexoes (usuario INTEGER NOT NULL, marca TEXT NOT NULL, estado TEXT NOT NULL, login_id TEXT, semana REAL NOT NULL,
  rotulo TEXT NOT NULL DEFAULT '', aplicada REAL, criado REAL NOT NULL, PRIMARY KEY (usuario, marca));
CREATE TABLE IF NOT EXISTS kits (id TEXT PRIMARY KEY, usuario INTEGER NOT NULL, arquivo TEXT NOT NULL, tipo TEXT NOT NULL, criado REAL NOT NULL);
"""


class BancoSQLite:
    def __init__(self, caminho: str):
        self._trava = threading.Lock()
        self.con = sqlite3.connect(caminho, check_same_thread=False, isolation_level=None)
        self.con.row_factory = sqlite3.Row
        self.con.execute("PRAGMA journal_mode=WAL")
        self.con.executescript(ESQUEMA)

    @contextmanager
    def tx(self):
        with self._trava:
            self.con.execute("BEGIN IMMEDIATE")
            try:
                yield self.con
                self.con.execute("COMMIT")
            except BaseException:
                self.con.execute("ROLLBACK")
                raise

    def um(self, sql: str, args=()):
        with self._trava:
            r = self.con.execute(sql, args).fetchone()
        return dict(r) if r else None

    def todos(self, sql: str, args=()):
        with self._trava:
            return [dict(r) for r in self.con.execute(sql, args).fetchall()]

    def exec(self, sql: str, args=()):
        with self._trava:
            return self.con.execute(sql, args)


def agora() -> float:
    return time.time()


def Banco(caminho: str):
    """Postgres central (banco `produtos`, schema do produto) quando PRODUTOS_DATABASE_URL existe; senão o SQLite de antes
    (plano de volta). Spec 57, seção 8. PRODUTOS_SCHEMA_TESTE=1 dá um schema novo por instância (testes isolados)."""
    dsn = os.environ.get("PRODUTOS_DATABASE_URL")
    if not dsn:
        return BancoSQLite(caminho)
    from produtos_core.banco_pg import Banco as BancoPG
    schema = os.environ.get("PRODUTOS_SCHEMA", "perfilai")
    if os.environ.get("PRODUTOS_SCHEMA_TESTE"):
        schema = "teste_" + uuid.uuid4().hex[:10]
    return BancoPG(dsn, schema, ESQUEMA)
