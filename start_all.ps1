# Script de démarrage global IKAN AI — Connecté à Render PostgreSQL
Write-Host "==================================================" -ForegroundColor Green
Write-Host "   🚀 DÉMARRAGE DE LA PLATEFORME IKAN AI          " -ForegroundColor Green
Write-Host "   (Connecté à la BDD Render PostgreSQL Production)" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Green
Write-Host ""

$rootDir = Get-Location

# 1. Démarrer l'API Backend FastAPI
Write-Host "[1/4] Démarrage du Backend FastAPI (Port 8000)..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$rootDir\apps\api'; .\venv\Scripts\python run.py"

# 2. Démarrer le Client Astro (Formulaire QR Code)
Write-Host "[2/4] Démarrage du Client Astro (Port 4321)..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$rootDir\apps\client'; npm run dev"

# 3. Démarrer le Dashboard React (Back-Office Admin / CX)
Write-Host "[3/4] Démarrage du Dashboard React (Port 5173)..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$rootDir\apps\dashboard'; npm run dev"

# 4. Démarrer l'Agent IA (uvicorn.exe échoue depuis ce dossier — utiliser python.exe -m uvicorn)
Write-Host "[4/4] Démarrage de l'Agent IA (Port 8001)..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$rootDir\apps\agent'; .venv\Scripts\python.exe -m uvicorn app.main:app --port 8001 --host 0.0.0.0"

Write-Host ""
Write-Host "==================================================" -ForegroundColor Green
Write-Host "✅ Tous les services ont été démarrés dans des fenêtres séparées !" -ForegroundColor Green
Write-Host ""
Write-Host " 🌐 Backend API Documentation : http://localhost:8000/api/v1/docs" -ForegroundColor Yellow
Write-Host " 📱 Client Mobile QR Code     : http://localhost:4321" -ForegroundColor Yellow
Write-Host " 📊 Dashboard Back-Office     : http://localhost:5173" -ForegroundColor Yellow
Write-Host " 🤖 Agent IA                  : http://localhost:8001" -ForegroundColor Yellow
Write-Host " ☁️ Base de données Render   : dpg-d9tej2h42hec7381j2ag-a.frankfurt-postgres.render.com" -ForegroundColor Magenta
Write-Host "==================================================" -ForegroundColor Green
