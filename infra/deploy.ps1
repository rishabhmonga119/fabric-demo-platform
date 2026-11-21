$ErrorActionPreference = 'Stop'
& "$PSScriptRoot\..\.venv\Scripts\python.exe" "$PSScriptRoot\deploy.py" @args
exit $LASTEXITCODE
