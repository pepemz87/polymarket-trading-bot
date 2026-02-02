# 🌐 Setup Completo en Google Colab (Sin Usar Local)

Esta guía te permite configurar y ejecutar el bot **completamente desde el navegador**, sin usar PowerShell ni comandos en tu PC.

## 🎯 Objetivo

Subir el código a GitHub y ejecutar el bot, todo desde Google Colab.

## 📋 Pasos Completos

### 1️⃣ Preparar en tu PC (Solo 2 minutos)

**Comprimir la carpeta del bot:**

1. Ve a: `c:\Users\josmarti7\.gemini\antigravity\playground\molten-magnetar`
2. Click derecho en la carpeta `molten-magnetar`
3. "Enviar a" → "Carpeta comprimida"
4. Se creará `molten-magnetar.zip`
5. Guarda este ZIP en un lugar fácil de encontrar (Escritorio, por ejemplo)

✅ **Listo en tu PC. El resto es en el navegador.**

---

### 2️⃣ Crear Cuenta en GitHub (Si no tienes)

1. Ve a [github.com/signup](https://github.com/signup)
2. Crea tu cuenta (gratis)
3. Verifica tu email

---

### 3️⃣ Crear Repositorio en GitHub

1. Ve a [github.com/new](https://github.com/new)
2. **Repository name:** `polymarket-trading-bot`
3. **Descripción:** (opcional) "Autonomous trading bot for Polymarket"
4. **Público o Privado:** Tu elección
5. **IMPORTANTE:** NO marques "Add a README file"
6. Click **"Create repository"**

📝 **Anota tu usuario de GitHub** (lo necesitarás después)

---

### 4️⃣ Crear Personal Access Token

Este token permite que Colab suba código a tu GitHub:

1. Ve a [github.com/settings/tokens](https://github.com/settings/tokens)
2. Click **"Generate new token"** → **"Generate new token (classic)"**
3. **Note:** `colab-upload`
4. **Expiration:** 90 days (o lo que prefieras)
5. **Marca SOLO:** ✅ `repo` (todos los sub-items se marcarán automáticamente)
6. Scroll abajo y click **"Generate token"**
7. **COPIA EL TOKEN** (empieza con `ghp_...`)
   - ⚠️ Solo se muestra UNA VEZ
   - Guárdalo en un lugar seguro temporalmente

---

### 5️⃣ Subir Código a GitHub desde Colab

1. **Abre Google Colab:**
   - Ve a [colab.research.google.com](https://colab.research.google.com)
   - Sign in con tu cuenta de Google

2. **Sube el notebook de upload:**
   - En Colab, click "Archivo" → "Subir notebook"
   - Arrastra el archivo `colab_upload_to_github.ipynb` desde tu PC
   - O usa "GitHub" y pega la URL de tu repo (después del primer upload)

3. **Ejecuta el notebook:**
   - Sigue las instrucciones en cada celda
   - Cuando pida el ZIP, sube `molten-magnetar.zip`
   - Cuando pida credenciales:
     - **Nombre:** Tu nombre
     - **Email:** Tu email de GitHub
     - **Usuario:** Tu usuario de GitHub
     - **Token:** El token que copiaste (ghp_...)

4. **Espera a que termine:**
   - Verás mensajes de progreso
   - Al final dirá "✅ ¡Código subido a GitHub!"

---

### 6️⃣ Ejecutar el Bot en Colab

Ahora que el código está en GitHub, puedes usarlo fácilmente:

1. **Crea un nuevo notebook en Colab**

2. **Clona tu repositorio:**
```python
!git clone https://github.com/TU_USUARIO/polymarket-trading-bot.git
%cd polymarket-trading-bot
```

3. **Instala dependencias:**
```python
!pip install -q -r requirements.txt
```

4. **Configura API keys:**
```python
import os
from getpass import getpass

# Gemini API (GRATIS)
os.environ['GEMINI_API_KEY'] = getpass('Gemini API Key: ')

# Groq API (OPCIONAL)
os.environ['GROQ_API_KEY'] = getpass('Groq API Key (opcional): ')

# Paper Trading
os.environ['TRADING_MODE'] = 'paper'
os.environ['INITIAL_BANKROLL'] = '100'
os.environ['DATABASE_URL'] = 'sqlite:///data/trades.db'

# Crear directorios
!mkdir -p data logs

print("✅ Configurado")
```

5. **Ejecutar el bot:**
```python
from main import TradingBot

bot = TradingBot()
bot.run_once()
```

---

## 🎯 Flujo Completo Resumido

```
PC (2 min)
└─ Comprimir carpeta en ZIP

GitHub (5 min)
├─ Crear cuenta
├─ Crear repositorio
└─ Crear token

Google Colab (5 min)
├─ Subir notebook de upload
├─ Ejecutar celdas
└─ Código sube a GitHub

Google Colab - Usar Bot (2 min)
├─ Nuevo notebook
├─ Clonar desde GitHub
├─ Configurar API keys
└─ ¡Ejecutar bot!
```

**Total: ~15 minutos**

---

## 🔄 Para Actualizaciones Futuras

Si modificas el código y quieres actualizarlo en GitHub:

```python
# En Colab, dentro de tu carpeta del proyecto
!git add .
!git commit -m "Descripción de los cambios"
!git push
```

---

## 📚 Archivos Importantes

- `colab_upload_to_github.ipynb` - Para subir código a GitHub (una sola vez)
- `polymarket_bot_colab.ipynb` - Para ejecutar el bot (siempre)

---

## ❓ Preguntas Frecuentes

### ¿Necesito instalar Git en mi PC?
**No.** Todo se hace desde el navegador.

### ¿Necesito PowerShell o terminal?
**No.** Todo se hace en Google Colab.

### ¿Es seguro el Personal Access Token?
**Sí**, siempre que:
- No lo compartas con nadie
- Lo uses solo en Colab (no lo subas a GitHub)
- Lo borres después de usarlo (opcional)

### ¿Puedo hacer esto desde un móvil o tablet?
**Técnicamente sí**, pero es más cómodo desde PC por el tema de subir archivos.

### ¿Qué pasa si pierdo el token?
Simplemente crea uno nuevo en GitHub settings.

---

## 🎉 ¡Listo!

Ahora tienes:
- ✅ Código en GitHub
- ✅ Bot ejecutándose en Colab
- ✅ Todo sin tocar tu PC (excepto comprimir el ZIP)

**Siguiente paso:** Obtén tus API keys gratuitas:
- Gemini: https://aistudio.google.com/app/apikey
- Groq: https://console.groq.com/keys

¡Y a hacer trading! 🚀📈
