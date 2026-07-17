CREATE OR REPLACE FUNCTION grover_meeting_subgraph(
    p_seeds text[],
    p_scope_prefix text DEFAULT NULL
)
RETURNS TABLE(path text)
LANGUAGE plpgsql
AS $fn$
DECLARE
    v_node text;
    v_origin text;
    v_neighbor text;
    v_neighbor_origin text;
    v_origin_component text;
    v_neighbor_component text;
    v_endpoint text;
    v_pred text;
    v_components integer;
    v_deleted integer;
BEGIN
    CREATE TEMP TABLE IF NOT EXISTS _gm_seed(seed text PRIMARY KEY, ord integer NOT NULL) ON COMMIT DROP;
    TRUNCATE _gm_seed;

    CREATE TEMP TABLE IF NOT EXISTS _gm_edge(
        source text NOT NULL,
        target text NOT NULL,
        edge_type text NOT NULL,
        PRIMARY KEY (source, target, edge_type)
    ) ON COMMIT DROP;
    TRUNCATE _gm_edge;

    CREATE TEMP TABLE IF NOT EXISTS _gm_adj(
        node text NOT NULL,
        neighbor text NOT NULL,
        PRIMARY KEY (node, neighbor)
    ) ON COMMIT DROP;
    TRUNCATE _gm_adj;

    CREATE TEMP TABLE IF NOT EXISTS _gm_component(
        seed text PRIMARY KEY,
        component text NOT NULL
    ) ON COMMIT DROP;
    TRUNCATE _gm_component;

    CREATE TEMP TABLE IF NOT EXISTS _gm_visited(
        node text PRIMARY KEY,
        origin text NOT NULL,
        pred text NOT NULL,
        ord integer NOT NULL
    ) ON COMMIT DROP;
    TRUNCATE _gm_visited;

    CREATE TEMP TABLE IF NOT EXISTS _gm_queue(
        seq bigserial PRIMARY KEY,
        node text NOT NULL UNIQUE
    ) ON COMMIT DROP;
    TRUNCATE _gm_queue RESTART IDENTITY;

    CREATE TEMP TABLE IF NOT EXISTS _gm_bridge(
        a text NOT NULL,
        b text NOT NULL,
        PRIMARY KEY (a, b)
    ) ON COMMIT DROP;
    TRUNCATE _gm_bridge;

    CREATE TEMP TABLE IF NOT EXISTS _gm_kept(node text PRIMARY KEY) ON COMMIT DROP;
    TRUNCATE _gm_kept;

    INSERT INTO _gm_edge(source, target, edge_type)
    SELECT o.source_path, o.target_path, o.edge_type
    FROM vfs_objects AS o
    WHERE o.kind = 'edge'
      AND o.deleted_at IS NULL
      AND o.source_path IS NOT NULL
      AND o.target_path IS NOT NULL
      AND o.edge_type IS NOT NULL
      AND (
          p_scope_prefix IS NULL
          OR (
              o.source_path LIKE p_scope_prefix || '%'
              AND o.target_path LIKE p_scope_prefix || '%'
          )
      );

    INSERT INTO _gm_adj(node, neighbor)
    SELECT source, target FROM _gm_edge
    UNION
    SELECT target, source FROM _gm_edge;

    INSERT INTO _gm_seed(seed, ord)
    SELECT u.seed, MIN(u.ord)::integer
    FROM unnest(coalesce(p_seeds, ARRAY[]::text[])) WITH ORDINALITY AS u(seed, ord)
    WHERE EXISTS (
        SELECT 1
        FROM _gm_adj a
        WHERE a.node = u.seed OR a.neighbor = u.seed
    )
    GROUP BY u.seed;

    SELECT count(*) INTO v_components FROM _gm_seed;
    IF v_components = 0 THEN
        RETURN;
    END IF;

    IF v_components = 1 THEN
        RETURN QUERY
        SELECT s.seed
        FROM _gm_seed s
        ORDER BY s.ord;
        RETURN;
    END IF;

    INSERT INTO _gm_component(seed, component)
    SELECT seed, seed
    FROM _gm_seed;

    INSERT INTO _gm_visited(node, origin, pred, ord)
    SELECT seed, seed, seed, ord
    FROM _gm_seed
    ORDER BY ord;

    INSERT INTO _gm_queue(node)
    SELECT seed
    FROM _gm_seed
    ORDER BY ord;

    LOOP
        SELECT count(DISTINCT component) INTO v_components
        FROM _gm_component;
        EXIT WHEN v_components <= 1;

        v_node := NULL;
        v_origin := NULL;

        SELECT q.node, v.origin
        INTO v_node, v_origin
        FROM _gm_queue q
        JOIN _gm_visited v ON v.node = q.node
        ORDER BY q.seq
        LIMIT 1;

        EXIT WHEN v_node IS NULL;

        DELETE FROM _gm_queue WHERE node = v_node;

        SELECT c.component
        INTO v_origin_component
        FROM _gm_component c
        WHERE c.seed = v_origin;

        FOR v_neighbor IN
            SELECT a.neighbor
            FROM _gm_adj a
            WHERE a.node = v_node
            ORDER BY a.neighbor
        LOOP
            v_neighbor_origin := NULL;

            SELECT v.origin
            INTO v_neighbor_origin
            FROM _gm_visited v
            WHERE v.node = v_neighbor;

            IF v_neighbor_origin IS NULL THEN
                INSERT INTO _gm_visited(node, origin, pred, ord)
                SELECT v_neighbor, v_origin, v_node, s.ord
                FROM _gm_seed s
                WHERE s.seed = v_origin
                ON CONFLICT (node) DO NOTHING;

                INSERT INTO _gm_queue(node)
                VALUES (v_neighbor)
                ON CONFLICT (node) DO NOTHING;
            ELSE
                SELECT c.component
                INTO v_neighbor_component
                FROM _gm_component c
                WHERE c.seed = v_neighbor_origin;

                IF v_neighbor_component <> v_origin_component THEN
                    INSERT INTO _gm_bridge(a, b)
                    VALUES (LEAST(v_node, v_neighbor), GREATEST(v_node, v_neighbor))
                    ON CONFLICT (a, b) DO NOTHING;

                    UPDATE _gm_component
                    SET component = LEAST(v_origin_component, v_neighbor_component)
                    WHERE component IN (v_origin_component, v_neighbor_component);

                    SELECT c.component
                    INTO v_origin_component
                    FROM _gm_component c
                    WHERE c.seed = v_origin;
                END IF;
            END IF;
        END LOOP;
    END LOOP;

    INSERT INTO _gm_kept(node)
    SELECT seed
    FROM _gm_seed;

    FOR v_endpoint IN
        SELECT x.endpoint
        FROM (
            SELECT a AS endpoint FROM _gm_bridge
            UNION
            SELECT b AS endpoint FROM _gm_bridge
        ) AS x
    LOOP
        v_node := v_endpoint;
        LOOP
            INSERT INTO _gm_kept(node)
            VALUES (v_node)
            ON CONFLICT (node) DO NOTHING;

            EXIT WHEN EXISTS (
                SELECT 1 FROM _gm_seed s WHERE s.seed = v_node
            );

            v_pred := NULL;
            SELECT v.pred INTO v_pred
            FROM _gm_visited v
            WHERE v.node = v_node;

            EXIT WHEN v_pred IS NULL OR v_pred = v_node;
            v_node := v_pred;
        END LOOP;
    END LOOP;

    LOOP
        WITH removable AS (
            SELECT k.node
            FROM _gm_kept k
            LEFT JOIN _gm_seed s ON s.seed = k.node
            WHERE s.seed IS NULL
              AND (
                  NOT EXISTS (
                      SELECT 1
                      FROM _gm_edge e
                      JOIN _gm_kept kt ON kt.node = e.target
                      WHERE e.source = k.node
                  )
                  OR NOT EXISTS (
                      SELECT 1
                      FROM _gm_edge e
                      JOIN _gm_kept ks ON ks.node = e.source
                      WHERE e.target = k.node
                  )
              )
        )
        DELETE FROM _gm_kept k
        USING removable r
        WHERE k.node = r.node;

        GET DIAGNOSTICS v_deleted = ROW_COUNT;
        EXIT WHEN v_deleted = 0;
    END LOOP;

    RETURN QUERY
    SELECT k.node
    FROM _gm_kept k

    UNION ALL

    SELECT
        '/.vfs'
        || e.source
        || '/__meta__/edges/out/'
        || e.edge_type
        || '/'
        || ltrim(e.target, '/')
    FROM _gm_edge e
    JOIN _gm_kept ks ON ks.node = e.source
    JOIN _gm_kept kt ON kt.node = e.target

    ORDER BY 1;
END;
$fn$;
