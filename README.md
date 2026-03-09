[![MseeP.ai Security Assessment Badge](https://mseep.net/mseep-audited.png)](https://mseep.ai/app/starrocks-mcp-server-starrocks)

# StarRocks Official MCP Server

The StarRocks MCP Server acts as a bridge between AI assistants and StarRocks databases. It allows for direct SQL execution, database exploration, data visualization via charts, and retrieving detailed schema/data overviews without requiring complex client-side setup.

<a href="https://glama.ai/mcp/servers/@StarRocks/mcp-server-starrocks">
  <img width="380" height="200" src="https://glama.ai/mcp/servers/@StarRocks/mcp-server-starrocks/badge" alt="StarRocks Server MCP server" />
</a>

## Features

- **Direct SQL Execution:** Run `SELECT` queries (`read_query`) and DDL/DML commands (`write_query`).
- **Database Exploration:** List databases and tables, retrieve table schemas (`starrocks://` resources).
- **System Information:** Access internal StarRocks metrics and states via the `proc://` resource path.
- **Detailed Overviews:** Get table overviews (`table_overview`) and intelligent database summaries (`db_summary`) including table sizes, replicas, and schema details.
- **Data Visualization:** Execute a query and generate a Plotly chart directly from the results (`query_and_plotly_chart`).
- **Performance Analysis:** Collect query dump/profile/analyze profile for diagnosis (`collect_query_dump_and_profile`).
- **HTTP Security:** Optional JWT SSO + IP allowlist controls for HTTP-based transports.
- **Intelligent Caching:** Table and database overviews are cached in memory to speed up repeated requests. Cache can be bypassed when needed.
- **Flexible Configuration:** Set connection details and behavior via environment variables.

## Configuration

The MCP server is typically run via an MCP host. Configuration is passed to the host, specifying how to launch the StarRocks MCP server process.

**Using Streamable HTTP (recommended):**

To start the server in Streamable HTTP mode:

First test connect is ok:
```
$ STARROCKS_URL=root:@localhost:8000 uv run mcp-server-starrocks --test
```

Start the server:

```
uv run mcp-server-starrocks --mode streamable-http --port 8000
```

Then config the MCP like this:

```json
{
  "mcpServers": {
    "mcp-server-starrocks": {
      "url": "http://localhost:8000/mcp"
    }
  }
}
```

### Streamable HTTP with SSO + Remote IP Allowlist

The following example enables both JWT SSO and HTTP-fetched IP allowlist.
These settings apply only to HTTP transports (`http`, `streamable-http`, `sse`), not `stdio`.

```bash
export STARROCKS_URL="root:password@localhost:9030/mydb"
export MCP_SSO_ENABLED=true
export MCP_SSO_JWKS_URL="https://your-idp.example.com/.well-known/jwks.json"
export MCP_SSO_ISSUER="https://your-idp.example.com/"
export MCP_SSO_AUDIENCE="starrocks-mcp"
export MCP_SSO_REQUIRED_SCOPES="mcp.read"

export MCP_IP_ALLOWLIST_URL="https://config.example.com/mcp/ip-allowlist"
export MCP_IP_ALLOWLIST_BEARER_TOKEN="your-config-service-token"
export MCP_IP_ALLOWLIST_REFRESH_SECONDS=60
export MCP_IP_ALLOWLIST_HTTP_TIMEOUT_SECONDS=3
export MCP_IP_ALLOWLIST_FAIL_OPEN=false
export MCP_TRUST_PROXY_HEADERS=true

uv run mcp-server-starrocks --mode streamable-http --host 0.0.0.0 --port 8000
```


**Using `uv` with installed package (individual environment variables):**

```json
{
  "mcpServers": {
    "mcp-server-starrocks": {
      "command": "uv",
      "args": ["run", "--with", "mcp-server-starrocks", "mcp-server-starrocks"],
      "env": {
        "STARROCKS_HOST": "default localhost",
        "STARROCKS_PORT": "default 9030",
        "STARROCKS_USER": "default root",
        "STARROCKS_PASSWORD": "default empty",
        "STARROCKS_DB": "default empty"
      }
    }
  }
}
```

**Using `uv` with installed package (connection URL):**

```json
{
  "mcpServers": {
    "mcp-server-starrocks": {
      "command": "uv",
      "args": ["run", "--with", "mcp-server-starrocks", "mcp-server-starrocks"],
      "env": {
        "STARROCKS_URL": "root:password@localhost:9030/my_database"
      }
    }
  }
}
```

**Using `uv` with local directory (for development):**

```json
{
  "mcpServers": {
    "mcp-server-starrocks": {
      "command": "uv",
      "args": [
        "--directory",
        "path/to/mcp-server-starrocks", // <-- Update this path
        "run",
        "mcp-server-starrocks"
      ],
      "env": {
        "STARROCKS_HOST": "default localhost",
        "STARROCKS_PORT": "default 9030",
        "STARROCKS_USER": "default root",
        "STARROCKS_PASSWORD": "default empty",
        "STARROCKS_DB": "default empty"
      }
    }
  }
}
```

**Using `uv` with local directory and connection URL:**

```json
{
  "mcpServers": {
    "mcp-server-starrocks": {
      "command": "uv",
      "args": [
        "--directory",
        "path/to/mcp-server-starrocks", // <-- Update this path
        "run",
        "mcp-server-starrocks"
      ],
      "env": {
        "STARROCKS_URL": "root:password@localhost:9030/my_database"
      }
    }
  }
}
```

**Command-line Arguments:**

The server supports the following command-line arguments:

```bash
uv run mcp-server-starrocks --help
```

- `--mode {stdio,sse,http,streamable-http}`: Transport mode (default: stdio or MCP_TRANSPORT_MODE env var)
- `--host HOST`: Server host for HTTP modes (default: localhost)
- `--port PORT`: Server port for HTTP modes
- `--test`: Run in test mode to verify functionality

Examples:

```bash
# Start in streamable HTTP mode on custom host/port
uv run mcp-server-starrocks --mode streamable-http --host 0.0.0.0 --port 8080

# Start in stdio mode (default)
uv run mcp-server-starrocks --mode stdio

# Run test mode
uv run mcp-server-starrocks --test
```

- The `url` field should point to the Streamable HTTP endpoint of your MCP server (adjust host/port as needed).
- With this configuration, clients can interact with the server using standard JSON over HTTP POST requests. No special SDK is required.
- All tool APIs accept and return standard JSON as described above.

> **Note:**
> The `sse` (Server-Sent Events) mode is deprecated and no longer maintained. Please use Streamable HTTP mode for all new integrations.

**Environment Variables:**

### Connection Configuration

You can configure StarRocks connection using either individual environment variables or a single connection URL:

**Option 1: Individual Environment Variables**

- `STARROCKS_HOST`: (Optional) Hostname or IP address of the StarRocks FE service. Defaults to `localhost`.
- `STARROCKS_PORT`: (Optional) MySQL protocol port of the StarRocks FE service. Defaults to `9030`.
- `STARROCKS_USER`: (Optional) StarRocks username. Defaults to `root`.
- `STARROCKS_PASSWORD`: (Optional) StarRocks password. Defaults to empty string.
- `STARROCKS_DB`: (Optional) Default database to use if not specified in tool arguments or resource URIs. If set, the connection will attempt to `USE` this database. Tools like `table_overview` and `db_summary` will use this if the database part is omitted in their arguments. Defaults to empty (no default database).

**Option 2: Connection URL (takes precedence over individual variables)**

- `STARROCKS_URL`: (Optional) A connection URL string that contains all connection parameters in a single variable. Format: `[<schema>://]user:password@host:port/database`. The schema part is optional. When this variable is set, it takes precedence over the individual `STARROCKS_HOST`, `STARROCKS_PORT`, `STARROCKS_USER`, `STARROCKS_PASSWORD`, and `STARROCKS_DB` variables.

  Examples:
  - `root:mypass@localhost:9030/test_db`
  - `mysql://admin:secret@db.example.com:9030/production`  
  - `starrocks://user:pass@192.168.1.100:9030/analytics`

### Additional Configuration

- `STARROCKS_OVERVIEW_LIMIT`: (Optional) An _approximate_ character limit for overview text generation (used by `table_overview` and related summary logic). Helps prevent excessive memory usage for very large schemas. Defaults to `20000`.

- `STARROCKS_MYSQL_AUTH_PLUGIN`: (Optional) Specifies the authentication plugin to use when connecting to the StarRocks FE service. For example, set to `mysql_clear_password` if your StarRocks deployment requires clear text password authentication (such as when using certain LDAP or external authentication setups). Only set this if your environment specifically requires it; otherwise, the default auth_plugin is used.

- `STARROCKS_POOL_SIZE`: (Optional) MySQL connection pool size. Defaults to `10`.
- `STARROCKS_CONNECTION_TIMEOUT`: (Optional) Connection timeout in seconds. Defaults to `10`.
- `STARROCKS_USE_PURE`: (Optional) Whether to use mysql-connector pure Python implementation. Defaults to `false`.
- `STARROCKS_FE_ARROW_FLIGHT_SQL_PORT`: (Optional) Enable Arrow Flight SQL mode when set.

- `MCP_TRANSPORT_MODE`: (Optional) Communication mode that specifies how the MCP Server exposes its services. Available options:
  - `stdio` (default): Communicates through standard input/output, suitable for MCP Host hosting.
  - `streamable-http` (Streamable HTTP): Starts as a Streamable HTTP Server, supporting RESTful API calls.
  - `sse`: **(Deprecated, not recommended)** Starts in Server-Sent Events (SSE) streaming mode, suitable for scenarios requiring streaming responses. **Note: SSE mode is no longer maintained, it is recommended to use Streamable HTTP mode uniformly.**

### HTTP Security Configuration (SSO + IP Allowlist)

> These settings only affect HTTP-based transports: `http`, `streamable-http`, and `sse`.
> `stdio` mode is not affected.

- `MCP_IP_ALLOWLIST`: (Optional) Comma-separated list of allowed client IPs or CIDRs.  
  Examples: `127.0.0.1,10.0.0.0/8,192.168.1.0/24`
- `MCP_IP_ALLOWLIST_URL`: (Optional) HTTP endpoint to fetch IP allowlist dynamically.
- `MCP_IP_ALLOWLIST_REFRESH_SECONDS`: (Optional) Refresh interval for `MCP_IP_ALLOWLIST_URL`. Defaults to `60`.
- `MCP_IP_ALLOWLIST_HTTP_TIMEOUT_SECONDS`: (Optional) HTTP timeout (seconds) when fetching allowlist. Defaults to `3`.
- `MCP_IP_ALLOWLIST_BEARER_TOKEN`: (Optional) Bearer token used when fetching allowlist from URL.
- `MCP_IP_ALLOWLIST_FAIL_OPEN`: (Optional) If `true`, requests are allowed when remote allowlist fetch fails and no local allowlist is available. Defaults to `false`.
- `MCP_TRUST_PROXY_HEADERS`: (Optional) Whether to trust proxy headers when resolving client IP (`X-Forwarded-For` / `X-Real-IP`). Defaults to `false`.

- `MCP_SSO_ENABLED`: (Optional) Enable JWT-based SSO authentication for HTTP requests. Defaults to `false`.
- `MCP_SSO_JWKS_URL`: (Optional) JWKS endpoint used to verify JWT signatures (recommended for OIDC providers).
- `MCP_SSO_JWT_SECRET`: (Optional) Shared secret for symmetric JWT verification (HS* algorithms).  
  `MCP_SSO_JWKS_URL` or `MCP_SSO_JWT_SECRET` is required when `MCP_SSO_ENABLED=true`.
- `MCP_SSO_JWT_ALGORITHMS`: (Optional) Comma-separated JWT algorithms.  
  If omitted: defaults to `RS256` when using JWKS, otherwise `HS256`.
- `MCP_SSO_ISSUER`: (Optional) Expected JWT issuer (`iss` claim).
- `MCP_SSO_AUDIENCE`: (Optional) Expected JWT audience (`aud` claim).
- `MCP_SSO_REQUIRED_SCOPES`: (Optional) Comma-separated required scopes.  
  Scopes are read from `scope` or `scp` claims.

When enabled, HTTP requests must include:

```http
Authorization: Bearer <JWT_TOKEN>
```

If `MCP_IP_ALLOWLIST_URL` is set, the server fetches allowlist entries from that endpoint and refreshes by interval.
Supported response formats:

1. JSON array:
```json
["10.0.0.0/8", "192.168.1.10"]
```
2. JSON object:
```json
{
  "allowlist": ["10.0.0.0/8", "192.168.1.10"]
}
```
3. Plain text (comma or newline separated):
```text
10.0.0.0/8,192.168.1.10
```

Behavior on fetch failure:
- If a previous allowlist exists, it continues using the last-known allowlist.
- If no allowlist is available and `MCP_IP_ALLOWLIST_FAIL_OPEN=false`, requests are rejected.

Request authorization order for HTTP transports:
1. IP allowlist check
2. SSO JWT check

## Components

### Tools

- `read_query`

  - **Description:** Execute a SELECT query or other commands that return a ResultSet (e.g., `SHOW`, `DESCRIBE`).
  - **Input:** 
    ```json
    {
      "query": "SQL query string",
      "db": "database name (optional, uses default database if not specified)"
    }
    ```
  - **Output:** Text content containing the query results in a CSV-like format, including a header row and a row count summary. Returns an error message on failure.

- `write_query`

  - **Description:** Execute a DDL (`CREATE`, `ALTER`, `DROP`), DML (`INSERT`, `UPDATE`, `DELETE`), or other StarRocks command that does not return a ResultSet.
  - **Input:** 
    ```json
    {
      "query": "SQL command string",
      "db": "database name (optional, uses default database if not specified)"
    }
    ```
  - **Output:** Text content confirming success (e.g., "Query OK, X rows affected") or reporting an error. Changes are committed automatically on success.

- `analyze_query`

  - **Description:** Analyze a query and get analyze result using query profile or explain analyze.
  - **Input:**
    ```json
    {
      "uuid": "Query ID, a string composed of 32 hexadecimal digits formatted as 8-4-4-4-12",
      "sql": "Query SQL to analyze",
      "db": "database name (optional, uses default database if not specified)"
    }
    ```
  - **Output:** Text content containing the query analysis results. Uses `ANALYZE PROFILE FROM` if uuid is provided, otherwise uses `EXPLAIN ANALYZE` if sql is provided.

- `collect_query_dump_and_profile`

  - **Description:** Execute a query and collect diagnostic artifacts: query dump, query profile, and analyze profile. This tool is designed for downstream tooling and troubleshooting workflows.
  - **Input:**
    ```json
    {
      "query": "SQL query to execute and analyze",
      "db": "database name (optional, uses default database if not specified)"
    }
    ```
  - **Output:** `ToolResult` with a short status text and structured diagnostic payload (`query_dump`, `profile`, `analyze_profile`, `query_id`, `duration`, etc.).

- `query_and_plotly_chart`

  - **Description:** Executes a SQL query, loads the results into a Pandas DataFrame, and generates a Plotly chart using a provided Python expression. Designed for visualization in supporting UIs.
  - **Input:**
    ```json
    {
      "query": "SQL query to fetch data",
      "plotly_expr": "Python expression string using 'px' (Plotly Express) and 'df' (DataFrame). Example: 'px.scatter(df, x=\"col1\", y=\"col2\")'",
      "format": "json|png|jpeg (optional, default: jpeg)",
      "db": "database name (optional, uses default database if not specified)"
    }
    ```
  - **Output:** A list containing:
    1.  `TextContent`: A text representation of the DataFrame and a note that the chart is for UI display.
    2.  `ImageContent`: For image formats (`png`/`jpeg`), the chart image is returned for UI rendering.
    3.  For `format=json`, chart `data` and `layout` are returned in `structured_content`.
    Returns text error message on failure or if the query yields no data.

- `table_overview`

  - **Description:** Get an overview of a specific table: columns (from `DESCRIBE`), total row count, and sample rows (`LIMIT 3`). Uses an in-memory cache unless `refresh` is true.
  - **Input:**
    ```json
    {
      "table": "Table name, optionally prefixed with database name (e.g., 'db_name.table_name' or 'table_name'). If database is omitted, uses STARROCKS_DB environment variable if set.",
      "refresh": false // Optional, boolean. Set to true to bypass the cache. Defaults to false.
    }
    ```
  - **Output:** Text content containing the formatted overview (columns, row count, sample data) or an error message. Cached results include previous errors if applicable.

- `db_summary`
  - **Description:** Get an intelligent summary for a database, including table size/replica statistics and schema details. Prioritizes large/high-impact tables first.
  - **Input:**
    ```json
    {
      "db": "database_name", // Optional if default database is set
      "limit": 10000, // Optional output length limit in characters
      "refresh": false // Optional, boolean. Force refresh if true
    }
    ```
  - **Output:** Text summary of database table inventory and schema hints, truncated by `limit`.

> Note: `db_overview` still exists in source as legacy logic but is currently not registered as an MCP tool.

### Resources

#### Direct Resources

- `starrocks:///databases`
  - **Description:** Lists all databases accessible to the configured user.
  - **Equivalent Query:** `SHOW DATABASES`
  - **MIME Type:** `text/plain`

#### Resource Templates

- `starrocks:///{db}/{table}/schema`

  - **Description:** Gets the schema definition of a specific table.
  - **Equivalent Query:** `SHOW CREATE TABLE {db}.{table}`
  - **MIME Type:** `text/plain`

- `starrocks:///{db}/tables`

  - **Description:** Lists all tables within a specific database.
  - **Equivalent Query:** `SHOW TABLES FROM {db}`
  - **MIME Type:** `text/plain`

- `proc:///{+path}`
  - **Description:** Accesses StarRocks internal system information, similar to Linux `/proc`. The `path` parameter specifies the desired information node.
  - **Equivalent Query:** `SHOW PROC '/{path}'`
  - **MIME Type:** `text/plain`
  - **Common Paths:**
    - `/frontends` - Information about FE nodes.
    - `/backends` - Information about BE nodes (for non-cloud native deployments).
    - `/compute_nodes` - Information about CN nodes (for cloud native deployments).
    - `/dbs` - Information about databases.
    - `/dbs/<DB_ID>` - Information about a specific database by ID.
    - `/dbs/<DB_ID>/<TABLE_ID>` - Information about a specific table by ID.
    - `/dbs/<DB_ID>/<TABLE_ID>/partitions` - Partition information for a table.
    - `/transactions` - Transaction information grouped by database.
    - `/transactions/<DB_ID>` - Transaction information for a specific database ID.
    - `/transactions/<DB_ID>/running` - Running transactions for a database ID.
    - `/transactions/<DB_ID>/finished` - Finished transactions for a database ID.
    - `/jobs` - Information about asynchronous jobs (Schema Change, Rollup, etc.).
    - `/statistic` - Statistics for each database.
    - `/tasks` - Information about agent tasks.
    - `/cluster_balance` - Load balance status information.
    - `/routine_loads` - Information about Routine Load jobs.
    - `/colocation_group` - Information about Colocation Join groups.
    - `/catalog` - Information about configured catalogs (e.g., Hive, Iceberg).

### Prompts

None defined by this server.

## Caching Behavior

- `table_overview` uses an in-memory cache keyed by `(database_name, table_name)`.
- If `refresh=false` (default) and cache exists, `table_overview` returns cached content directly.
- `db_summary` uses `DatabaseSummaryManager` cache:
  - Table metadata cache: `(database, table) -> TableInfo`
  - Per-database sync timestamp cache
  - Periodic refresh and prioritization for large tables
- `STARROCKS_OVERVIEW_LIMIT` acts as a soft size guard for overview output generation.
- Cached entries may include partial error information from previous fetch attempts.

## Debug

After starting mcp server, you can use inspector to debug:
```
npx @modelcontextprotocol/inspector
```

## Demo

![MCP Demo Image](mcpserverdemo.jpg)
