# find_python.ps1
# ================
# Encuentra Python 3.13+ 64-bit ESTANDAR o lo descarga e instala automaticamente.
# IGNORA la version free-threaded (3.13t) que no tiene wheels compatibles.
#
# Inno Setup lo llama desde [Run] pasando la ruta de instalacion como argumento.

param([string]$AppDir = "C:\Asistencia")

$PYTHON_VERSION = "3.13.11"
$PYTHON_URL     = "https://www.python.org/ftp/python/$PYTHON_VERSION/python-$PYTHON_VERSION-amd64.exe"
$LOG_FILE       = Join-Path $AppDir "logs\install.log"

New-Item -ItemType Directory -Path (Split-Path $LOG_FILE) -Force -ErrorAction SilentlyContinue | Out-Null

function Log($msg) {
    Write-Host $msg
    Add-Content -Path $LOG_FILE -Value $msg -ErrorAction SilentlyContinue
}

function Test-PythonValid {
    # Verifica: 64-bit Y NO free-threaded
    param([string]$PythonPath)
    if (-not (Test-Path $PythonPath)) { return $false }
    try {
        # Verificar 64-bit
        $bits = & $PythonPath -c "import struct; print(struct.calcsize('P')*8)" 2>&1
        if ($bits -notmatch '64') {
            Log "    SKIP: $PythonPath es 32-bit"
            return $false
        }
        # Verificar que NO es free-threaded (abiflags contiene 't')
        $abi = & $PythonPath -c "import sys; print(getattr(sys, 'abiflags', ''))" 2>&1
        if ($abi -match 't') {
            Log "    SKIP: $PythonPath es free-threaded (experimental, sin wheels)"
            return $false
        }
        return $true
    } catch {}
    return $false
}

function Find-Python {
    # 1. Ruta de instalacion por defecto (sistema) — la mas confiable
    $systemPath = "C:\Program Files\Python313\python.exe"
    if ((Test-Path $systemPath) -and (Test-PythonValid $systemPath)) {
        Log "  Python encontrado (sistema): $systemPath"
        return $systemPath
    }

    # 2. py.exe (lanzador oficial)
    try {
        $py = Get-Command py -ErrorAction Stop
        $ver = & py --version 2>&1
        if ($ver -match '3\.(1[3-9]|[2-9]\d)') {
            # py.exe puede lanzar la version free-threaded, verificar
            $abi = & py -c "import sys; print(getattr(sys, 'abiflags', ''))" 2>&1
            if ($abi -notmatch 't') {
                $bits = & py -c "import struct; print(struct.calcsize('P')*8)" 2>&1
                if ($bits -match '64') {
                    Log "  Python encontrado via py.exe: $($py.Path) ($ver, 64-bit)"
                    return $py.Path
                }
            } else {
                Log "  py.exe encontrado pero es free-threaded, saltando..."
            }
        }
    } catch {}

    # 3. Comando 'python' en PATH
    try {
        $python = Get-Command python -ErrorAction Stop
        $ver = & python --version 2>&1
        if ($ver -match '3\.(1[3-9]|[2-9]\d)') {
            if (Test-PythonValid $python.Path) {
                Log "  Python encontrado en PATH: $($python.Path) ($ver, 64-bit)"
                return $python.Path
            }
        }
    } catch {}

    # 4. Rutas conocidas (solo 64-bit, no free-threaded)
    $bases = @(
        "$env:LOCALAPPDATA\Programs\Python",
        "C:\",
        "C:\Program Files"
    )
    foreach ($base in $bases) {
        foreach ($ver in @("313","312","311")) {
            $candidate = Join-Path $base "Python$ver\python.exe"
            if ((Test-Path $candidate) -and (Test-PythonValid $candidate)) {
                Log "  Python encontrado en: $candidate"
                return $candidate
            }
        }
    }

    # 5. Registro de Windows
    $regRoots = @("HKLM:\SOFTWARE\Python\PythonCore", "HKCU:\SOFTWARE\Python\PythonCore")
    foreach ($root in $regRoots) {
        if (Test-Path $root) {
            foreach ($v in @("3.13","3.12","3.11")) {
                $keyPath = "$root\$v\InstallPath"
                if (Test-Path $keyPath) {
                    $installPath = (Get-ItemProperty $keyPath -ErrorAction SilentlyContinue).'(default)'
                    $candidate = "$installPath\python.exe"
                    if ($installPath -and (Test-Path $candidate) -and (Test-PythonValid $candidate)) {
                        Log "  Python encontrado en registro: $candidate"
                        return $candidate
                    }
                }
            }
        }
    }

    return $null
}

function Install-Python {
    Log ""
    Log "=== Python no encontrado. Descargando Python $PYTHON_VERSION 64-bit ==="
    Log "  URL: $PYTHON_URL"

    $installer = Join-Path $env:TEMP "python-$PYTHON_VERSION-amd64.exe"

    try {
        Log "  Descargando... (puede tardar 1-2 minutos)"
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        Invoke-WebRequest -Uri $PYTHON_URL -OutFile $installer -UseBasicParsing
        Log "  Descarga OK: $([math]::Round((Get-Item $installer).Length/1MB, 1)) MB"
    } catch {
        Log "  ERROR descargando: $_"
        return $null
    }

    # Instalar: sistema completo, 64-bit, con pip, sin tests
    $installArgs = "/quiet InstallAllUsers=1 PrependPath=1 Include_pip=1 Include_launcher=1 Include_test=0"
    Log "  Instalando Python $PYTHON_VERSION..."

    try {
        $proc = Start-Process -FilePath $installer -ArgumentList $installArgs -Wait -PassThru
        if ($proc.ExitCode -eq 0) {
            Log "  Instalacion exitosa."
        } else {
            Log "  Instalador termino con codigo $($proc.ExitCode)"
        }
    } catch {
        Log "  ERROR: $_"
        return $null
    }

    Remove-Item $installer -Force -ErrorAction SilentlyContinue

    # Refrescar PATH
    $env:PATH = [System.Environment]::GetEnvironmentVariable("PATH", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("PATH", "User")

    Start-Sleep -Seconds 2

    # Buscar en ruta por defecto
    $defaultPath = "C:\Program Files\Python313\python.exe"
    if ((Test-Path $defaultPath) -and (Test-PythonValid $defaultPath)) {
        Log "  Python listo en: $defaultPath"
        return $defaultPath
    }

    # Buscar de nuevo
    $found = Find-Python
    if ($found) { return $found }

    Log "  ERROR: Python no encontrado tras instalacion."
    return $null
}

# ─── MAIN ───────────────────────────────────────────────────────

Log ""
Log "=== Buscando Python 3.13+ 64-bit (estandar, no free-threaded) ==="

$pythonExe = Find-Python

if (-not $pythonExe) {
    $pythonExe = Install-Python
}

if (-not $pythonExe) {
    Add-Type -AssemblyName System.Windows.Forms
    [System.Windows.Forms.MessageBox]::Show(
        "No se pudo encontrar ni instalar Python 3.13 64-bit.`n`n" +
        "IMPORTANTE: Si tiene Python 'free-threaded' (experimental),`n" +
        "debe instalar la version ESTANDAR de Python 3.13.`n`n" +
        "Descargue desde: https://www.python.org/downloads/`n" +
        "Elija 'Windows installer (64-bit)' (NO la version experimental).`n`n" +
        "Luego vuelva a ejecutar el instalador.",
        "Python no encontrado",
        [System.Windows.Forms.MessageBoxButtons]::OK,
        [System.Windows.Forms.MessageBoxIcon]::Error
    ) | Out-Null
    exit 1
}

Log "Python seleccionado: $pythonExe"
$ver = & $pythonExe --version 2>&1
Log "Version: $ver"

# --- Ejecutar post_install.py ---
$postInstall = Join-Path $AppDir ".installer\post_install.py"

if (-not (Test-Path $postInstall)) {
    Add-Type -AssemblyName System.Windows.Forms
    [System.Windows.Forms.MessageBox]::Show(
        "Archivo de configuracion no encontrado:`n$postInstall`n`nReinstale la aplicacion.",
        "Error de instalacion",
        [System.Windows.Forms.MessageBoxButtons]::OK,
        [System.Windows.Forms.MessageBoxIcon]::Error
    ) | Out-Null
    exit 1
}

& $pythonExe $postInstall $AppDir
exit $LASTEXITCODE
