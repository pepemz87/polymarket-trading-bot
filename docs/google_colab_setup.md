# Google Colab Setup Guide

Esta guía te ayudará a ejecutar el bot de Polymarket en Google Colab de forma **GRATUITA**.

## ✅ Ventajas de Google Colab

- ✅ **100% GRATIS** - No necesitas tarjeta de crédito
- ✅ **Fácil de usar** - Solo necesitas una cuenta de Google
- ✅ **Ideal para paper trading** - Perfecto para probar el bot
- ✅ **GPU gratis** (aunque no la necesitamos)
- ✅ **Jupyter notebooks** - Interfaz familiar

## ❌ Limitaciones

- ❌ **Máximo 12 horas** de ejecución continua
- ❌ **Se desconecta** si está inactivo (~90 minutos)
- ❌ **No es 24/7** - Necesitas reconectar manualmente
- ❌ **Archivos temporales** - Se borran al desconectar

## 🚀 Inicio Rápido

### Opción 1: Usar el Notebook Incluido (Recomendado)

1. **Sube el notebook a Google Drive:**
   - Abre [Google Drive](https://drive.google.com)
   - Crea una carpeta "Polymarket Bot"
   - Sube el archivo `polymarket_bot_colab.ipynb`

2. **Abre con Google Colab:**
   - Click derecho en el archivo
   - "Abrir con" → "Google Colaboratory"
   - Si no aparece Colab, instálalo desde Google Workspace Marketplace

3. **Ejecuta el notebook:**
   - Sigue las instrucciones en cada celda
   - Ejecuta celda por celda (Shift + Enter)
   - Configura tus API keys cuando se solicite

### Opción 2: Crear Desde Cero

1. **Ir a Google Colab:**
   - Ve a [colab.research.google.com](https://colab.research.google.com)
   - Click en "Nuevo Notebook"

2. **Clonar el repositorio:**
```python
!git clone https://github.com/TU_USUARIO/polymarket-trading-bot.git
%cd polymarket-trading-bot
```

3. **Instalar dependencias:**
```python
!pip install -q -r requirements.txt
```

4. **Configurar API keys:**
```python
import os
from getpass import getpass

# Gemini API (REQUERIDO)
os.environ['GEMINI_API_KEY'] = getpass('Gemini API Key: ')

# Groq API (OPCIONAL)
os.environ['GROQ_API_KEY'] = getpass('Groq API Key: ')

# Paper Trading
os.environ['TRADING_MODE'] = 'paper'
os.environ['INITIAL_BANKROLL'] = '100'
```

5. **Crear directorios:**
```python
!mkdir -p data logs
```

6. **Ejecutar el bot:**
```python
from main import TradingBot

bot = TradingBot()
bot.run_once()
```

## 📋 Configuración Detallada

### API Keys Necesarias

Para **paper trading** solo necesitas:

1. **Gemini API** (GRATIS):
   - Ve a https://aistudio.google.com/app/apikey
   - Sign in con tu cuenta de Google
   - Click "Create API Key"
   - Copia la key

2. **Groq API** (GRATIS, opcional):
   - Ve a https://console.groq.com/keys
   - Sign up
   - Crea una API key
   - Copia la key

### Variables de Entorno

```python
import os

# API Keys
os.environ['GEMINI_API_KEY'] = 'tu_key_aqui'
os.environ['GROQ_API_KEY'] = 'tu_key_aqui'  # Opcional

# Configuración
os.environ['TRADING_MODE'] = 'paper'  # IMPORTANTE: paper trading
os.environ['INITIAL_BANKROLL'] = '100'
os.environ['DATABASE_URL'] = 'sqlite:///data/trades.db'
os.environ['LOG_LEVEL'] = 'INFO'

# Polymarket (vacío para paper trading)
os.environ['POLYMARKET_API_KEY'] = ''
os.environ['POLYMARKET_API_SECRET'] = ''
os.environ['POLYMARKET_API_PASSPHRASE'] = ''
os.environ['POLYMARKET_PRIVATE_KEY'] = ''
```

## 🎮 Modos de Ejecución

### Modo 1: Ejecución Única (Recomendado para pruebas)

```python
from main import TradingBot

bot = TradingBot()
bot.run_once()  # Ejecuta una vez y termina
```

**Ventajas:**
- Rápido para probar
- Puedes revisar resultados inmediatamente
- No consume tiempo de Colab innecesariamente

### Modo 2: Ejecución Continua

```python
from main import TradingBot

bot = TradingBot()
bot.run_continuous()  # Ejecuta hasta que detengas
```

**Ventajas:**
- Simula operación 24/7
- Escanea mercados cada 6 horas
- Revisa posiciones cada 30 minutos

**Desventajas:**
- Consume las 12 horas de Colab
- Necesitas detener manualmente

## 📊 Ver Resultados

### Ver Trades

```python
from src.models.database import get_database, Trade
import pandas as pd

db = get_database()
session = db.get_session()

trades = session.query(Trade).all()

for trade in trades:
    print(f"ID: {trade.id}")
    print(f"Market: {trade.market_question}")
    print(f"Side: {trade.side} {trade.outcome}")
    print(f"Size: ${trade.size:.2f}")
    print(f"P&L: ${trade.realized_pnl or trade.unrealized_pnl or 0:.2f}")
    print("-" * 50)

session.close()
```

### Ver Predicciones

```python
from src.models.database import Prediction

session = db.get_session()
predictions = session.query(Prediction).limit(5).all()

for pred in predictions:
    print(f"Market: {pred.market_question}")
    print(f"Prediction: {pred.predicted_outcome} ({pred.confidence}%)")
    print(f"Reasoning: {pred.reasoning}")
    print("-" * 50)

session.close()
```

### Ver Logs

```python
# Ver últimas 50 líneas del log
!tail -50 logs/bot.log

# Ver log de trades
!tail -20 logs/trades.log

# Ver errores
!tail -20 logs/errors.log
```

## 📈 Visualizaciones

### Equity Curve

```python
import matplotlib.pyplot as plt

# Obtener trades cerrados
closed_trades = session.query(Trade).filter(
    Trade.status == 'closed'
).order_by(Trade.exit_time).all()

# Calcular equity
initial = 100
equity = [initial]
for trade in closed_trades:
    equity.append(equity[-1] + (trade.realized_pnl or 0))

# Graficar
plt.figure(figsize=(12, 6))
plt.plot(equity, marker='o')
plt.axhline(y=initial, color='r', linestyle='--')
plt.title('Equity Curve')
plt.xlabel('Trade #')
plt.ylabel('Bankroll (USDC)')
plt.grid(True)
plt.show()
```

## 💾 Guardar y Descargar Datos

### Descargar Base de Datos

```python
from google.colab import files

# Descargar DB
files.download('data/trades.db')

# Descargar logs
files.download('logs/bot.log')
```

### Guardar en Google Drive

```python
from google.colab import drive

# Montar Drive
drive.mount('/content/drive')

# Copiar archivos
!cp data/trades.db /content/drive/MyDrive/polymarket-bot/
!cp logs/*.log /content/drive/MyDrive/polymarket-bot/logs/
```

## 🔄 Mantener Colab Activo

Colab se desconecta después de ~90 minutos de inactividad. Para evitarlo:

### Opción 1: JavaScript en Consola del Navegador

```javascript
function KeepAlive() {
    console.log("Keeping alive...");
    document.querySelector("colab-connect-button").click();
}
setInterval(KeepAlive, 60000); // Cada minuto
```

### Opción 2: Usar Colab Pro

- $9.99/mes
- Hasta 24 horas de ejecución
- GPU más potentes
- Sin desconexión por inactividad

## ⚠️ Problemas Comunes

### "Runtime disconnected"
**Solución:** Reconecta y vuelve a ejecutar las celdas

### "Out of memory"
**Solución:** Reduce `max_positions` en config.yaml

### "API key invalid"
**Solución:** Verifica que copiaste la key correctamente

### "No module named 'src'"
**Solución:** Asegúrate de estar en el directorio correcto:
```python
%cd polymarket-trading-bot
```

## 🎯 Workflow Recomendado

### Día 1-3: Pruebas Iniciales
1. Ejecuta el bot en modo único varias veces
2. Revisa las predicciones del LLM
3. Verifica que los trades se ejecutan correctamente
4. Ajusta configuración si es necesario

### Día 4-7: Simulación Extendida
1. Ejecuta en modo continuo durante 12 horas
2. Revisa resultados cada 2-3 horas
3. Descarga datos al final del día
4. Analiza rendimiento

### Después de 7 días: Decisión
- ✅ **Si funciona bien:** Migra a Railway para 24/7
- ⚠️ **Si necesita ajustes:** Modifica config y repite
- ❌ **Si no funciona:** Revisa logs y estrategia

## 🚀 Migrar a Railway

Cuando estés listo para 24/7:

1. **Sube tu código a GitHub:**
```bash
git init
git add .
git commit -m "Bot tested on Colab"
git push
```

2. **Deploy en Railway:**
   - Ve a railway.app
   - Conecta tu repo
   - Configura variables de entorno
   - Deploy automático

3. **Ventajas de Railway:**
   - 24/7 sin interrupciones
   - $5 gratis/mes
   - Logs en tiempo real
   - Fácil de actualizar

## 📚 Recursos Adicionales

- [Notebook de ejemplo](../polymarket_bot_colab.ipynb)
- [README principal](../README.md)
- [Guía de API keys](api_setup_guide.md)
- [Deploy en Railway](deployment_pythonanywhere.md)

## 💡 Tips

1. **Guarda tu trabajo:** Descarga la DB regularmente
2. **Usa Drive:** Monta Google Drive para backups automáticos
3. **Monitorea:** Revisa logs cada hora
4. **Ajusta:** Modifica config.yaml según resultados
5. **Documenta:** Anota qué configuraciones funcionan mejor

---

**¿Listo para empezar? Abre el notebook y ejecuta la primera celda! 🚀**
