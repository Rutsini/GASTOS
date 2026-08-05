import os
import tempfile
import unittest

import db as root_db


class MovimientosServiceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root_db.DATA_DIR = self.tmp.name
        root_db.BACKUP_DIR = os.path.join(self.tmp.name, "backups")
        root_db.DB_PATH = os.path.join(self.tmp.name, "gastos_test.db")
        root_db._BACKUP_REALIZADO = False
        root_db._MIGRACION_INFORMADA = False
        os.makedirs(root_db.BACKUP_DIR, exist_ok=True)

        from app.services import movimientos_service, tarjetas_service

        self.movimientos_service = movimientos_service
        self.tarjetas_service = tarjetas_service
        self.tarjetas_service.asegurar_modulo_tarjetas()
        self._crear_categoria()

    def tearDown(self):
        self.tmp.cleanup()

    def _crear_categoria(self):
        with root_db.get_conn() as conn:
            conn.execute("INSERT INTO categorias (nombre, tipo, activa) VALUES ('Servicios', 'gasto', 1)")
            cat_id = conn.execute("SELECT id FROM categorias WHERE nombre = 'Servicios'").fetchone()["id"]
            conn.execute("INSERT INTO subcategorias (nombre, activa) VALUES ('Streaming', 1)")
            sub_id = conn.execute("SELECT id FROM subcategorias WHERE nombre = 'Streaming'").fetchone()["id"]
            conn.execute(
                "INSERT INTO categoria_subcategoria (categoria_id, subcategoria_id) VALUES (?, ?)",
                (cat_id, sub_id),
            )
            conn.commit()
        self.subcategoria_id = sub_id

    def _tarjeta(self):
        return self.tarjetas_service.crear_tarjeta({
            "nombre": "Visa Galicia",
            "banco": "Galicia",
            "tipo": "Visa",
            "ultimos_cuatro": "1234",
            "activa": "1",
        })

    def _compra(self, tarjeta_id):
        return self.tarjetas_service.crear_compra_en_cuotas(tarjeta_id, {
            "descripcion": "Monitor",
            "comercio": "Tienda",
            "monto_original": "1200,00",
            "cantidad_cuotas": "1",
            "fecha_compra": "2026-07-01",
            "fecha_inicio": "2026-07-01",
            "primer_vencimiento": "2026-07-10",
            "categoria": "Servicios",
            "subcategoria_id": str(self.subcategoria_id),
        })

    def _suscripcion(self, tarjeta_id):
        return self.tarjetas_service.crear_suscripcion(tarjeta_id, {
            "descripcion": "Netflix",
            "comercio": "Streaming",
            "monto_original": "1000,00",
            "fecha_inicio": "2026-08-22",
            "categoria": "Servicios",
            "subcategoria_id": str(self.subcategoria_id),
        })

    def _movimiento_simple(self, tx_hash="mov-simple", tarjeta_id=None):
        with root_db.get_conn() as conn:
            cur = conn.execute("""
                INSERT INTO movimientos (
                    tx_hash, archivo, linea, fecha, descripcion, monto_centavos, monto_raw,
                    categoria, subcategoria_id, clasificacion_origen, clasificacion_bloqueada,
                    tarjeta_id, generado_desde_tarjeta, anulado
                )
                VALUES (?, 'manual', NULL, '2026-07-01', 'Movimiento simple', -10000, '-100,00',
                        'Servicios', ?, 'manual', 1, ?, ?, 0)
            """, (
                tx_hash,
                self.subcategoria_id,
                tarjeta_id,
                1 if tarjeta_id else 0,
            ))
            conn.commit()
            return cur.lastrowid

    def _assert_integridad_ok(self):
        with root_db.get_conn() as conn:
            self.assertEqual(conn.execute("PRAGMA foreign_keys").fetchone()[0], 1)
            self.assertEqual(conn.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_elimina_movimiento_sin_relaciones(self):
        mov_id = self._movimiento_simple()

        resultado = self.movimientos_service.eliminar_movimientos([str(mov_id)])

        self.assertEqual(resultado["eliminados"], 1)
        with root_db.get_conn() as conn:
            self.assertIsNone(conn.execute("SELECT 1 FROM movimientos WHERE id = ?", (mov_id,)).fetchone())
        self._assert_integridad_ok()

    def test_elimina_movimiento_de_cuota_y_la_reabre(self):
        tarjeta_id = self._tarjeta()
        compra_id = self._compra(tarjeta_id)
        mov_id = self.tarjetas_service.pagar_cuota(compra_id=compra_id, fecha_pago="2026-07-15")

        resultado = self.movimientos_service.eliminar_movimientos([str(mov_id)])

        self.assertEqual(resultado["eliminados"], 1)
        self.assertEqual(resultado["cuotas_reabiertas"], 1)
        with root_db.get_conn() as conn:
            cuota = conn.execute("SELECT estado, fecha_pago, movimiento_id FROM cuotas_tarjeta WHERE compra_tarjeta_id = ?", (compra_id,)).fetchone()
            compra = conn.execute("SELECT estado FROM compras_tarjeta WHERE id = ?", (compra_id,)).fetchone()
            historial = conn.execute("SELECT COUNT(*) AS total FROM historial_pagos_tarjeta WHERE movimiento_id = ?", (mov_id,)).fetchone()
            movimiento = conn.execute("SELECT 1 FROM movimientos WHERE id = ?", (mov_id,)).fetchone()

        self.assertEqual(cuota["estado"], "pendiente")
        self.assertIsNone(cuota["fecha_pago"])
        self.assertIsNone(cuota["movimiento_id"])
        self.assertEqual(compra["estado"], "activa")
        self.assertEqual(historial["total"], 0)
        self.assertIsNone(movimiento)
        self._assert_integridad_ok()

    def test_elimina_movimiento_de_suscripcion_sin_eliminar_suscripcion(self):
        tarjeta_id = self._tarjeta()
        suscripcion_id = self._suscripcion(tarjeta_id)
        pago = self.tarjetas_service.pagar_suscripcion(suscripcion_id, "2026-08-10")
        mov_id = pago["movimiento_id"]

        resultado = self.movimientos_service.eliminar_movimientos([str(mov_id)])

        self.assertEqual(resultado["eliminados"], 1)
        self.assertEqual(resultado["cobros_suscripcion_eliminados"], 1)
        with root_db.get_conn() as conn:
            suscripcion = conn.execute(
                "SELECT estado, fecha_proximo_cobro FROM tarjeta_suscripciones WHERE id = ?",
                (suscripcion_id,),
            ).fetchone()
            cobros = conn.execute(
                "SELECT COUNT(*) AS total FROM tarjeta_suscripcion_cobros WHERE suscripcion_id = ?",
                (suscripcion_id,),
            ).fetchone()
            movimiento = conn.execute("SELECT 1 FROM movimientos WHERE id = ?", (mov_id,)).fetchone()

        self.assertEqual(suscripcion["estado"], "activa")
        self.assertEqual(suscripcion["fecha_proximo_cobro"], "2026-08-22")
        self.assertEqual(cobros["total"], 0)
        self.assertIsNone(movimiento)
        self._assert_integridad_ok()

    def test_elimina_movimiento_relacionado_solo_con_tarjeta(self):
        tarjeta_id = self._tarjeta()
        mov_id = self._movimiento_simple("mov-tarjeta", tarjeta_id=tarjeta_id)

        resultado = self.movimientos_service.eliminar_movimientos([str(mov_id)])

        self.assertEqual(resultado["eliminados"], 1)
        with root_db.get_conn() as conn:
            tarjeta = conn.execute("SELECT id FROM tarjetas WHERE id = ?", (tarjeta_id,)).fetchone()
            movimiento = conn.execute("SELECT 1 FROM movimientos WHERE id = ?", (mov_id,)).fetchone()
        self.assertIsNotNone(tarjeta)
        self.assertIsNone(movimiento)
        self._assert_integridad_ok()

    def test_elimina_varios_movimientos_con_repetidos_y_no_existentes(self):
        tarjeta_id = self._tarjeta()
        compra_id = self._compra(tarjeta_id)
        mov_simple = self._movimiento_simple()
        mov_cuota = self.tarjetas_service.pagar_cuota(compra_id=compra_id, fecha_pago="2026-07-15")
        suscripcion_id = self._suscripcion(tarjeta_id)
        mov_suscripcion = self.tarjetas_service.pagar_suscripcion(suscripcion_id, "2026-08-10")["movimiento_id"]

        resultado = self.movimientos_service.eliminar_movimientos([
            str(mov_simple),
            str(mov_cuota),
            str(mov_cuota),
            str(mov_suscripcion),
            "999999",
        ])

        self.assertEqual(resultado["solicitados"], 4)
        self.assertEqual(resultado["eliminados"], 3)
        self.assertEqual(resultado["no_encontrados"], 1)
        self.assertEqual(resultado["cuotas_reabiertas"], 1)
        self.assertEqual(resultado["cobros_suscripcion_eliminados"], 1)
        with root_db.get_conn() as conn:
            restantes = conn.execute(
                "SELECT COUNT(*) AS total FROM movimientos WHERE id IN (?, ?, ?)",
                (mov_simple, mov_cuota, mov_suscripcion),
            ).fetchone()["total"]
        self.assertEqual(restantes, 0)
        self._assert_integridad_ok()

    def test_lista_vacia_o_ids_invalidos(self):
        with self.assertRaises(self.movimientos_service.MovimientosError):
            self.movimientos_service.eliminar_movimientos([])
        with self.assertRaises(self.movimientos_service.MovimientosError):
            self.movimientos_service.eliminar_movimientos(["abc", "1"])
        self._assert_integridad_ok()

    def test_rollback_ante_error(self):
        tarjeta_id = self._tarjeta()
        compra_id = self._compra(tarjeta_id)
        mov_id = self.tarjetas_service.pagar_cuota(compra_id=compra_id, fecha_pago="2026-07-15")
        original = self.movimientos_service.repo.eliminar_movimientos_por_ids

        def fallar(*args, **kwargs):
            raise RuntimeError("fallo simulado")

        self.movimientos_service.repo.eliminar_movimientos_por_ids = fallar
        try:
            with self.assertRaises(RuntimeError):
                self.movimientos_service.eliminar_movimientos([str(mov_id)])
        finally:
            self.movimientos_service.repo.eliminar_movimientos_por_ids = original

        with root_db.get_conn() as conn:
            cuota = conn.execute("SELECT estado, movimiento_id FROM cuotas_tarjeta WHERE compra_tarjeta_id = ?", (compra_id,)).fetchone()
            historial = conn.execute("SELECT COUNT(*) AS total FROM historial_pagos_tarjeta WHERE movimiento_id = ?", (mov_id,)).fetchone()
            movimiento = conn.execute("SELECT 1 FROM movimientos WHERE id = ?", (mov_id,)).fetchone()

        self.assertEqual(cuota["estado"], "pagada")
        self.assertEqual(cuota["movimiento_id"], mov_id)
        self.assertEqual(historial["total"], 1)
        self.assertIsNotNone(movimiento)
        self._assert_integridad_ok()


if __name__ == "__main__":
    unittest.main()
