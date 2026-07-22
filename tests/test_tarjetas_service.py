import os
import tempfile
import unittest

import db as root_db


class TarjetasServiceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root_db.DATA_DIR = self.tmp.name
        root_db.BACKUP_DIR = os.path.join(self.tmp.name, "backups")
        root_db.DB_PATH = os.path.join(self.tmp.name, "gastos_test.db")
        root_db._BACKUP_REALIZADO = False
        root_db._MIGRACION_INFORMADA = False
        os.makedirs(root_db.BACKUP_DIR, exist_ok=True)

        from app.services import tarjetas_service

        self.service = tarjetas_service
        self.service.asegurar_modulo_tarjetas()
        self._crear_categoria()

    def tearDown(self):
        self.tmp.cleanup()

    def _crear_categoria(self):
        with root_db.get_conn() as conn:
            conn.execute("INSERT INTO categorias (nombre, tipo, activa) VALUES ('Electronica', 'gasto', 1)")
            cat_id = conn.execute("SELECT id FROM categorias WHERE nombre = 'Electronica'").fetchone()["id"]
            conn.execute("INSERT INTO subcategorias (nombre, activa) VALUES ('Celulares', 1)")
            sub_id = conn.execute("SELECT id FROM subcategorias WHERE nombre = 'Celulares'").fetchone()["id"]
            conn.execute(
                "INSERT INTO categoria_subcategoria (categoria_id, subcategoria_id) VALUES (?, ?)",
                (cat_id, sub_id),
            )
            conn.commit()
        self.subcategoria_id = sub_id

    def _tarjeta(self):
        return self.service.crear_tarjeta({
            "nombre": "Visa Galicia",
            "banco": "Galicia",
            "tipo": "Visa",
            "ultimos_cuatro": "1234",
            "activa": "1",
        })

    def _compra(self, tarjeta_id, cuotas="3", monto="100,00"):
        return self.service.crear_compra_en_cuotas(tarjeta_id, {
            "descripcion": "Celular",
            "comercio": "Tienda",
            "monto_original": monto,
            "cantidad_cuotas": cuotas,
            "fecha_compra": "2026-07-01",
            "fecha_inicio": "2026-07-01",
            "primer_vencimiento": "2026-07-10",
            "categoria": "Electronica",
            "subcategoria_id": str(self.subcategoria_id),
        })

    def test_crea_tarjeta_compra_y_cuotas_con_redondeo(self):
        tarjeta_id = self._tarjeta()
        compra_id = self._compra(tarjeta_id)

        with root_db.get_conn() as conn:
            cuotas = conn.execute(
                "SELECT numero_cuota, importe_centavos FROM cuotas_tarjeta WHERE compra_tarjeta_id = ? ORDER BY numero_cuota",
                (compra_id,),
            ).fetchall()

        self.assertEqual([c["importe_centavos"] for c in cuotas], [3333, 3333, 3334])

    def test_paga_cuota_crea_movimiento_y_evita_duplicado(self):
        tarjeta_id = self._tarjeta()
        compra_id = self._compra(tarjeta_id, cuotas="1", monto="50000,00")
        with root_db.get_conn() as conn:
            cuota_id = conn.execute("SELECT id FROM cuotas_tarjeta WHERE compra_tarjeta_id = ?", (compra_id,)).fetchone()["id"]

        movimiento_id = self.service.pagar_cuota(cuota_id=cuota_id, fecha_pago="2026-07-15")
        self.assertTrue(movimiento_id)
        with self.assertRaises(self.service.TarjetasError):
            self.service.pagar_cuota(cuota_id=cuota_id, fecha_pago="2026-07-15")

        with root_db.get_conn() as conn:
            movimiento = conn.execute("SELECT * FROM movimientos WHERE id = ?", (movimiento_id,)).fetchone()
            cuota = conn.execute("SELECT estado, movimiento_id FROM cuotas_tarjeta WHERE id = ?", (cuota_id,)).fetchone()
            compra = conn.execute("SELECT estado FROM compras_tarjeta WHERE id = ?", (compra_id,)).fetchone()

        self.assertEqual(movimiento["monto_centavos"], -5000000)
        self.assertEqual(movimiento["generado_desde_tarjeta"], 1)
        self.assertEqual(cuota["estado"], "pagada")
        self.assertEqual(cuota["movimiento_id"], movimiento_id)
        self.assertEqual(compra["estado"], "finalizada")

    def test_paga_periodo_y_anula_pago(self):
        tarjeta_id = self._tarjeta()
        compra_id = self._compra(tarjeta_id, cuotas="2", monto="200,00")

        movimientos = self.service.pagar_cuotas_periodo(tarjeta_id, "2026-07", "2026-07-20")
        self.assertEqual(len(movimientos), 1)

        with root_db.get_conn() as conn:
            cuota = conn.execute(
                "SELECT id, estado, movimiento_id FROM cuotas_tarjeta WHERE compra_tarjeta_id = ? AND numero_cuota = 1",
                (compra_id,),
            ).fetchone()
        self.assertEqual(cuota["estado"], "pagada")

        self.service.anular_pago(cuota["id"], fecha_anulacion="2026-07-21")
        with root_db.get_conn() as conn:
            cuota_reabierta = conn.execute("SELECT estado, movimiento_id FROM cuotas_tarjeta WHERE id = ?", (cuota["id"],)).fetchone()
            movimiento = conn.execute("SELECT anulado FROM movimientos WHERE id = ?", (cuota["movimiento_id"],)).fetchone()
            historial = conn.execute("SELECT tipo_operacion FROM historial_pagos_tarjeta ORDER BY id").fetchall()

        self.assertEqual(cuota_reabierta["estado"], "pendiente")
        self.assertIsNone(cuota_reabierta["movimiento_id"])
        self.assertEqual(movimiento["anulado"], 1)
        self.assertEqual([h["tipo_operacion"] for h in historial], ["pago", "anulacion"])


if __name__ == "__main__":
    unittest.main()
