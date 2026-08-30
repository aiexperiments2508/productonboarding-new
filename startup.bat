@echo off
REM ===========================================================================
REM  Autonomous Product Intelligence Factory - Windows launcher
REM
REM    startup.bat          production: one process serving the API and the
REM                         pre-built UI together.  http://127.0.0.1:8100
REM    startup.bat dev      development: backend with autoreload in this
REM                         window, Vite dev server in a second one.
REM    startup.bat build    rebuild the frontend, then run production.
REM    startup.bat clean    reinstall frontend dependencies, rebuild, run.
REM    startup.bat reset    wipe the database and reload the seed pack.
REM    startup.bat studio   LangGraph Studio dev server on :2024 (optional).
REM
REM  No Docker. The only hard requirement is Python; the frontend ships
REM  pre-built in frontend\dist, so Node is needed only for `dev` and `build`.
REM  When it is needed it must be Node 20 or newer: the UI compiles its CSS
REM  with Tailwind v4, whose compiler is a native addon needing Node 20 up.
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

REM Read the port and gateway settings out of .env so the banner and the
REM browser open on the right address.
set "API_PORT=8100"
set "EXTERNAL_GATEWAY="
if exist ".env" (
    for /f "usebackq eol=# tokens=1,* delims==" %%A in (".env") do (
        if /i "%%A"=="API_PORT" set "API_PORT=%%B"
        if /i "%%A"=="LITELLM_BASE_URL" set "EXTERNAL_GATEWAY=%%B"
    )
)
REM Trim stray spaces picked up from the file.
for /f "tokens=* delims= " %%A in ("!API_PORT!") do set "API_PORT=%%A"

REM Refuse to start on a port somebody else already owns. Without this the
REM server fails to bind, the browser opens anyway, and whatever was already
REM listening answers - which looks exactly like this app booting the wrong
REM code. It is a genuinely confusing five minutes, and worth one check.
set "PORT_OWNER="
for /f "tokens=5" %%P in ('netstat -ano -p TCP ^| findstr /r /c:"LISTENING" ^| findstr /r /c:":!API_PORT! "') do set "PORT_OWNER=%%P"
if defined PORT_OWNER (
    echo.
    echo  [X] Port !API_PORT! is already in use by process !PORT_OWNER!.
    echo.
    echo      Something is already serving that address, and it is not this
    echo      run. Opening the browser now would show you that other app.
    echo.
    echo      Check what it is:   tasklist /fi "pid eq !PORT_OWNER!"
    echo      Stop it:            taskkill /pid !PORT_OWNER! /f
    echo      Or set a different API_PORT in .env
    echo.
    goto :fail
)

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

REM --- 7. modes ---------------------------------------------------------------
if /i "%MODE%"=="reset"  goto :reset
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


:reset
echo  [.] Resetting the database and reloading the seed pack ...
"%VPY%" scripts\generate_data.py
if errorlevel 1 goto :fail
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
echo  editing the UI. Close both windows to stop.
echo.
start "Product Intelligence Factory - frontend" cmd /k "cd /d "%~dp0frontend" && npm.cmd run dev"
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
echo.
echo  UI and API:  http://127.0.0.1:!API_PORT!
echo.
echo  Ctrl-K / Cmd-K   command palette: jump, drive the replay, search the corpus
echo  Status bar       replay transport, on screen from every view
echo  Top right        theme ^(light / dark / system^), density, accent
echo.
echo  Ctrl-C to stop
echo.
start "" "http://127.0.0.1:!API_PORT!"
"%VPY%" run.py !GATEWAY_FLAG!
goto :done


REM --- helpers ----------------------------------------------------------------
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
