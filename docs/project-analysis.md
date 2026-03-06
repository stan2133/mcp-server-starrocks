# mcp-server-starrocks 项目文档（源码分析版）

分析日期：2026-03-06  
分析范围：`mcp-server-starrocks` 仓库当前代码（`src/`、`tests/`、`pyproject.toml`、`README.md`）

## 1. 项目定位

`mcp-server-starrocks` 是一个基于 MCP（Model Context Protocol）的 StarRocks 连接服务，目标是让 AI Agent 通过标准 MCP 工具/资源访问 StarRocks，完成：

- SQL 读写执行
- 数据库与表结构探索
- 查询可视化（Plotly）
- 数据库摘要（按表大小和副本优先级）
- 查询诊断信息收集（query dump/profile）

## 2. 技术栈与依赖

核心技术：

- Python >= 3.10
- FastMCP（MCP 工具与资源注册）
- mysql-connector-python（MySQL 协议连接 StarRocks）
- ADBC + Flight SQL（可选高性能连接）
- pandas / plotly / kaleido（查询结果可视化）
- loguru（日志）

依赖入口：`pyproject.toml`  
命令入口：`mcp-server-starrocks = "mcp_server_starrocks:main"`

## 3. 目录结构与职责

```text
mcp-server-starrocks/
├── src/mcp_server_starrocks/
│   ├── __init__.py                    # 命令入口，调用 async main
│   ├── server.py                      # MCP tools/resources 注册，启动逻辑
│   ├── db_client.py                   # 连接管理、SQL执行、结果封装
│   ├── db_summary_manager.py          # 数据库摘要缓存与格式化输出
│   └── connection_health_checker.py   # 后台连接健康检查线程
├── tests/
│   └── test_db_client.py              # DBClient/ResultSet/URL 解析/ArrowFlight 测试
├── README.md                          # 用户接入文档
├── RELEASE_NOTES.md                   # 发布记录
└── pyproject.toml                     # 包配置
```

## 4. 运行模式与启动方式

支持传输模式：

- `stdio`（默认）
- `streamable-http`（推荐）
- `http`
- `sse`（代码仍支持，但 README 标注已废弃）

启动参数（`server.py`）：

- `--mode {stdio,sse,http,streamable-http}`
- `--host`（HTTP 模式生效）
- `--port`（HTTP 模式生效）
- `--test`（仅做连通性测试）

示例：

```bash
# 连通性测试
STARROCKS_URL=root:@localhost:8000 uv run mcp-server-starrocks --test

# Streamable HTTP 模式
uv run mcp-server-starrocks --mode streamable-http --host 0.0.0.0 --port 8080
```

## 5. 配置项（源码实际）

### 5.1 连接配置

- `STARROCKS_URL`：优先于分散参数。格式 `[schema://]user[:password]@host[:port][/database]`
- `STARROCKS_HOST`：默认 `localhost`
- `STARROCKS_PORT`：默认 `9030`
- `STARROCKS_USER`：默认 `root`
- `STARROCKS_PASSWORD`：默认空
- `STARROCKS_DB`：默认数据库（可为空）
- `STARROCKS_MYSQL_AUTH_PLUGIN`：默认 `mysql_native_password`

### 5.2 执行与连接行为

- `STARROCKS_POOL_SIZE`：MySQL 连接池大小，默认 `10`
- `STARROCKS_CONNECTION_TIMEOUT`：连接超时（秒），默认 `10`
- `STARROCKS_USE_PURE`：mysql connector pure 模式，默认 `false`
- `STARROCKS_FE_ARROW_FLIGHT_SQL_PORT`：设置后启用 Arrow Flight SQL
- `STARROCKS_DUMMY_TEST`：非空即启用 dummy 数据模式

### 5.3 摘要/服务配置

- `STARROCKS_OVERVIEW_LIMIT`：摘要文本软限制，默认 `20000`
- `MCP_TRANSPORT_MODE`：默认传输模式（默认 `stdio`）
- `LOG_LEVEL`：日志级别（默认 `INFO`）

## 6. MCP 能力清单（以 `server.py` 注册为准）

### 6.1 Tools

- `read_query`
  - 执行返回 ResultSet 的语句（SELECT/SHOW/DESCRIBE 等）
  - 返回 `ToolResult`：文本 + `structured_content`

- `write_query`
  - 执行 DDL/DML 等无结果集语句
  - 成功时返回受影响行数/耗时

- `analyze_query`
  - `uuid` 存在：执行 `ANALYZE PROFILE FROM '<uuid>'`
  - 否则若 `sql` 存在：执行 `EXPLAIN ANALYZE <sql>`

- `collect_query_dump_and_profile`
  - 获取 query dump、query profile、analyze profile
  - 输出较大，主要供工具链进一步处理

- `query_and_plotly_chart`
  - SQL -> DataFrame -> Plotly 图形
  - `format` 支持 `json|png|jpeg`（`jpg` 会被转成 `jpeg`）
  - `plotly_expr` 通过 AST 校验后 `eval`

- `table_overview`
  - 输出单表行数、列信息、样例数据
  - 使用全局内存缓存 `(db, table)`，支持 `refresh`

- `db_summary`
  - 输出数据库级摘要（表大小、副本、字段等）
  - 由 `DatabaseSummaryManager` 维护缓存与排序策略

说明：`db_overview` 函数仍在代码中，但装饰器被注释，当前不会作为 MCP tool 暴露。

### 6.2 Resources

- `starrocks:///databases`：列出数据库
- `starrocks:///{db}/{table}/schema`：`SHOW CREATE TABLE`
- `starrocks:///{db}/tables`：列出表
- `proc:///{path*}`：`SHOW PROC '/path'` 系统信息

## 7. 核心架构与执行链路

总体链路：

1. `FastMCP` 在 `server.py` 注册 tools/resources  
2. tool 调用 `db_client.execute()` 或 `collect_perf_analysis_input()`  
3. `DBClient` 根据环境选择 MySQL Pool 或 Arrow Flight SQL  
4. 执行结果封装为 `ResultSet` 或 `ToolResult` 返回 MCP 客户端

连接与健康机制：

- MySQL 模式：连接池 + `ping(reconnect=True)` 校验
- Flight 模式：单例 ADBC 连接 + `adbc_get_info()` 健康检查
- 后台线程每 30 秒执行 `show databases` 做健康探测

## 8. 缓存与摘要策略

### 8.1 表级 overview 缓存

- 全局字典 `global_table_overview_cache`
- 键：`(database, table)`
- 值：overview 文本（包括错误文本）
- `table_overview(refresh=True)` 可强制刷新

### 8.2 数据库 summary 缓存

`DatabaseSummaryManager` 维护：

- `table_cache[(db, table)] -> TableInfo`
- `db_last_sync[db] -> timestamp`

关键策略：

- 每 120 秒（或 `refresh=True`）重做 `SHOW DATA` 同步表清单
- 优先展示“大表”（副本数 > 64 或 > 2GB）
- 大表最多取前 10 个 `SHOW CREATE TABLE`
- 字段信息批量从 `information_schema.columns` 拉取
- 输出受 `limit` 控制，按优先级截断

## 9. 测试现状

测试文件：`tests/test_db_client.py`

覆盖点：

- DBClient 初始化、连接、异常处理
- MySQL 与 Arrow Flight SQL 两种模式
- `ResultSet` 转字符串/转 DataFrame
- `parse_connection_url` 多种 URL 解析场景
- `STARROCKS_DUMMY_TEST` 行为

执行方式：

```bash
uv run pytest tests/test_db_client.py -v
```

## 10. 已知限制与风险

1. 文档与实现存在轻微偏差  
当前代码暴露 `db_summary` 与 `collect_query_dump_and_profile`，但 README 的工具说明主要仍围绕 `db_overview`。

2. `STARROCKS_URL` 解析能力有限  
`parse_connection_url()` 基于正则，对带 `@` 的密码/用户名支持不完整（测试中也明确了该限制）。

3. `query_and_plotly_chart` 使用受限 `eval`  
虽然做了 AST 校验并限制 `px.*` 单调用，但仍建议在高安全环境进一步收敛表达式能力或使用白名单映射。

4. HTTP 模式默认 CORS 全开放  
当前 `allow_origins=["*"]` 适合开发环境，生产建议改为受控域名。

5. 健康检查线程固定周期探活  
高并发或多实例场景下可考虑可配置化间隔、失败退避策略和指标上报。

## 11. 建议的维护与演进方向

1. 对齐 README 与真实 tool 列表（补充 `db_summary`、`collect_query_dump_and_profile`、`format` 参数）。  
2. 将连接 URL 解析改为标准 URL parser（并增加 URL encode 场景测试）。  
3. 给 `query_and_plotly_chart` 增加 plotly API 白名单和输出大小限制。  
4. 为 `db_summary_manager` 增加单元测试（缓存同步、排序、截断逻辑）。  
5. 将 CORS、健康检查间隔、探活 SQL 提升为可配置项。  

## 12. 快速上手（开发者视角）

```bash
# 1) 安装依赖
uv sync

# 2) 连通性测试（建议先用 URL 模式）
STARROCKS_URL=root:@localhost:9030 uv run mcp-server-starrocks --test

# 3) 启动服务（HTTP）
STARROCKS_URL=root:@localhost:9030 uv run mcp-server-starrocks --mode streamable-http --port 8000

# 4) MCP 客户端配置
# endpoint: http://localhost:8000/mcp
```

