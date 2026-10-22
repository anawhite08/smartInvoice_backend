-- =============================================================================
-- Asignación de roles a usuarios y unidades de negocio
--
-- Usuarios y unidades de negocio son ambos "sujetos" (tabla sujeto, mismo UUID
-- que usuarios.id_usuario / unidades_negocio.id_unidad_negocio), así que una sola
-- tabla sujeto_roles sirve para los dos.
--
-- Correr DESPUÉS de seed_roles_permisos.sql. Idempotente: se puede correr varias
-- veces sin duplicar filas.
-- =============================================================================

BEGIN;

CREATE TABLE IF NOT EXISTS sujeto_roles (
    id_sujeto         UUID      NOT NULL REFERENCES sujeto (id_sujeto) ON DELETE CASCADE,
    id_rol            UUID      NOT NULL REFERENCES roles (id_rol) ON DELETE CASCADE,
    fecha_asignacion  TIMESTAMP NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id_sujeto, id_rol)
);

-- Usuarios/unidades creados antes de que existiera la tabla sujeto pueden no tener
-- su fila ahí; sin ella no se les podría asignar un rol (llave foránea).
INSERT INTO sujeto (id_sujeto, tipo)
SELECT u.id_usuario, 'usuario'
FROM usuarios u
WHERE NOT EXISTS (SELECT 1 FROM sujeto s WHERE s.id_sujeto = u.id_usuario);

INSERT INTO sujeto (id_sujeto, tipo)
SELECT un.id_unidad_negocio, 'unidad_negocio'
FROM unidades_negocio un
WHERE NOT EXISTS (SELECT 1 FROM sujeto s WHERE s.id_sujeto = un.id_unidad_negocio);

-- Asignación inicial: cada usuario recibe el rol del sistema con el mismo nombre que
-- su tipo_usuario actual (Administrador / Unidad de Negocio). Solo a usuarios que
-- todavía no tengan ningún rol, para no pisar asignaciones hechas desde la pantalla.
INSERT INTO sujeto_roles (id_sujeto, id_rol)
SELECT u.id_usuario, r.id_rol
FROM usuarios u
JOIN roles r ON r.nombre = u.tipo_usuario AND r.es_predefinido = TRUE
WHERE NOT EXISTS (SELECT 1 FROM sujeto_roles sr WHERE sr.id_sujeto = u.id_usuario);

COMMIT;

-- Verificación
SELECT u.nombre, u.apellido, u.tipo_usuario, r.nombre AS rol
FROM usuarios u
LEFT JOIN sujeto_roles sr ON sr.id_sujeto = u.id_usuario
LEFT JOIN roles r ON r.id_rol = sr.id_rol
ORDER BY u.nombre;
