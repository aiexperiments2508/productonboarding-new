@echo off
REM ===========================================================================
REM  Autonomous Product Intelligence Factory - Windows launcher
REM
REM    startup.bat          production: the platform, plus the three connected
REM                         applications, each in its own window.
REM    startup.bat solo     the platform only, no connected applications.
REM    startup.bat dev      development: backend with autoreload in this
REM                         window, Vite dev server in a second one.
REM    startup.bat build    rebuild the frontend, then run production.
REM    startup.bat clean    reinstall frontend dependencies, rebuild, run.
REM    startup.bat reset    wipe the database and reload the seed pack.
REM    startup.bat stage    put two products on sale, ready for a late change.
REM    startup.bat studio   LangGraph Studio dev server on :2024 (optional).
REM    startup.bat graph    fetch Neo4j, unpack it, and load the knowledge
REM                         graph into it. Once, then `startup.bat` as usual.
REM
REM  FIVE processes, on six ports:
REM
REM    8000   the platform  - API, the UI, and every MCP server
REM    8110   Vendor Portal - upstream. Suppliers push corrections in here.
REM    8120   Storefront    - downstream. What a shopper sees.
REM    8130   Ops Console   - downstream. Print, shelf, search, errata.
REM    8140   Back Office   - reference. Stock, trading, campaigns, certificates.
REM    7474   Neo4j browser - optional. Only if neo4j\ has been unpacked.
REM    7687   Neo4j bolt    - optional. What the loader and the API speak.
REM
REM  The three connected applications reach the platform over MCP and by no
REM  other route - they have no database and no access to its API. That is the
REM  reason they are separate processes rather than three more tabs, and it is
REM  why they can be started, stopped and restarted independently.
REM
REM  No Docker. The only hard requirement is Python; the frontend ships
REM  pre-built in frontend\dist, so Node is needed only for `dev` and `build`.
REM  When it is needed it must be Node 20 or newer: the UI compiles its CSS
REM  with Tailwind v4, whose compiler is a native addon needing Node 20 up.
REM
REM  Neo4j is no exception to that. It is a zip with a batch file in it, and on
REM  a machine with a JDK 17 or 21 it needs nothing else - `startup.bat graph`
REM  fetches and unpacks it into neo4j\, and this script starts it from there
REM  whenever it finds it. Nothing here requires it: with no Neo4j at all the
REM  Knowledge Graph tab walks the same projection in process, and every
REM  response says which engine answered.
REM ===========================================================================

setlocal enabledelayedexpansion
cd /d "%~dp0"

REM UTF-8 console. Several dependencies print emoji in their banners, and the
REM default Windows codepage (cp1252) cannot encode them - the process dies on
REM a UnicodeEncodeError while writing its own startup message. Setting both
REM the codepage and PYTHONIOENCODING makes that a non-issue.
chcp 65001 >nul 2>&1
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"

set "MODE=%~1"
if "%MODE%"=="" set "MODE=run"

echo.
echo  Product Intelligence Factory
echo  ----------------------------

REM --- 1. locate a Python -----------------------------------------------------
REM The LiteLLM proxy cannot install on 3.14 (orjson has no wheel and its Rust
REM build fails against that ABI), so prefer 3.12 when the launcher has to pick.
set "PY="
for %%V in (3.12 3.13 3.11) do (
    if not defined PY (
        py -%%V -c "import sys" >nul 2>&1 && set "PY=py -%%V"
    )
)
if not defined PY (
    python -c "import sys" >nul 2>&1 && set "PY=python"
)
if not defined PY (
    echo  [X] No Python found on PATH.
    echo      Install Python 3.12 from https://python.org and re-run this script.
    goto :fail
)

for /f "delims=" %%v in ('%PY% -c "import sys;print('.'.join(map(str,sys.version_info[:2])))"') do set "PYVER=%%v"
echo  [.] Python !PYVER!  ^(%PY%^)

REM --- 2. virtual environment -------------------------------------------------
if not exist ".venv\Scripts\python.exe" (
    echo  [.] Creating virtual environment ...
    %PY% -m venv .venv
    if errorlevel 1 (
        echo  [X] Could not create .venv
        goto :fail
    )
    set "FRESH_VENV=1"
)
set "VPY=.venv\Scripts\python.exe"

REM --- 3. application dependencies --------------------------------------------
"%VPY%" -c "import fastapi, langgraph, numpy" >nul 2>&1
if errorlevel 1 set "FRESH_VENV=1"

if defined FRESH_VENV (
    echo  [.] Installing dependencies ^(a few minutes the first time^) ...
    "%VPY%" -m pip install --upgrade pip --quiet
    "%VPY%" -m pip install -r requirements.txt --quiet
    if errorlevel 1 (
        echo  [X] Dependency install failed - see the output above.
        goto :fail
    )
)
echo  [.] Dependencies ready

REM --- 4. configuration -------------------------------------------------------
if not exist ".env" (
    if exist ".env.example" (
        copy /y ".env.example" ".env" >nul
        echo  [!] Created .env from .env.example - point it at a model gateway.
    )
)

REM Read the ports and gateway settings out of .env so the banner and the
REM browser open on the right addresses. The defaults here have to match
REM .env.example, or a machine with no .env gets a different estate.
set "API_PORT=8000"
set "VENDOR_PORT=8110"
set "STOREFRONT_PORT=8120"
set "OPS_PORT=8130"
set "BACKOFFICE_PORT=8140"
set "EXTERNAL_GATEWAY="
if exist ".env" (
    for /f "usebackq eol=# tokens=1,* delims==" %%A in (".env") do (
        if /i "%%A"=="API_PORT" set "API_PORT=%%B"
        if /i "%%A"=="VENDOR_PORT" set "VENDOR_PORT=%%B"
        if /i "%%A"=="STOREFRONT_PORT" set "STOREFRONT_PORT=%%B"
        if /i "%%A"=="OPS_PORT" set "OPS_PORT=%%B"
        if /i "%%A"=="BACKOFFICE_PORT" set "BACKOFFICE_PORT=%%B"
        if /i "%%A"=="LITELLM_BASE_URL" set "EXTERNAL_GATEWAY=%%B"
    )
)
REM Trim stray spaces picked up from the file.
for /f "tokens=* delims= " %%A in ("!API_PORT!") do set "API_PORT=%%A"
for /f "tokens=* delims= " %%A in ("!VENDOR_PORT!") do set "VENDOR_PORT=%%A"
for /f "tokens=* delims= " %%A in ("!STOREFRONT_PORT!") do set "STOREFRONT_PORT=%%A"
for /f "tokens=* delims= " %%A in ("!OPS_PORT!") do set "OPS_PORT=%%A"
for /f "tokens=* delims= " %%A in ("!BACKOFFICE_PORT!") do set "BACKOFFICE_PORT=%%A"

REM  only unpacks a zip and installs a driver - it binds nothing, so it
REM is dispatched before the port checks. Refusing to fetch Neo4j because the
REM platform is already running would be a confusing way to fail.
if /i "%MODE%"=="graph" goto :graph

REM Refuse to start on a port somebody else already owns. Without this the
REM server fails to bind, the browser opens anyway, and whatever was already
REM listening answers - which looks exactly like this app booting the wrong
REM code. It is a genuinely confusing five minutes, and worth one check.
REM Four ports now, and each one is checked by name so the message says which
REM application could not have its address rather than only which number.
call :check_port "!API_PORT!" "the platform" "API_PORT"
if errorlevel 1 goto :fail
if /i not "%MODE%"=="solo" (
    call :check_port "!VENDOR_PORT!" "the Vendor Portal" "VENDOR_PORT"
    if errorlevel 1 goto :fail
    call :check_port "!STOREFRONT_PORT!" "the Storefront" "STOREFRONT_PORT"
    if errorlevel 1 goto :fail
    call :check_port "!OPS_PORT!" "the Ops Console" "OPS_PORT"
    call :check_port "!BACKOFFICE_PORT!" "the Back Office" "BACKOFFICE_PORT"
    if errorlevel 1 goto :fail
)

REM Neo4j is deliberately not port-checked. The check exists so this script
REM never starts a server over somebody else's; an already-running Neo4j is
REM the one case where the thing on the port is exactly what we want, and
REM :start_neo4j steps aside for it.

REM --- 5. gateway -------------------------------------------------------------
REM Two ways to reach models: attach to a gateway that is already running, or
REM start one here. Attaching needs nothing installed, which is why the proxy
REM is a separate requirements file - it cannot install on Python 3.14.
set "GATEWAY_FLAG="
if defined EXTERNAL_GATEWAY (
    REM No flag needed: run.py sees LITELLM_BASE_URL and attaches by itself.
    REM Passing --no-gateway here would make it report "skipping gateway"
    REM instead of naming the gateway it is actually talking to.
    echo  [.] Attaching to the gateway at !EXTERNAL_GATEWAY!
) else (
    "%VPY%" -c "import litellm.proxy.proxy_cli" >nul 2>&1
    if errorlevel 1 (
        echo  [.] Installing the LiteLLM gateway ...
        "%VPY%" -m pip install -r requirements-gateway.txt --quiet
        if errorlevel 1 (
            echo.
            echo  [!] The gateway could not be installed on Python !PYVER!.
            echo      On 3.14 this is expected: orjson has no wheel and its Rust
            echo      build fails against that ABI.
            echo.
            echo      The app will still start, and every model step falls back
            echo      to a deterministic path. To get live model calls, either:
            echo        - install Python 3.12, delete .venv, re-run this script; or
            echo        - point LITELLM_BASE_URL in .env at a gateway elsewhere.
            echo.
            set "GATEWAY_FLAG=--no-gateway"
        )
    )
)

REM --- 6. seed data -----------------------------------------------------------
REM Keyed on catalog.json, the file the generator actually writes. This used to
REM name network.json, which the current generator deletes - so the check was
REM always true and the pack was rebuilt on every single boot.
if not exist "data\catalog.json" (
    echo  [.] Generating the seed pack ...
    "%VPY%" scripts\generate_data.py
    if errorlevel 1 goto :fail
)

REM The supplier data pack: the templates a supplier fills in, derived from the
REM attribute registry and the retailer profile. Keyed on the workbook because
REM it is the last file the builder writes. Never fatal - the pack is what the
REM vendor portal hands out, and a platform that would not boot because a
REM spreadsheet library is missing would be trading a whole demo for one
REM download.
if not exist "data\datapack\supplier-feed.xlsx" (
    echo  [.] Building the supplier data pack ...
    "%VPY%" scripts\build_datapack.py
    if errorlevel 1 echo  [!] the data pack was not built - the portal will
    if errorlevel 1 echo      generate templates on demand instead
)

REM --- 7. modes ---------------------------------------------------------------
if /i "%MODE%"=="reset"  goto :reset
if /i "%MODE%"=="stage"  goto :stage
if /i "%MODE%"=="solo"   goto :run
if /i "%MODE%"=="build"  goto :build
if /i "%MODE%"=="clean"  goto :clean
if /i "%MODE%"=="dev"    goto :dev
if /i "%MODE%"=="studio" goto :studio
goto :run


:clean
REM node_modules only. frontend\dist is a committed artifact and this tree is
REM not necessarily under version control, so the build overwrites it in place
REM rather than this deleting it first - a failed build must not be able to
REM leave the lab with no UI at all.
if exist "frontend\node_modules" (
    echo  [.] Removing frontend\node_modules ...
    rmdir /s /q "frontend\node_modules"
)
goto :build


:build
call :ensure_node
if errorlevel 1 goto :fail
call :ensure_frontend_deps
if errorlevel 1 goto :fail
echo  [.] Building the frontend ...
pushd frontend
call npm.cmd run build
if errorlevel 1 ( popd & echo  [X] Frontend build failed. & goto :fail )
popd
echo  [.] Frontend built into frontend\dist
goto :run


:studio
"%VPY%" -c "import langgraph_cli" >nul 2>&1
if errorlevel 1 (
    echo  [.] Installing LangGraph Studio ...
    "%VPY%" -m pip install -r requirements-studio.txt --quiet
    if errorlevel 1 (
        echo  [X] Could not install langgraph-cli.
        goto :fail
    )
)
REM Studio can run the graph but has no replay controls, so put the system in
REM its demo position first - otherwise it opens on a quiet network and the
REM graph correctly finds nothing to do.
echo  [.] Preparing the demo state ...
"%VPY%" scripts\prepare_demo.py
if errorlevel 1 goto :fail

echo.
echo  LangGraph Studio
echo  ----------------
echo  Local API : http://127.0.0.1:2024
echo  Studio UI : https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:2024
echo.
echo  The Studio UI needs a LangSmith sign-in ^(free tier^). The graph runs
echo  locally either way - Studio is only the view.
echo.
echo  Ctrl-C to stop
echo.
"%VPY%" -m langgraph_cli dev --port 2024
goto :done


:stage
REM Two products on sale, so the late change has something to be late for.
REM Every listing in the seed pack is PREPARED - which is right for the arc the
REM tape tells and wrong for this one, which is about a correction arriving
REM after a launch.
echo  [.] Putting two products on sale ...
"%VPY%" scripts\stage_launch.py --press
if errorlevel 1 goto :fail
echo.
echo  Staged. Send the late change from the Vendor Portal, or re-run with:
echo    .venv\Scripts\python.exe scripts\stage_launch.py --press --inject
echo.
goto :run


:reset
echo  [.] Resetting the database and reloading the seed pack ...
"%VPY%" scripts\generate_data.py
if errorlevel 1 goto :fail
"%VPY%" scripts\build_datapack.py
echo.
echo  UI and API:  http://127.0.0.1:!API_PORT!
echo  Ctrl-C to stop
echo.
"%VPY%" run.py --reset !GATEWAY_FLAG!
goto :done


:dev
call :ensure_node
if errorlevel 1 goto :fail
call :ensure_frontend_deps
if errorlevel 1 goto :fail
echo.
echo  Starting BACKEND  http://127.0.0.1:!API_PORT!   ^(this window^)
echo  Starting FRONTEND http://127.0.0.1:5173         ^(new window, hot reload^)
echo.
echo  The Vite dev server proxies /api to the backend, so use :5173 while
echo  editing the UI. Close the windows to stop.
echo.
start "Product Intelligence Factory - frontend" cmd /k "cd /d "%~dp0frontend" && npm.cmd run dev"
call :start_satellites
timeout /t 2 /nobreak >nul
start "" "http://127.0.0.1:5173"
"%VPY%" run.py --reload !GATEWAY_FLAG!
goto :done


:run
REM Flat rather than one big parenthesised block: `call`, `goto` and `&` all
REM parse differently once they are nested inside `if (...)`, and this branch
REM is the one nobody exercises until the day dist is missing.
if exist "frontend\dist\index.html" goto :serve

echo  [!] No built frontend found.
call :ensure_node
if errorlevel 1 (
    echo  [X] frontend\dist is missing and Node is not available to build it.
    echo      Restore the built dist, or install Node 20+ and run:
    echo        startup.bat build
    goto :fail
)
call :ensure_frontend_deps
if errorlevel 1 goto :fail
echo  [.] Building the frontend ...
pushd frontend
call npm.cmd run build
if errorlevel 1 ( popd & echo  [X] Frontend build failed. & goto :fail )
popd

:serve
if /i not "%MODE%"=="solo" call :start_satellites
call :start_neo4j

echo.
echo  Platform       http://127.0.0.1:!API_PORT!        API, UI, MCP servers
if /i not "%MODE%"=="solo" (
    echo  Vendor Portal  http://127.0.0.1:!VENDOR_PORT!        upstream - suppliers push here
    echo  Storefront     http://127.0.0.1:!STOREFRONT_PORT!        downstream - what a shopper sees
    echo  Ops Console    http://127.0.0.1:!OPS_PORT!        downstream - print, shelf, errata
    echo  Back Office    http://127.0.0.1:!BACKOFFICE_PORT!        reference - stock, trading, campaigns, certificates
    echo.
    echo  The four connected applications reach the platform over MCP and by no
    echo  other route. They open inside Product Lifecycle, or on their own.
)
if defined NEO4J_STARTED echo  Neo4j          http://127.0.0.1:7474        the knowledge graph, bolt on 7687
echo.
echo  Ctrl-K / Cmd-K   command palette: jump, drive the replay, search the corpus
echo  Status bar       replay transport, on screen from every view
echo  Top right        theme ^(light / dark / system^), density, accent
echo.
echo  Ctrl-C stops the platform. Close the other windows to stop those.
echo.
start "" "http://127.0.0.1:!API_PORT!"
"%VPY%" run.py !GATEWAY_FLAG!
goto :done


:graph
REM Fetch Neo4j and load the graph into it. Run once; after that plain
REM `startup.bat` starts it alongside everything else.
REM
REM The loader needs the platform running, because it does not read the
REM database - it dials the four back-office systems on their own MCP
REM endpoints and MERGEs what they answer with. So this starts Neo4j, waits
REM for it, and tells you to run the loader once the platform is up.
echo.
echo  [.] Fetching Neo4j ^(no Docker; needs a JDK 17 or 21^) ...
"%VPY%" scripts\get_neo4j.py
if errorlevel 1 goto :fail
echo.
echo  [.] Installing the Neo4j driver ...
"%VPY%" -m pip install -q -r requirements-graph.txt
if errorlevel 1 goto :fail
echo.
echo  Neo4j is unpacked. Now:
echo    1. put NEO4J_URI, NEO4J_USER and NEO4J_PASSWORD in .env
echo    2. startup.bat            ^(starts Neo4j with everything else^)
echo    3. python scripts\load_graph.py   ^(with the platform running^)
echo.
echo  Step 3 needs the platform up because the loader crosses MCP rather than
echo  reading the database. `--offline` reads SQLite instead, and says so.
goto :done


REM --- helpers ----------------------------------------------------------------
:start_neo4j
REM Optional, and silent about it when absent.
REM
REM Started here rather than left to the reader because a graph database that
REM has to be launched by hand is a graph database the tab quietly falls back
REM from, and "why is it saying backend: memory" is a worse five minutes than
REM one more window. If neo4j\ is not unpacked this prints one line and moves
REM on - the tab works either way.
set "NEO4J_STARTED="
if not exist "neo4j\bin\neo4j.bat" (
    echo  [.] No local Neo4j - the Knowledge Graph tab will walk the graph in
    echo      process. `startup.bat graph` fetches one ^(no Docker needed^).
    exit /b 0
)
where java >nul 2>&1
if errorlevel 1 (
    echo  [!] neo4j\ is unpacked but there is no java on PATH, so it cannot
    echo      start. Neo4j 5 needs a JDK 17 or 21. The tab still works.
    exit /b 0
)
echo  [.] Starting Neo4j ...
start "Neo4j - knowledge graph" cmd /k "cd /d "%~dp0" && neo4j\bin\neo4j.bat console"
set "NEO4J_STARTED=1"
exit /b 0


:start_satellites
REM The four connected applications, each in its own window.
REM
REM Their own windows rather than one supervisor, deliberately: each is a
REM separate system and each keeps its own log, so "the Storefront cannot reach
REM the platform" is one window saying so rather than three interleaved
REM streams. They share this venv - they are Python, and their only dependency
REM beyond the standard library is the MCP client the platform already needs.
REM
REM They tolerate the platform not being up yet. Each dials on its first call
REM and reconnects afterwards, so start order does not matter and restarting
REM the platform mid-demo does not require restarting these.
echo  [.] Starting the connected applications ...
start "Vendor Portal - upstream" cmd /k "cd /d "%~dp0" && .venv\Scripts\python.exe -m apps.vendor.server"
start "Storefront - downstream" cmd /k "cd /d "%~dp0" && .venv\Scripts\python.exe -m apps.storefront.server"
start "Ops Console - downstream" cmd /k "cd /d "%~dp0" && .venv\Scripts\python.exe -m apps.ops.server"
start "Back Office - reference" cmd /k "cd /d "%~dp0" && .venv\Scripts\python.exe -m apps.backoffice.server"
exit /b 0


:check_port
REM %~1 port, %~2 what wants it, %~3 the .env key that moves it.
REM
REM Refusing to start beats binding failure. Without this the server fails to
REM bind, the browser opens anyway, and whatever was already listening answers -
REM which looks exactly like this app booting the wrong code.
set "PORT_OWNER="
for /f "tokens=5" %%P in ('netstat -ano -p TCP ^| findstr /r /c:"LISTENING" ^| findstr /r /c:":%~1 "') do set "PORT_OWNER=%%P"
if not defined PORT_OWNER exit /b 0
echo.
echo  [X] Port %~1, which %~2 needs, is held by process !PORT_OWNER!.
echo.
echo      Check what it is:   tasklist /fi "pid eq !PORT_OWNER!"
echo      Stop it:            taskkill /pid !PORT_OWNER! /f
echo      Or set a different %~3 in .env
echo.
exit /b 1


:ensure_node
where npm.cmd >nul 2>&1
if errorlevel 1 (
    echo  [X] Node/npm not found on PATH - needed for dev and build.
    echo      Plain 'startup.bat' still works: frontend\dist ships pre-built.
    exit /b 1
)

REM Version matters here, and it did not used to. Tailwind v4 compiles the
REM stylesheet in a native addon that requires Node 20 or newer, and Vite 6
REM rules out 19 and 21. Below that floor `npm install` appears to succeed and
REM the build then fails on the CSS step - a confusing place to learn that.
set "NODEMAJOR="
for /f "tokens=1 delims=." %%a in ('node --version 2^>nul') do set "NODEMAJOR=%%a"
set "NODEMAJOR=!NODEMAJOR:v=!"
if not defined NODEMAJOR (
    echo  [X] npm is on PATH but `node --version` did not run.
    exit /b 1
)
if !NODEMAJOR! LSS 20 (
    echo  [X] Node !NODEMAJOR! is too old - the UI build needs Node 20 or newer.
    echo      Install Node 22 LTS from https://nodejs.org, or skip the build:
    echo      frontend\dist ships pre-built, so plain 'startup.bat' still works.
    exit /b 1
)
exit /b 0


:ensure_frontend_deps
REM node_modules EXISTING is not the same as node_modules being CURRENT, and
REM the old check could not tell the difference. The UI gained Tailwind and
REM Radix in the enterprise revamp, so a tree installed before that is present,
REM stale, and fails the build with a module-not-found that looks nothing like
REM "your dependencies are out of date". Check for what the build imports.
set "DEPS_OK=1"
if not exist "frontend\node_modules"                   set "DEPS_OK="
if not exist "frontend\node_modules\react"             set "DEPS_OK="
if not exist "frontend\node_modules\vite"              set "DEPS_OK="
if not exist "frontend\node_modules\tailwindcss"       set "DEPS_OK="
if not exist "frontend\node_modules\@tailwindcss\vite" set "DEPS_OK="
if not exist "frontend\node_modules\radix-ui"          set "DEPS_OK="
REM The Tailwind compiler is a platform-specific native binding, so a
REM node_modules copied from another machine or another OS carries the wrong
REM one and only fails at build time. npm install is idempotent; a spurious
REM run costs a second, a missed one costs a confusing failure.
if not exist "frontend\node_modules\@tailwindcss\oxide-win32-*" set "DEPS_OK="

if defined DEPS_OK (
    echo  [.] Frontend dependencies ready
    exit /b 0
)
echo  [.] Installing frontend dependencies ...
pushd frontend
call npm.cmd install --no-audit --no-fund
if errorlevel 1 (
    popd
    echo  [X] npm install failed - see the output above.
    exit /b 1
)
popd
exit /b 0

:fail
echo.
echo  Startup failed. See the messages above.
pause
exit /b 1

:done
endlocal
