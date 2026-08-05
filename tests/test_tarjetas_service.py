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

    def _suscripcion(self, tarjeta_id, nombre="Netflix", monto="1000,00", fecha_inicio="2026-07-05"):
        return self.service.crear_suscripcion(tarjeta_id, {
            "descripcion": nombre,
            "comercio": "Streaming",
            "monto_original": monto,
            "fecha_inicio": fecha_inicio,
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

    def test_suscripcion_genera_cobros_mensuales_sin_duplicar(self):
        tarjeta_id = self._tarjeta()
        suscripcion_id = self._suscripcion(tarjeta_id, fecha_inicio="2026-07-05")

        movimientos = self.service.generar_cobros_pendientes(tarjeta_id, "2026-09-30")
        self.assertEqual(len(movimientos), 3)
        self.assertEqual(self.service.generar_cobros_pendientes(tarjeta_id, "2026-09-30"), [])

        with root_db.get_conn() as conn:
            cobros = conn.execute(
                "SELECT periodo, monto_centavos FROM tarjeta_suscripcion_cobros WHERE suscripcion_id = ? ORDER BY periodo",
                (suscripcion_id,),
            ).fetchall()
            movimientos_db = conn.execute(
                "SELECT descripcion, monto_centavos, tarjeta_id, suscripcion_tarjeta_id FROM movimientos WHERE suscripcion_tarjeta_id = ? ORDER BY fecha",
                (suscripcion_id,),
            ).fetchall()
            suscripcion = conn.execute(
                "SELECT fecha_proximo_cobro FROM tarjeta_suscripciones WHERE id = ?",
                (suscripcion_id,),
            ).fetchone()

        self.assertEqual([c["periodo"] for c in cobros], ["2026-07", "2026-08", "2026-09"])
        self.assertEqual([c["monto_centavos"] for c in cobros], [100000, 100000, 100000])
        self.assertEqual([m["monto_centavos"] for m in movimientos_db], [-100000, -100000, -100000])
        self.assertEqual(movimientos_db[0]["descripcion"], "Suscripcion - Netflix")
        self.assertEqual(movimientos_db[0]["tarjeta_id"], tarjeta_id)
        self.assertEqual(movimientos_db[0]["suscripcion_tarjeta_id"], suscripcion_id)
        self.assertEqual(suscripcion["fecha_proximo_cobro"], "2026-10-05")

    def test_editar_monto_aplica_solo_a_periodos_futuros(self):
        tarjeta_id = self._tarjeta()
        suscripcion_id = self._suscripcion(tarjeta_id, fecha_inicio="2026-07-05")
        self.service.generar_cobros_pendientes(tarjeta_id, "2026-07-31")

        resultado = self.service.editar_monto_suscripcion(suscripcion_id, {"nuevo_monto": "1500,00"})
        self.assertEqual(resultado["periodo_desde"], "2026-08")
        self.service.generar_cobros_pendientes(tarjeta_id, "2026-09-30")

        with root_db.get_conn() as conn:
            cobros = conn.execute(
                "SELECT periodo, monto_centavos FROM tarjeta_suscripcion_cobros WHERE suscripcion_id = ? ORDER BY periodo",
                (suscripcion_id,),
            ).fetchall()
            historial = conn.execute(
                "SELECT monto_anterior_centavos, monto_nuevo_centavos, periodo_desde FROM tarjeta_suscripcion_historial_montos WHERE suscripcion_id = ?",
                (suscripcion_id,),
            ).fetchone()
            suscripcion = conn.execute(
                "SELECT monto_centavos, fecha_inicio, fecha_proximo_cobro FROM tarjeta_suscripciones WHERE id = ?",
                (suscripcion_id,),
            ).fetchone()

        self.assertEqual([(c["periodo"], c["monto_centavos"]) for c in cobros], [
            ("2026-07", 100000),
            ("2026-08", 150000),
            ("2026-09", 150000),
        ])
        self.assertEqual(historial["monto_anterior_centavos"], 100000)
        self.assertEqual(historial["monto_nuevo_centavos"], 150000)
        self.assertEqual(historial["periodo_desde"], "2026-08")
        self.assertEqual(suscripcion["monto_centavos"], 150000)
        self.assertEqual(suscripcion["fecha_inicio"], "2026-07-05")
        self.assertEqual(suscripcion["fecha_proximo_cobro"], "2026-10-05")

    def test_editar_monto_valida_importe_y_periodo(self):
        tarjeta_id = self._tarjeta()
        suscripcion_id = self._suscripcion(tarjeta_id, fecha_inicio="2026-07-05")
        self.service.generar_cobros_pendientes(tarjeta_id, "2026-07-31")

        with self.assertRaises(self.service.TarjetasError):
            self.service.editar_monto_suscripcion(suscripcion_id, {"nuevo_monto": "1000,00"})
        with self.assertRaises(self.service.TarjetasError):
            self.service.editar_monto_suscripcion(suscripcion_id, {"nuevo_monto": "0"})
        with self.assertRaises(self.service.TarjetasError):
            self.service.editar_monto_suscripcion(suscripcion_id, {"nuevo_monto": "1200,00", "periodo_desde": "2026-07"})

    def test_pago_manual_anticipado_evitar_duplicado_automatico(self):
        tarjeta_id = self._tarjeta()
        suscripcion_id = self._suscripcion(tarjeta_id, fecha_inicio="2026-08-22")

        pago = self.service.pagar_suscripcion(suscripcion_id, "2026-08-10")
        self.assertEqual(pago["periodo"], "2026-08")
        self.assertEqual(pago["monto_centavos"], 100000)
        self.assertEqual(self.service.generar_cobros_pendientes(tarjeta_id, "2026-08-31"), [])

        with root_db.get_conn() as conn:
            cobros = conn.execute(
                "SELECT periodo, fecha_cobro, fecha_pago, origen, estado, movimiento_id FROM tarjeta_suscripcion_cobros WHERE suscripcion_id = ?",
                (suscripcion_id,),
            ).fetchall()
            movimientos = conn.execute(
                "SELECT fecha, monto_centavos FROM movimientos WHERE suscripcion_tarjeta_id = ?",
                (suscripcion_id,),
            ).fetchall()
            suscripcion = conn.execute(
                "SELECT fecha_proximo_cobro FROM tarjeta_suscripciones WHERE id = ?",
                (suscripcion_id,),
            ).fetchone()

        self.assertEqual(len(cobros), 1)
        self.assertEqual(cobros[0]["periodo"], "2026-08")
        self.assertEqual(cobros[0]["fecha_cobro"], "2026-08-22")
        self.assertEqual(cobros[0]["fecha_pago"], "2026-08-10")
        self.assertEqual(cobros[0]["origen"], "manual")
        self.assertEqual(cobros[0]["estado"], "pagado")
        self.assertEqual(len(movimientos), 1)
        self.assertEqual(movimientos[0]["fecha"], "2026-08-10")
        self.assertEqual(movimientos[0]["monto_centavos"], -100000)
        self.assertEqual(suscripcion["fecha_proximo_cobro"], "2026-09-22")

    def test_regulariza_periodos_vencidos_una_sola_vez(self):
        tarjeta_id = self._tarjeta()
        suscripcion_id = self._suscripcion(tarjeta_id, fecha_inicio="2026-08-22")

        movimientos = self.service.generar_cobros_pendientes(tarjeta_id, "2026-10-25")
        self.assertEqual(len(movimientos), 3)
        self.assertEqual(self.service.generar_cobros_pendientes(tarjeta_id, "2026-10-25"), [])

        with root_db.get_conn() as conn:
            cobros = conn.execute(
                "SELECT periodo, origen FROM tarjeta_suscripcion_cobros WHERE suscripcion_id = ? ORDER BY periodo",
                (suscripcion_id,),
            ).fetchall()
            suscripcion = conn.execute(
                "SELECT fecha_proximo_cobro FROM tarjeta_suscripciones WHERE id = ?",
                (suscripcion_id,),
            ).fetchone()

        self.assertEqual([(c["periodo"], c["origen"]) for c in cobros], [
            ("2026-08", "automatico"),
            ("2026-09", "automatico"),
            ("2026-10", "automatico"),
        ])
        self.assertEqual(suscripcion["fecha_proximo_cobro"], "2026-11-22")

    def test_relacion_monto_y_pago_anticipado(self):
        tarjeta_id = self._tarjeta()
        suscripcion_id = self._suscripcion(tarjeta_id, fecha_inicio="2026-08-22")

        pago_agosto = self.service.pagar_suscripcion(suscripcion_id, "2026-08-10")
        self.service.editar_monto_suscripcion(suscripcion_id, {"nuevo_monto": "1800,00"})
        self.service.generar_cobros_pendientes(tarjeta_id, "2026-09-30")

        with root_db.get_conn() as conn:
            cobros = conn.execute(
                "SELECT periodo, monto_centavos FROM tarjeta_suscripcion_cobros WHERE suscripcion_id = ? ORDER BY periodo",
                (suscripcion_id,),
            ).fetchall()

        self.assertEqual(pago_agosto["monto_centavos"], 100000)
        self.assertEqual([(c["periodo"], c["monto_centavos"]) for c in cobros], [
            ("2026-08", 100000),
            ("2026-09", 180000),
        ])

        tarjeta_id_2 = self._tarjeta()
        suscripcion_id_2 = self._suscripcion(tarjeta_id_2, nombre="Spotify", fecha_inicio="2026-08-22")
        self.service.editar_monto_suscripcion(suscripcion_id_2, {"nuevo_monto": "1800,00"})
        pago_agosto_nuevo = self.service.pagar_suscripcion(suscripcion_id_2, "2026-08-10")
        self.assertEqual(pago_agosto_nuevo["monto_centavos"], 180000)

    def test_suscripcion_cancelada_no_permite_monto_ni_pago(self):
        tarjeta_id = self._tarjeta()
        suscripcion_id = self._suscripcion(tarjeta_id, fecha_inicio="2026-08-22")
        self.service.cambiar_estado_suscripcion(suscripcion_id, "cancelada", "2026-08-01")

        with self.assertRaises(self.service.TarjetasError):
            self.service.editar_monto_suscripcion(suscripcion_id, {"nuevo_monto": "1200,00"})
        with self.assertRaises(self.service.TarjetasError):
            self.service.pagar_suscripcion(suscripcion_id, "2026-08-10")

    def test_error_durante_cobro_no_deja_datos_parciales(self):
        tarjeta_id = self._tarjeta()
        suscripcion_id = self._suscripcion(tarjeta_id, fecha_inicio="2026-08-22")
        original = self.service.repo.registrar_cobro_suscripcion

        def fallar(*args, **kwargs):
            raise RuntimeError("fallo simulado")

        self.service.repo.registrar_cobro_suscripcion = fallar
        try:
            with self.assertRaises(RuntimeError):
                self.service.pagar_suscripcion(suscripcion_id, "2026-08-10")
        finally:
            self.service.repo.registrar_cobro_suscripcion = original

        with root_db.get_conn() as conn:
            movimientos = conn.execute(
                "SELECT COUNT(*) AS total FROM movimientos WHERE suscripcion_tarjeta_id = ?",
                (suscripcion_id,),
            ).fetchone()["total"]
            cobros = conn.execute(
                "SELECT COUNT(*) AS total FROM tarjeta_suscripcion_cobros WHERE suscripcion_id = ?",
                (suscripcion_id,),
            ).fetchone()["total"]
            suscripcion = conn.execute(
                "SELECT fecha_proximo_cobro FROM tarjeta_suscripciones WHERE id = ?",
                (suscripcion_id,),
            ).fetchone()

        self.assertEqual(movimientos, 0)
        self.assertEqual(cobros, 0)
        self.assertEqual(suscripcion["fecha_proximo_cobro"], "2026-08-22")

    def test_suscripcion_estados_controlan_cobros(self):
        tarjeta_id = self._tarjeta()
        suscripcion_id = self._suscripcion(tarjeta_id, fecha_inicio="2026-07-10")

        self.service.cambiar_estado_suscripcion(suscripcion_id, "suspendida", "2026-07-15")
        self.assertEqual(self.service.generar_cobros_pendientes(tarjeta_id, "2026-08-31"), [])

        self.service.cambiar_estado_suscripcion(suscripcion_id, "activa", "2026-09-01")
        movimientos = self.service.generar_cobros_pendientes(tarjeta_id, "2026-09-30")
        self.assertEqual(len(movimientos), 1)

        self.service.cambiar_estado_suscripcion(suscripcion_id, "cancelada", "2026-09-20")
        self.assertEqual(self.service.generar_cobros_pendientes(tarjeta_id, "2026-12-31"), [])

        with root_db.get_conn() as conn:
            suscripcion = conn.execute("SELECT estado, fecha_cancelacion FROM tarjeta_suscripciones WHERE id = ?", (suscripcion_id,)).fetchone()
            periodos = conn.execute(
                "SELECT periodo FROM tarjeta_suscripcion_cobros WHERE suscripcion_id = ? ORDER BY periodo",
                (suscripcion_id,),
            ).fetchall()

        self.assertEqual(suscripcion["estado"], "cancelada")
        self.assertEqual(suscripcion["fecha_cancelacion"], "2026-09-20")
        self.assertEqual([p["periodo"] for p in periodos], ["2026-09"])


if __name__ == "__main__":
    unittest.main()
