# Path to your conduit server directory
$ServerDir = "C:\path\to\conduit\server"

# To run this script from anywhere, add the following line to your $PROFILE:
# function conduit { & "C:\path\to\conduit\server\start.ps1" }
# Then reload: . $PROFILE
# Usage: conduit

$python = "$ServerDir\.venv\Scripts\python.exe"
$script = "$ServerDir\main.py"

Write-Host "Starting conduit server..."
& $python $script
