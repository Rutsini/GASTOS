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

    def _compra(
        self,
        tarjeta_id,
        cuotas="3",
        monto="100,00",
        descripcion="Celular",
        fecha_compra="2026-07-01",
        fecha_inicio="2026-07-01",
        primer_vencimiento="2026-07-10",
    ):
        return self.service.crear_compra_en_cuotas(tarjeta_id, {
            "descripcion": descripcion,
            "comercio": "Tienda",
            "monto_original": monto,
            "cantidad_cuotas": cuotas,
            "fecha_compra": fecha_compra,
            "fecha_inicio": fecha_inicio,
            "primer_vencimiento": primer_vencimiento,
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

    def test_resumen_tarjeta_simplificado_cuenta_compras_y_total_financiado_activo(self):
        tarjeta_id = self._tarjeta()
        self._compra(tarjeta_id, cuotas="3", monto="100,00", descripcion="Compra activa 1")
        self._compra(tarjeta_id, cuotas="2", monto="200,00", descripcion="Compra activa 2")
        finalizada_id = self._compra(tarjeta_id, cuotas="1", monto="500,00", descripcion="Compra finalizada")
        with root_db.get_conn() as conn:
            conn.execute(
                "UPDATE cuotas_tarjeta SET estado = 'pagada', fecha_pago = '2026-07-15' WHERE compra_tarjeta_id = ?",
                (finalizada_id,),
            )
            conn.execute("UPDATE compras_tarjeta SET estado = 'finalizada' WHERE id = ?", (finalizada_id,))
            conn.commit()

        tarjeta = self.service.obtener_detalle_tarjeta(tarjeta_id)["tarjeta"]

        self.assertEqual(tarjeta["compras_activas"], 2)
        self.assertEqual(tarjeta["monto_total_tarjeta_centavos"], 30000)
        self.assertEqual(tarjeta["monto_total_tarjeta_fmt"], "$300,00")
        self.assertEqual(tarjeta["pendiente_centavos"], 30000)

    def test_total_periodo_suma_cuotas_y_suscripciones_sin_duplicar(self):
        tarjeta_id = self._tarjeta()
        compra_pagada_id = self._compra(
            tarjeta_id,
            cuotas="2",
            monto="200,00",
            descripcion="Compra con cuota pagada",
            fecha_compra="2026-12-01",
            fecha_inicio="2026-12-01",
            primer_vencimiento="2026-12-10",
        )
        compra_pendiente_id = self._compra(
            tarjeta_id,
            cuotas="1",
            monto="300,00",
            descripcion="Compra pendiente",
            fecha_compra="2026-12-01",
            fecha_inicio="2026-12-01",
            primer_vencimiento="2026-12-15",
        )
        compra_cancelada_id = self._compra(
            tarjeta_id,
            cuotas="1",
            monto="999,00",
            descripcion="Compra cancelada",
            fecha_compra="2026-12-01",
            fecha_inicio="2026-12-01",
            primer_vencimiento="2026-12-20",
        )
        with root_db.get_conn() as conn:
            cuota_pagada_id = conn.execute(
                "SELECT id FROM cuotas_tarjeta WHERE compra_tarjeta_id = ? AND numero_cuota = 1",
                (compra_pagada_id,),
            ).fetchone()["id"]
            conn.execute("UPDATE compras_tarjeta SET estado = 'cancelada' WHERE id = ?", (compra_cancelada_id,))
            conn.commit()
        self.service.pagar_cuota(cuota_id=cuota_pagada_id, fecha_pago="2026-12-11")

        suscripcion_pagada_id = self._suscripcion(tarjeta_id, nombre="Streaming pagado", monto="25,00", fecha_inicio="2026-12-05")
        self.service.pagar_suscripcion(suscripcion_pagada_id, fecha_pago="2026-12-06")
        self._suscripcion(tarjeta_id, nombre="Streaming pendiente", monto="30,00", fecha_inicio="2026-12-08")
        suscripcion_modificada_id = self._suscripcion(tarjeta_id, nombre="Streaming modificado", monto="40,00", fecha_inicio="2026-11-05")
        self.service.editar_monto_suscripcion(
            suscripcion_modificada_id,
            {"nuevo_monto": "45,00", "periodo_desde": "2026-12"},
        )
        suscripcion_suspendida_id = self._suscripcion(tarjeta_id, nombre="Streaming suspendido", monto="50,00", fecha_inicio="2026-11-05")
        self.service.cambiar_estado_suscripcion(suscripcion_suspendida_id, "suspendida", "2026-11-20")
        suscripcion_cancelada_id = self._suscripcion(tarjeta_id, nombre="Streaming cancelado", monto="60,00", fecha_inicio="2026-11-05")
        self.service.cambiar_estado_suscripcion(suscripcion_cancelada_id, "cancelada", "2026-11-25")

        detalle = self.service.obtener_detalle_tarjeta(tarjeta_id, periodo="2026-12")
        total_periodo = detalle["total_periodo"]

        self.assertEqual(total_periodo["total_cuotas_periodo"], 40000)
        self.assertEqual(total_periodo["total_suscripciones_periodo"], 10000)
        self.assertEqual(total_periodo["total_periodo"], 50000)
        self.assertEqual(total_periodo["total_periodo_fmt"], "$500,00")
        self.assertEqual(detalle["tarjeta"]["periodo_actual_centavos"], 30000)
        self.assertEqual(detalle["tarjeta"]["periodo_actual_fmt"], "$300,00")

        with root_db.get_conn() as conn:
            cobros = conn.execute(
                "SELECT COUNT(*) AS total FROM tarjeta_suscripcion_cobros WHERE suscripcion_id = ? AND periodo = '2026-12'",
                (suscripcion_pagada_id,),
            ).fetchone()["total"]
            pendiente = conn.execute(
                "SELECT estado FROM cuotas_tarjeta WHERE compra_tarjeta_id = ?",
                (compra_pendiente_id,),
            ).fetchone()["estado"]
        self.assertEqual(cobros, 1)
        self.assertEqual(pendiente, "pendiente")

    def test_total_periodo_cubre_solo_cuotas_solo_suscripciones_sin_conceptos_y_cambio_anio(self):
        tarjeta_id = self._tarjeta()
        self._compra(
            tarjeta_id,
            cuotas="2",
            monto="200,00",
            descripcion="Compra cambio de anio",
            fecha_compra="2026-12-01",
            fecha_inicio="2026-12-01",
            primer_vencimiento="2026-12-10",
        )
        self._suscripcion(tarjeta_id, nombre="Servicio marzo", monto="80,00", fecha_inicio="2027-03-05")

        solo_cuotas = self.service.obtener_detalle_tarjeta(tarjeta_id, periodo="2027-01")["total_periodo"]
        solo_suscripciones = self.service.obtener_detalle_tarjeta(tarjeta_id, periodo="2027-03")["total_periodo"]
        sin_conceptos = self.service.obtener_detalle_tarjeta(tarjeta_id, periodo="2026-11")["total_periodo"]

        self.assertEqual(solo_cuotas["total_cuotas_periodo"], 10000)
        self.assertEqual(solo_cuotas["total_suscripciones_periodo"], 0)
        self.assertEqual(solo_cuotas["total_periodo"], 10000)
        self.assertEqual(solo_suscripciones["total_cuotas_periodo"], 0)
        self.assertEqual(solo_suscripciones["total_suscripciones_periodo"], 8000)
        self.assertEqual(solo_suscripciones["total_periodo"], 8000)
        self.assertEqual(sin_conceptos["total_cuotas_periodo"], 0)
        self.assertEqual(sin_conceptos["total_suscripciones_periodo"], 0)
        self.assertEqual(sin_conceptos["total_periodo_fmt"], "$0,00")

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

    def test_pago_manual_no_adelanta_periodo_futuro_con_segundo_click(self):
        tarjeta_id = self._tarjeta()
        suscripcion_id = self._suscripcion(tarjeta_id, fecha_inicio="2026-08-22")

        self.service.pagar_suscripcion(suscripcion_id, "2026-08-10")

        with self.assertRaisesRegex(self.service.TarjetasError, "periodo actual"):
            self.service.pagar_suscripcion(suscripcion_id, "2026-08-10")

        with root_db.get_conn() as conn:
            movimientos = conn.execute(
                "SELECT fecha, descripcion, monto_centavos, categoria, subcategoria_id, tarjeta_id FROM movimientos WHERE suscripcion_tarjeta_id = ?",
                (suscripcion_id,),
            ).fetchall()
            cobros = conn.execute(
                "SELECT periodo, movimiento_id, monto_centavos, fecha_pago, origen FROM tarjeta_suscripcion_cobros WHERE suscripcion_id = ?",
                (suscripcion_id,),
            ).fetchall()
            suscripcion = conn.execute(
                "SELECT fecha_proximo_cobro FROM tarjeta_suscripciones WHERE id = ?",
                (suscripcion_id,),
            ).fetchone()

        self.assertEqual(len(movimientos), 1)
        self.assertEqual(movimientos[0]["fecha"], "2026-08-10")
        self.assertEqual(movimientos[0]["descripcion"], "Suscripcion - Netflix")
        self.assertEqual(movimientos[0]["monto_centavos"], -100000)
        self.assertEqual(movimientos[0]["categoria"], "Electronica")
        self.assertEqual(movimientos[0]["subcategoria_id"], self.subcategoria_id)
        self.assertEqual(movimientos[0]["tarjeta_id"], tarjeta_id)
        self.assertEqual(len(cobros), 1)
        self.assertEqual(cobros[0]["periodo"], "2026-08")
        self.assertTrue(cobros[0]["movimiento_id"])
        self.assertEqual(cobros[0]["monto_centavos"], 100000)
        self.assertEqual(cobros[0]["fecha_pago"], "2026-08-10")
        self.assertEqual(cobros[0]["origen"], "manual")
        self.assertEqual(suscripcion["fecha_proximo_cobro"], "2026-09-22")

    def test_pago_manual_no_registra_cobro_si_movimiento_no_se_crea(self):
        tarjeta_id = self._tarjeta()
        suscripcion_id = self._suscripcion(tarjeta_id, fecha_inicio="2026-08-22")
        original = self.service.repo.crear_movimiento_cobro_suscripcion

        def sin_movimiento(*args, **kwargs):
            return None

        self.service.repo.crear_movimiento_cobro_suscripcion = sin_movimiento
        try:
            with self.assertRaisesRegex(self.service.TarjetasError, "movimiento"):
                self.service.pagar_suscripcion(suscripcion_id, "2026-08-10")
        finally:
            self.service.repo.crear_movimiento_cobro_suscripcion = original

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

    def test_pago_manual_diciembre_no_adelanta_enero_sin_indicar_periodo(self):
        tarjeta_id = self._tarjeta()
        suscripcion_id = self._suscripcion(tarjeta_id, fecha_inicio="2026-12-31")

        self.service.pagar_suscripcion(suscripcion_id, "2026-12-05")

        with self.assertRaisesRegex(self.service.TarjetasError, "periodo actual"):
            self.service.pagar_suscripcion(suscripcion_id, "2026-12-05")

        with root_db.get_conn() as conn:
            cobros = conn.execute(
                "SELECT periodo FROM tarjeta_suscripcion_cobros WHERE suscripcion_id = ? ORDER BY periodo",
                (suscripcion_id,),
            ).fetchall()
            movimientos = conn.execute(
                "SELECT COUNT(*) AS total FROM movimientos WHERE suscripcion_tarjeta_id = ?",
                (suscripcion_id,),
            ).fetchone()["total"]
            suscripcion = conn.execute(
                "SELECT fecha_proximo_cobro FROM tarjeta_suscripciones WHERE id = ?",
                (suscripcion_id,),
            ).fetchone()

        self.assertEqual([c["periodo"] for c in cobros], ["2026-12"])
        self.assertEqual(movimientos, 1)
        self.assertEqual(suscripcion["fecha_proximo_cobro"], "2027-01-31")

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

    def test_proyeccion_cuotas_usa_cuotas_pendientes_y_totales_por_mes(self):
        tarjeta_id = self._tarjeta()
        self._compra(
            tarjeta_id,
            cuotas="6",
            monto="600,00",
            descripcion="Televisor Samsung",
            fecha_compra="2026-11-20",
            fecha_inicio="2026-12-01",
            primer_vencimiento="2026-12-10",
        )
        self._compra(
            tarjeta_id,
            cuotas="2",
            monto="200,00",
            descripcion="Celular Motorola",
            fecha_compra="2026-12-15",
            fecha_inicio="2027-01-01",
            primer_vencimiento="2027-01-10",
        )
        self._compra(
            tarjeta_id,
            cuotas="1",
            monto="1000,00",
            descripcion="Nombre de compra larguisimo para probar que la proyeccion no se rompe",
            fecha_compra="2026-12-01",
            fecha_inicio="2026-12-01",
            primer_vencimiento="2026-12-20",
        )
        finalizada_id = self._compra(
            tarjeta_id,
            cuotas="1",
            monto="999,00",
            descripcion="Compra finalizada",
            fecha_compra="2026-12-01",
            fecha_inicio="2026-12-01",
            primer_vencimiento="2026-12-10",
        )
        cancelada_id = self._compra(
            tarjeta_id,
            cuotas="3",
            monto="300,00",
            descripcion="Compra cancelada",
            fecha_compra="2026-12-01",
            fecha_inicio="2026-12-01",
            primer_vencimiento="2026-12-10",
        )
        self._compra(
            tarjeta_id,
            cuotas="2",
            monto="200,00",
            descripcion="Compra fuera de ventana",
            fecha_compra="2027-06-01",
            fecha_inicio="2027-06-01",
            primer_vencimiento="2027-06-10",
        )
        with root_db.get_conn() as conn:
            conn.execute("UPDATE cuotas_tarjeta SET estado = 'pagada', fecha_pago = '2026-12-12' WHERE compra_tarjeta_id = ?", (finalizada_id,))
            conn.execute("UPDATE compras_tarjeta SET estado = 'finalizada' WHERE id = ?", (finalizada_id,))
            conn.execute("UPDATE compras_tarjeta SET estado = 'cancelada' WHERE id = ?", (cancelada_id,))
            conn.commit()

        detalle = self.service.obtener_detalle_tarjeta(tarjeta_id)
        proyeccion = self.service.proyectar_cuotas_tarjeta(
            detalle["compras"],
            detalle["cuotas_por_compra"],
            fecha_base="2026-12-15",
        )

        self.assertEqual([m["periodo"] for m in proyeccion["meses"]], [
            "2026-12",
            "2027-01",
            "2027-02",
            "2027-03",
            "2027-04",
            "2027-05",
        ])
        self.assertEqual(proyeccion["meses"][0]["label"], "Dic 2026")
        self.assertEqual(proyeccion["meses"][1]["label"], "Ene 2027")
        descripciones = [fila["descripcion"] for fila in proyeccion["filas"]]
        self.assertIn("Televisor Samsung", descripciones)
        self.assertIn("Celular Motorola", descripciones)
        self.assertIn("Nombre de compra larguisimo para probar que la proyeccion no se rompe", descripciones)
        self.assertNotIn("Compra finalizada", descripciones)
        self.assertNotIn("Compra cancelada", descripciones)
        self.assertNotIn("Compra fuera de ventana", descripciones)
        self.assertEqual([t["monto_centavos"] for t in proyeccion["totales"]], [
            110000,
            20000,
            20000,
            10000,
            10000,
            10000,
        ])

    def test_proyeccion_cuotas_muestra_vacio_si_no_hay_compras_activas(self):
        tarjeta_id = self._tarjeta()
        compra_id = self._compra(tarjeta_id, cuotas="1", monto="500,00")
        with root_db.get_conn() as conn:
            conn.execute("UPDATE cuotas_tarjeta SET estado = 'pagada', fecha_pago = '2026-07-15' WHERE compra_tarjeta_id = ?", (compra_id,))
            conn.execute("UPDATE compras_tarjeta SET estado = 'finalizada' WHERE id = ?", (compra_id,))
            conn.commit()

        detalle = self.service.obtener_detalle_tarjeta(tarjeta_id)
        proyeccion = self.service.proyectar_cuotas_tarjeta(
            detalle["compras"],
            detalle["cuotas_por_compra"],
            fecha_base="2026-12-15",
        )

        self.assertFalse(proyeccion["tiene_datos"])
        self.assertEqual(len(proyeccion["meses"]), 6)
        self.assertEqual([t["monto_centavos"] for t in proyeccion["totales"]], [0, 0, 0, 0, 0, 0])

    def test_elimina_compra_sin_pagos_borra_compra_y_cuotas(self):
        tarjeta_id = self._tarjeta()
        compra_id = self._compra(tarjeta_id, cuotas="3", monto="300,00", descripcion="Compra erronea")

        resultado = self.service.eliminar_compra(compra_id)

        self.assertEqual(resultado["tarjeta_id"], tarjeta_id)
        self.assertEqual(resultado["cuotas_eliminadas"], 3)
        self.assertEqual(resultado["movimientos_eliminados"], 0)
        with root_db.get_conn() as conn:
            self.assertIsNone(conn.execute("SELECT 1 FROM compras_tarjeta WHERE id = ?", (compra_id,)).fetchone())
            self.assertEqual(
                conn.execute("SELECT COUNT(*) AS total FROM cuotas_tarjeta WHERE compra_tarjeta_id = ?", (compra_id,)).fetchone()["total"],
                0,
            )
            self.assertEqual(conn.execute("PRAGMA foreign_key_check").fetchall(), [])

        detalle = self.service.obtener_detalle_tarjeta(tarjeta_id, periodo="2026-07")
        self.assertEqual(detalle["tarjeta"]["compras_activas"], 0)
        self.assertEqual(detalle["tarjeta"]["pendiente_centavos"], 0)
        self.assertFalse(detalle["proyeccion_cuotas"]["tiene_datos"])

    def test_elimina_compra_con_pagos_borra_historial_y_movimientos_automaticos(self):
        tarjeta_id = self._tarjeta()
        compra_id = self._compra(tarjeta_id, cuotas="2", monto="200,00", descripcion="Notebook")
        movimiento_id = self.service.pagar_cuota(compra_id=compra_id, fecha_pago="2026-07-15")
        with root_db.get_conn() as conn:
            conn.execute("""
                INSERT INTO movimientos (
                    tx_hash, archivo, linea, fecha, descripcion, monto_centavos, monto_raw,
                    categoria, subcategoria_id, clasificacion_origen, clasificacion_bloqueada,
                    tarjeta_id, generado_desde_tarjeta, anulado
                )
                VALUES ('manual-misma-notebook', 'manual', NULL, '2026-07-15', 'Notebook', -10000, '-100,00',
                        'Electronica', ?, 'manual', 1, ?, 0, 0)
            """, (self.subcategoria_id, tarjeta_id))
            manual_id = conn.execute("SELECT id FROM movimientos WHERE tx_hash = 'manual-misma-notebook'").fetchone()["id"]
            conn.commit()

        resultado = self.service.eliminar_compra(compra_id)

        self.assertEqual(resultado["movimientos_eliminados"], 1)
        self.assertEqual(resultado["historial_eliminado"], 1)
        with root_db.get_conn() as conn:
            self.assertIsNone(conn.execute("SELECT 1 FROM movimientos WHERE id = ?", (movimiento_id,)).fetchone())
            self.assertIsNotNone(conn.execute("SELECT 1 FROM movimientos WHERE id = ?", (manual_id,)).fetchone())
            self.assertEqual(
                conn.execute("SELECT COUNT(*) AS total FROM historial_pagos_tarjeta WHERE compra_tarjeta_id = ?", (compra_id,)).fetchone()["total"],
                0,
            )
            self.assertEqual(conn.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_elimina_suscripcion_sin_pagos_borra_registro_principal(self):
        tarjeta_id = self._tarjeta()
        suscripcion_id = self._suscripcion(tarjeta_id, nombre="Suscripcion erronea")

        resultado = self.service.eliminar_suscripcion(suscripcion_id)

        self.assertEqual(resultado["tarjeta_id"], tarjeta_id)
        self.assertEqual(resultado["cobros_eliminados"], 0)
        with root_db.get_conn() as conn:
            self.assertIsNone(conn.execute("SELECT 1 FROM tarjeta_suscripciones WHERE id = ?", (suscripcion_id,)).fetchone())
            self.assertEqual(conn.execute("PRAGMA foreign_key_check").fetchall(), [])

        detalle = self.service.obtener_detalle_tarjeta(tarjeta_id, periodo="2026-07")
        self.assertEqual(detalle["suscripciones"], [])
        self.assertEqual(detalle["total_periodo"]["total_suscripciones_periodo"], 0)

    def test_elimina_suscripcion_con_cobros_borra_cobros_historial_montos_y_movimientos_automaticos(self):
        tarjeta_id = self._tarjeta()
        suscripcion_id = self._suscripcion(tarjeta_id, nombre="Netflix")
        pago = self.service.pagar_suscripcion(suscripcion_id, "2026-07-05")
        self.service.editar_monto_suscripcion(suscripcion_id, {"nuevo_monto": "1200,00"})
        with root_db.get_conn() as conn:
            conn.execute("""
                INSERT INTO movimientos (
                    tx_hash, archivo, linea, fecha, descripcion, monto_centavos, monto_raw,
                    categoria, subcategoria_id, clasificacion_origen, clasificacion_bloqueada,
                    tarjeta_id, generado_desde_tarjeta, anulado
                )
                VALUES ('manual-mismo-netflix', 'manual', NULL, '2026-07-05', 'Suscripcion - Netflix', -100000, '-1000,00',
                        'Electronica', ?, 'manual', 1, ?, 0, 0)
            """, (self.subcategoria_id, tarjeta_id))
            manual_id = conn.execute("SELECT id FROM movimientos WHERE tx_hash = 'manual-mismo-netflix'").fetchone()["id"]
            conn.commit()

        resultado = self.service.eliminar_suscripcion(suscripcion_id)

        self.assertEqual(resultado["cobros_eliminados"], 1)
        self.assertEqual(resultado["historial_montos_eliminado"], 1)
        self.assertEqual(resultado["movimientos_eliminados"], 1)
        with root_db.get_conn() as conn:
            self.assertIsNone(conn.execute("SELECT 1 FROM movimientos WHERE id = ?", (pago["movimiento_id"],)).fetchone())
            self.assertIsNotNone(conn.execute("SELECT 1 FROM movimientos WHERE id = ?", (manual_id,)).fetchone())
            self.assertEqual(
                conn.execute("SELECT COUNT(*) AS total FROM tarjeta_suscripcion_cobros WHERE suscripcion_id = ?", (suscripcion_id,)).fetchone()["total"],
                0,
            )
            self.assertEqual(
                conn.execute("SELECT COUNT(*) AS total FROM tarjeta_suscripcion_historial_montos WHERE suscripcion_id = ?", (suscripcion_id,)).fetchone()["total"],
                0,
            )
            self.assertEqual(conn.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_eliminar_bloquea_movimientos_no_automaticos_vinculados_por_id(self):
        tarjeta_id = self._tarjeta()
        compra_id = self._compra(tarjeta_id, cuotas="1", monto="100,00")
        suscripcion_id = self._suscripcion(tarjeta_id)
        with root_db.get_conn() as conn:
            conn.execute("""
                INSERT INTO movimientos (
                    tx_hash, archivo, linea, fecha, descripcion, monto_centavos, monto_raw,
                    categoria, subcategoria_id, clasificacion_origen, clasificacion_bloqueada,
                    tarjeta_id, compra_tarjeta_id, generado_desde_tarjeta, anulado
                )
                VALUES ('manual-vinculado-compra', 'manual', NULL, '2026-07-01', 'Manual compra', -10000, '-100,00',
                        'Electronica', ?, 'manual', 1, ?, ?, 0, 0)
            """, (self.subcategoria_id, tarjeta_id, compra_id))
            conn.execute("""
                INSERT INTO movimientos (
                    tx_hash, archivo, linea, fecha, descripcion, monto_centavos, monto_raw,
                    categoria, subcategoria_id, clasificacion_origen, clasificacion_bloqueada,
                    tarjeta_id, suscripcion_tarjeta_id, generado_desde_tarjeta, anulado
                )
                VALUES ('manual-vinculado-suscripcion', 'manual', NULL, '2026-07-01', 'Manual suscripcion', -10000, '-100,00',
                        'Electronica', ?, 'manual', 1, ?, ?, 0, 0)
            """, (self.subcategoria_id, tarjeta_id, suscripcion_id))
            conn.commit()

        with self.assertRaisesRegex(self.service.TarjetasError, "no fueron generados automaticamente"):
            self.service.eliminar_compra(compra_id)
        with self.assertRaisesRegex(self.service.TarjetasError, "no fueron generados automaticamente"):
            self.service.eliminar_suscripcion(suscripcion_id)

        with root_db.get_conn() as conn:
            self.assertIsNotNone(conn.execute("SELECT 1 FROM compras_tarjeta WHERE id = ?", (compra_id,)).fetchone())
            self.assertIsNotNone(conn.execute("SELECT 1 FROM tarjeta_suscripciones WHERE id = ?", (suscripcion_id,)).fetchone())
            self.assertEqual(conn.execute("PRAGMA foreign_key_check").fetchall(), [])


if __name__ == "__main__":
    unittest.main()
