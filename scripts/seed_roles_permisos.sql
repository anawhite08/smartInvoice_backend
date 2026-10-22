-- =============================================================================
-- Catálogo de permisos y roles predefinidos de Smart Invoice
--
-- Requiere que ya existan las tablas permisos, roles y rol_permisos (las usa el
-- backend en app/utils/cloudsql.py). Los IDs son UUID y se generan acá; como el
-- UUID cambia en cada base, permisos y roles se identifican por su "nombre".
--
-- Idempotente: se puede correr varias veces sin duplicar filas (solo inserta lo
-- que falta).
--
-- La pantalla Roles y Permisos solo muestra las categorías 'Facturas' y
-- 'Administracion' (sin tilde) — usar exactamente esos valores.
-- =============================================================================

BEGIN;

-- -----------------------------------------------------------------------------
-- Permisos
-- -----------------------------------------------------------------------------
INSERT INTO permisos (id_permiso, nombre, descripcion, categoria)
SELECT gen_random_uuid(), v.nombre, v.descripcion, v.categoria
FROM (VALUES
    -- Facturas
    ('Ver facturas asignadas',        'Ver en la bandeja y el dashboard las facturas de los proveedores asignados al usuario', 'Facturas'),
    ('Ver todas las facturas',        'Ver las facturas de todos los proveedores (selector "Todas")',                          'Facturas'),
    ('Cargar facturas',               'Subir documentos y procesarlos con la extracción por IA',                               'Facturas'),
    ('Revisar y editar facturas',     'Corregir los datos extraídos y guardar la factura',                                     'Facturas'),
    ('Aprobar facturas',              'Pasar facturas al estado En aprobación / aprobadas',                                    'Facturas'),
    ('Registrar en SAP',              'Enviar facturas aprobadas para su registro en SAP',                                     'Facturas'),
    ('Eliminar facturas',             'Eliminar facturas y sus documentos',                                                    'Facturas'),
    ('Ver reportes',                  'Acceder a la sección de Reportes',                                                      'Facturas'),
    -- Administración
    ('Gestionar usuarios',            'Crear, editar usuarios y enviar el restablecimiento de contraseña',                     'Administracion'),
    ('Gestionar unidades de negocio', 'Crear y editar unidades de negocio y sus integrantes',                                  'Administracion'),
    ('Gestionar roles y permisos',    'Crear y editar roles personalizados',                                                   'Administracion'),
    ('Asignar proveedores',           'Asignar cada proveedor a un usuario responsable',                                       'Administracion'),
    ('Gestionar catálogos',           'Mantener proveedores, sociedades e impuestos',                                          'Administracion'),
    ('Configuración del sistema',     'Acceder al Panel de Administración',                                                    'Administracion')
) AS v (nombre, descripcion, categoria)
WHERE NOT EXISTS (SELECT 1 FROM permisos p WHERE p.nombre = v.nombre);

-- -----------------------------------------------------------------------------
-- Roles predefinidos (es_predefinido = TRUE: la pantalla no permite editarlos)
-- Mismos nombres que los tipos de usuario actuales.
-- -----------------------------------------------------------------------------
INSERT INTO roles (id_rol, nombre, descripcion, es_predefinido)
SELECT gen_random_uuid(), v.nombre, v.descripcion, TRUE
FROM (VALUES
    ('Administrador',     'Acceso completo a facturas y a la administración de la plataforma'),
    ('Unidad de Negocio', 'Carga y revisión de las facturas de sus proveedores asignados')
) AS v (nombre, descripcion)
WHERE NOT EXISTS (SELECT 1 FROM roles r WHERE r.nombre = v.nombre);

-- Administrador: todos los permisos
INSERT INTO rol_permisos (id_rol, id_permiso)
SELECT r.id_rol, p.id_permiso
FROM roles r
CROSS JOIN permisos p
WHERE r.nombre = 'Administrador'
  AND NOT EXISTS (
      SELECT 1 FROM rol_permisos rp WHERE rp.id_rol = r.id_rol AND rp.id_permiso = p.id_permiso
  );

-- Unidad de Negocio: solo operación sobre sus facturas
INSERT INTO rol_permisos (id_rol, id_permiso)
SELECT r.id_rol, p.id_permiso
FROM roles r
JOIN permisos p ON p.nombre IN ('Ver facturas asignadas', 'Cargar facturas', 'Revisar y editar facturas', 'Ver reportes')
WHERE r.nombre = 'Unidad de Negocio'
  AND NOT EXISTS (
      SELECT 1 FROM rol_permisos rp WHERE rp.id_rol = r.id_rol AND rp.id_permiso = p.id_permiso
  );

COMMIT;

-- Verificación
SELECT categoria, nombre, id_permiso FROM permisos ORDER BY categoria, nombre;
SELECT r.nombre AS rol, r.es_predefinido, COUNT(rp.id_permiso) AS permisos
FROM roles r LEFT JOIN rol_permisos rp ON rp.id_rol = r.id_rol
GROUP BY r.nombre, r.es_predefinido ORDER BY r.nombre;
