````markdow

# Integrantes

# Integrantes

# Integrantes

| Nombre | Legajo |
| --- | --- |
| Micaela Arrigoni | `90314` |
| Cristian Nicolás Oviedo | `99666` |
| Emanuel Rubiolo | `424360` |
| Matías Bruna | `77682` |
| Lisandro Revol | `66456` |
| Lisandro Puentes | `403113` |
| Carlos Tomás Ortiz | `99672` |
| Agustín Grassis | `400448` |
| Luis David Trifoglio | `402252` |
| Federico Aimetta | `406818` |
| Facundo Bazán Moreno | `401410` |
| Ignacio Agustín Bustamante | `402465` |
| Facundo Kolomi | `400948` |
| Federico Alejandro Nieto Poklepovic | `79542` |
| Máximo Andrés Russo | `403348` |

---

# Estructura del repositorio

```text
/
├── DocumentacionGeneral/
│   ├── EstructuraRepositorio.md
│   ├── Glosario.md
│   └── PlanDeConfiguracion.md
│
├── ReglasDeJuego/
│
├── Resumenes/
│
├── TPs/
│   ├── TP1 - ...
│   ├── TP2 - ...
│   ├── TP3 - ...
│   └── ...
│
└── Teorico/
    ├── Bibliografia/
    │   ├── ISW/
    │   ├── PA/
    │   ├── SCM/
    │   └── TS/
    │
    └── Presentaciones/
````

## Descripción de las carpetas

### `DocumentacionGeneral`

Contiene la documentación relacionada con la organización y gestión del repositorio.

* `EstructuraRepositorio.md`: describe la estructura de carpetas.
* `Glosario.md`: define las siglas utilizadas.
* `PlanDeConfiguracion.md`: contiene las decisiones relacionadas con la Gestión de Configuración.

### `ReglasDeJuego`

Contiene los documentos generales y reglas establecidas por la cátedra.

### `Resumenes`

Contiene los resúmenes elaborados durante el cursado.

### `TPs`

Contiene los Trabajos Prácticos realizados durante la materia.

Cada Trabajo Práctico posee su propia carpeta, en la cual se almacenan sus enunciados, documentos, enlaces, código y demás archivos relacionados.

### `Teorico`

Contiene el material teórico de la materia.

Se divide principalmente en:

* `Bibliografia`: material bibliográfico organizado por temática.
* `Presentaciones`: presentaciones utilizadas durante las clases.

---

# Ítems de Configuración

Se considera **Ítem de Configuración (IC)** a cada elemento que será identificado, almacenado y controlado dentro del repositorio.

Los ítems se identificarán mediante siglas que permitan reconocer rápidamente su contenido.

## Glosario de siglas

| Sigla | Significado            |
| ----- | ---------------------- |
| `MB`  | Material Bibliográfico |
| `PC`  | Presentación de Clase  |
| `TP`  | Trabajo Práctico       |

Además:

* `x` representa el número del Trabajo Práctico.
* El nombre posterior a la sigla identifica el contenido del ítem.
* La extensión identifica el formato del archivo.

---

# Regla de nombrado de Ítems de Configuración

Los archivos serán nombrados utilizando una sigla que permita identificar el tipo de Ítem de Configuración, seguida por la información necesaria para identificar su contenido.

Los diferentes componentes del nombre serán separados mediante guion bajo `_`.

## Material Bibliográfico

Se utilizará:

```text
MB_NombreMaterial.ext
```

Ejemplo:

```text
MB_GestionDeConfiguracionDeSoftware.pdf
```

---

## Presentaciones de Clase

Se utilizará:

```text
PC_NombrePresentacion.ext
```

Ejemplos:

```text
PC_IntroduccionALaIngenieriaDeSoftware.pdf
PC_SCM.pdf
PC_TestingDeSoftware.pdf
```

---

## Trabajos Prácticos

Se utilizará:

```text
TPx_NombreTP_Tipo.ext
```

Donde:

* `TP` identifica que se trata de un Trabajo Práctico.
* `x` corresponde al número del Trabajo Práctico.
* `NombreTP` identifica el tema o nombre del trabajo.
* `Tipo` identifica el tipo de documento contenido dentro del TP.
* `ext` corresponde a la extensión del archivo.

Ejemplos:

```text
TP4_HerramientasSCM_Enunciado.pdf
TP4_HerramientasSCM_Informe.pdf
TP5_UsoDelRepositorio_Enunciado.pdf
TP5_UsoDelRepositorio_Informe.pdf
```

De esta manera, el nombre del archivo permite identificar su contenido sin necesidad de abrirlo.

---

# Gestión de versiones

El repositorio utilizará **Git** para controlar las modificaciones realizadas sobre los Ítems de Configuración.

Cada cambio significativo deberá quedar registrado mediante un commit.

Esto permite:

* mantener un historial de modificaciones;
* conocer qué cambios fueron realizados;
* conocer quién realizó cada cambio;
* recuperar estados anteriores del repositorio.

---

# Convenciones de commits

El mensaje del commit deberá indicar claramente qué operación se realizó.

Se utilizarán los siguientes prefijos:

* `add:` o `agregar:` para incorporar un nuevo elemento.
* `update:` o `actualizar:` para modificar o mejorar un elemento existente.
* `remove:`, `delete:` o `eliminar:` para eliminar un elemento.

Los mensajes deberán utilizar verbos en presente y ser breves, claros y descriptivos.

Ejemplos:

```text
add: agregar enunciado del TP4
```

```text
update: corregir informe del TP4
```

```text
remove: eliminar documento obsoleto
```

El mensaje del commit debe permitir identificar qué elemento fue modificado y cuál fue el objetivo del cambio.

---

# Criterio de Línea Base

Se establece una **línea base** al momento de recibir la corrección de cada Trabajo Práctico.

La línea base estará compuesta por la documentación, código e Ítems de Configuración desarrollados hasta ese momento, dentro de los límites de tiempo establecidos por la cátedra.

La línea base representa un estado estable y de referencia del repositorio.

---

# Regla de nombrado de Líneas Base

Las líneas base serán identificadas mediante el siguiente formato:

```text
vX.X - <descripcion>
```

El número de versión se administrará de la siguiente manera:

* El primer número se incrementará con la primera entrega de un nuevo Trabajo Práctico.
* El segundo número se incrementará cuando se realicen correcciones o reentregas del mismo Trabajo Práctico.

Ejemplos:

```text
v1.0 - Entrega TP4
v1.1 - Reentrega TP4
v2.0 - Entrega TP5
v2.1 - Reentrega TP5
```

Las líneas base serán identificadas en Git mediante **tags**.

---

# Gestión de cambios

Los cambios posteriores a una línea base deberán registrarse mediante nuevos commits.

Una línea base previamente establecida no será modificada. Si se realizan correcciones o modificaciones, se establecerá una nueva versión.

Esto permite mantener la trazabilidad de los cambios realizados sobre los Ítems de Configuración.

---

# Herramientas utilizadas

Para la Gestión de Configuración se utilizan:

* **Git** como herramienta de control de versiones.
* **GitHub** como repositorio remoto.

El repositorio será de acceso público de acuerdo con lo establecido por la cátedra.

```
```
