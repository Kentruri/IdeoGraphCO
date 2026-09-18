# Anotar el gold set — guía de comandos

1.301 artículos de prensa política colombiana. Hay que asignarle a cada uno
**una** de ocho clases ideológicas.

Todo corre en tu computador. No hace falta el corpus completo ni ningún
servidor: el repositorio ya trae los artículos.

---

## 1. Requisitos

**macOS**

```bash
brew install python@3.11 git
```

**Windows** (PowerShell como administrador)

```powershell
winget install --id Python.Python.3.11 -e
winget install --id Git.Git -e
```

Cierra y vuelve a abrir la terminal. Comprueba:

```
python3 --version     # macOS   → 3.11.x
python --version      # Windows → 3.11.x
git --version
```

---

## 2. Clonar el repositorio

**macOS**

```bash
cd ~/Desktop
git clone git@github.com:Kentruri/IdeoGraphCO.git
cd IdeoGraphCO
```

**Windows**

```powershell
cd $HOME\Desktop
git clone git@github.com:Kentruri/IdeoGraphCO.git
cd IdeoGraphCO
```

---

## 3. Instalar Label Studio

Va en su propio entorno, aparte del proyecto.

**macOS**

```bash
python3 -m venv ~/label-studio-env
~/label-studio-env/bin/pip install --upgrade pip
~/label-studio-env/bin/pip install label-studio requests
```

**Windows**

```powershell
python -m venv $HOME\label-studio-env
$HOME\label-studio-env\Scripts\pip install --upgrade pip
$HOME\label-studio-env\Scripts\pip install label-studio requests
```

---

## 4. Arrancar Label Studio

Deja esta terminal abierta mientras anotas.

**macOS**

```bash
~/label-studio-env/bin/label-studio start --port 8080
```

**Windows**

```powershell
$HOME\label-studio-env\Scripts\label-studio start --port 8080
```

Abre `http://localhost:8080` y crea una cuenta: correo y contraseña
cualesquiera. **Solo existen en tu computador** — apúntalas.

---

## 5. Cargar los artículos

En una terminal **nueva**, dentro de la carpeta del repositorio.

**macOS**

```bash
cd ~/Desktop/IdeoGraphCO
~/label-studio-env/bin/python scripts/anotar.py init
```

**Windows**

```powershell
cd $HOME\Desktop\IdeoGraphCO
$HOME\label-studio-env\Scripts\python scripts\anotar.py init
```

Pide el correo y la contraseña del paso 4. Al terminar imprime el enlace
donde anotar.

---

## 6. Anotar

Abre el enlace que imprimió el paso 5 (`http://localhost:8080/projects/N/data`).

- Clic en cualquier fila para abrir el artículo.
- Se lee a la izquierda, se elige la clase a la derecha, `Submit`.
- La clase es obligatoria; sin ella no deja enviar.
- El campo de **notas** es para dudas y empates.
- Se guarda solo: puedes cerrar y volver cuando quieras.
- La tabla muestra cuántos llevas y qué le pusiste a cada uno. Filtra por
  `Annotated: no` para ver lo que falta.

Las ocho clases, en cuatro ejes opuestos:

| Eje | Clases |
|---|---|
| Gobernanza y discurso | populismo ↔ institucionalismo |
| Liderazgo político | personalismo ↔ doctrinarismo |
| Política exterior | soberanismo ↔ globalismo |
| Sociocultural | conservadurismo ↔ progresismo |

---

## 7. Entregar

Cuando lleves un bloque o al terminar.

**macOS**

```bash
cd ~/Desktop/IdeoGraphCO
~/label-studio-env/bin/python scripts/anotar.py export
git add annotation/gold_set_v2_juan.json
git commit -m "gold: juan, avance de anotacion"
git push
```

**Windows**

```powershell
cd $HOME\Desktop\IdeoGraphCO
$HOME\label-studio-env\Scripts\python scripts\anotar.py export
git add annotation/gold_set_v2_juan.json
git commit -m "gold: juan, avance de anotacion"
git push
```

Se puede repetir tantas veces como quieras: cada export incluye **todo** lo
anotado hasta ese momento y reemplaza el archivo anterior.

---

## Volver a empezar una sesión

Solo los pasos 4 y 6: arrancar Label Studio y abrir el enlace. Los pasos
1, 2, 3 y 5 se hacen una única vez.

---

## Si algo falla

```
X No responde Label Studio en http://localhost:8080
```
El paso 4 no está corriendo, o se cerró esa terminal.

```
X Usuario o contrasena incorrectos
```
Son los del paso 4, los que creaste en `localhost:8080`. No son los de GitHub.

```
! El proyecto 'Gold set — juan' ya existe
```
Normal si repites el paso 5. Usa el enlace que imprime. `--replace` lo rehace
desde cero y **borra lo anotado**.

Para rehacer la instalación, borra `~/label-studio-env` (o
`$HOME\label-studio-env`) y repite el paso 3. Lo anotado no vive ahí, así que
no se pierde.
