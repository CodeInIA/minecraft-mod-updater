# 🧩 Minecraft Mod Updater

<img src="updater-logo.png" alt="Mod Updater Logo" width="150" />

A desktop app to keep your Minecraft mods up to date with the latest versions from [Modrinth](https://modrinth.com).

## ✨ Features

- **Works with every Minecraft version**, including the new year-based versions (`26.1`, `26.3`, snapshots…). The version list comes live from Modrinth, nothing is hard-coded.
- **Any loader**: Fabric, NeoForge, Forge, Quilt (also uses Fabric mods) and every other loader Modrinth supports.
- **Graphical interface** with light/dark theme: every mod is listed with its Modrinth icon, installed and available version and status, with a filter, "Select all" and per-mod selection. Click a mod's name to open its Modrinth page.
- **14 languages**: English, Spanish, Portuguese, French, German, Italian, Dutch, Polish, Russian, Ukrainian, Turkish, Japanese, Korean and Chinese. The app and the Windows installer use the operating system's language automatically (English if it is not available); the app language can also be changed in Settings.
- **Multiple profiles** (client, server, modpacks…), each with its own folder, Minecraft version, loader and color. Drag them in the sidebar to reorder them.
- **Automatic detection** (default): the Minecraft version and loader are detected from the mods already in the profile folder every time you check for updates.
- **Move a profile to another Minecraft version**: **Change version** shows which mods already have a version for it, which are not ready yet and which new dependencies they need, then installs them (optionally disabling the mods that are not ready) and switches the profile.
- **Find and install mods** from Modrinth inside the app (**+ Find on Modrinth**): results only show what works with the profile's Minecraft version and loader, and required dependencies are installed too.
- **Safe updates**: downloads are verified by SHA-512, replaced files are moved to a backup folder, and disabled mods (`.jar.disabled`) stay disabled. Any update can be **undone** from the **Backups** button.
- **Missing dependencies**: if a mod (or its update) needs another mod you do not have, such as Fabric API, it is offered for installation too.
- **See what changes** before updating: right-click a mod (or double-click it) to read the changelog of every version between yours and the new one.
- **Keep a mod as it is**: right-click → *Don't update this mod*, per profile. Or **choose the exact version** to install (for example an older one when a new release breaks something): the mod is then pinned to it.
- **Enable or disable mods** with a right-click (renames them to/from `.disabled`).
- **Problems are pointed out**: a mod installed twice (two versions of the same mod) or mods their authors mark as incompatible get a warning.
- **Minecraft must be closed** to replace mods: the app notices when the game (or a server) is running with the profile's folder and asks to close it first.
- **Modpacks**: export a profile as an `.mrpack` (Prism Launcher, Modrinth App, ATLauncher…) or install an `.mrpack` as a new profile; compare two profiles, for example a client and its server.
- **Resource packs, shaders and data packs** are updated the same way: choose the content type of each profile.
- **Client/server warnings**: mark a profile as a server and the app points out mods that only work on the client (and vice versa).
- **Import from launchers**: profiles are created from the instances of Prism Launcher, Modrinth App, CurseForge, ATLauncher and MultiMC.
- **Fast rescans**: unchanged files are not hashed again. Mods that are not on Modrinth byte for byte (for example a version only published elsewhere) are still recognised by the mod ID inside the jar.
- **Reliable**: failed requests and downloads are retried, and everything the app does is written to a log (**Settings → Open log**).
- **Keyboard shortcuts**: F5 check, Ctrl+U update, Ctrl+F search, Ctrl+↑/↓ switch profile… (F1 lists them; ⌘ on macOS).
- **Updates itself**: at startup the app checks GitHub for a new version and installs it automatically (Windows asks for administrator permission). This can be turned off in Settings; the app then only shows a notice with an **Update now** button.

## 📥 Download

| System | Download | How to install |
|---|---|---|
| Windows 10/11 | [MinecraftModUpdater_Setup.exe](https://github.com/CodeInIA/minecraft-mod-updater/releases/latest/download/MinecraftModUpdater_Setup.exe) | Run the installer. |
| macOS (Apple Silicon) | [MinecraftModUpdater_macOS.dmg](https://github.com/CodeInIA/minecraft-mod-updater/releases/latest/download/MinecraftModUpdater_macOS.dmg) | Drag the app to Applications. The app is not signed: the first time, right-click → Open (or System Settings → Privacy & Security → Open Anyway). |
| Linux x64 | [MinecraftModUpdater_Linux.tar.gz](https://github.com/CodeInIA/minecraft-mod-updater/releases/latest/download/MinecraftModUpdater_Linux.tar.gz) | Extract it and run `./install.sh` (installs for your user, no root). `./install.sh --uninstall` removes it. |

Python is **not** required. New versions are published automatically for the three systems once they pass the tests, and the app installs them by itself — see [Releases](https://github.com/CodeInIA/minecraft-mod-updater/releases).

## 🚀 Running from source

Requires Python 3.10 or newer.

```bash
pip install -r requirements.txt
python mod_updater.py
```

## 💻 Usage

1. Create a profile (or edit the default `client` one), choose its mods folder and, if you like, a color. The default is the official launcher's `mods` folder (`%APPDATA%\.minecraft\mods` on Windows, `~/Library/Application Support/minecraft/mods` on macOS, `~/.minecraft/mods` on Linux).
2. Leave Minecraft version and loader on **Auto** to detect them from the mods in the folder, or choose a specific version to migrate your mods to it.
3. Press **Check for updates**. Each mod shows its icon, installed version, available version and status; click its name to open it on Modrinth.
4. Tick the mods you want (or use **Select all**) and press **Update selected**.

Right-click a mod for its changelog, its Modrinth page, *Choose version…*, *Don't update this mod*, *Disable*/*Enable* or *Show in folder*. **Backups** lists the backups of the profile and undoes the latest update. **⇄ Change version** moves the profile to another Minecraft version, **+ Find on Modrinth** installs new mods, and the **⋯** menu exports the profile as an `.mrpack` or compares it with another profile. Import (sidebar) also installs `.mrpack` files.

Settings (⚙): backups on/off, allow beta/alpha mod versions, show Minecraft snapshots, theme, language, and automatic or manual updates of the app.

Backups are stored next to the mods folder, in `mod_updater_backups/<date>/`.
Configuration is stored in `minecraft_mod_updater/mod_updater_config.json` inside `%APPDATA%` (Windows), `~/Library/Application Support` (macOS) or `~/.config` (Linux); configs from version 1.x are migrated automatically.

## 📝 How it works

1. Each `.jar` in the folder is hashed (SHA-512) and identified on Modrinth.
2. Modrinth is asked for the newest version of each mod for the selected Minecraft version and loader.
3. A mod is updated when that version is different from the installed one and is either newer or the installed file was built for another Minecraft version or loader. Version numbers are never parsed, so any versioning scheme works.

Files whose hash is unknown are looked up by the mod ID declared inside the jar (`fabric.mod.json`, `quilt.mod.json`, `mods.toml`) when it matches a Modrinth project with the same name. Mods not published on Modrinth at all are listed as "not on Modrinth" and left untouched.

## 🛠️ Building

Locally: `pip install -r requirements.txt pyinstaller`, then `pyinstaller --noconfirm mod_updater.spec`. On Windows, `build_installer.bat` also builds the installer (requires [Inno Setup 6](https://jrsoftware.org/isinfo.php)) into `installer/`.

Development happens on the `dev` branch; `main` only receives merges from `dev`.

- `.github/workflows/tests.yml` checks the code with `ruff` and `mypy` (settings in `pyproject.toml`) and runs the test suite (`pytest`) on Windows, macOS and Linux on every push to `dev` and on pull requests to `main`.
- `.github/workflows/release.yml` runs on every push to `main` (merging `dev`). It runs the tests, builds the app with PyInstaller on the three systems, starts each packaged app in `--self-test` mode, tests the Windows installer, the macOS disk image and the Linux `install.sh`, and only then publishes a new release. A release is only published when files that end up in the app changed since the previous one: pushes that only touch documentation (`*.md`, `docs/`), tests or CI files (`.github/`) run the tests and stop there (a manual run always publishes). Its changelog is built from the commit messages since the previous release (`.github/scripts/changelog.py`; merges and `tests:`/`release:`/`ci:` commits are left out). The version is computed from the latest `vX.Y.Z` tag: the patch number goes up by default, and a standalone `#minor` or `#major` in a commit message since the last release bumps the minor or major number (`v2.0.4` → `v2.1.0` → `v3.0.0`). When the workflow is started by hand from the Actions tab, the bump can be chosen.

Run the tests locally with `pip install -r requirements.txt -r requirements-dev.txt` and `python -m pytest` (`-m "not network"` skips the tests that use the internet); `ruff check .` and `mypy` run the same checks as the workflow.

## 📜 License

Copyright (c) 2025-2026 CodeInIA. Free for personal, non-commercial use; all other rights reserved. See [LICENSE](LICENSE).

---

# Minecraft Mod Updater (Español)

Aplicación de escritorio para mantener tus mods de Minecraft actualizados desde Modrinth.

## Características
- Funciona con **todas las versiones de Minecraft**, incluidas las nuevas (`26.1`, `26.3`, snapshots…).
- Fabric, NeoForge, Forge, Quilt y el resto de loaders de Modrinth.
- Interfaz gráfica con tema claro/oscuro: cada mod aparece con su icono de Modrinth, la versión instalada y la disponible y su estado, con filtro, «Seleccionar todo» y selección individual. Haz clic en el nombre de un mod para abrir su página de Modrinth.
- **14 idiomas**: inglés, español, portugués, francés, alemán, italiano, neerlandés, polaco, ruso, ucraniano, turco, japonés, coreano y chino. La app y el instalador de Windows usan automáticamente el idioma del sistema operativo (inglés si no está disponible); el idioma de la app también se puede cambiar en Ajustes.
- Varios perfiles (cliente, servidor, modpacks…), cada uno con su carpeta, versión de Minecraft, loader y color. Se reordenan arrastrándolos en la barra lateral.
- Detección automática (por defecto) de la versión de Minecraft y el loader a partir de los mods de la carpeta del perfil.
- **Cambiar un perfil de versión de Minecraft**: **Cambiar versión** muestra qué mods ya tienen versión para ella, cuáles aún no y qué dependencias nuevas hacen falta; después los instala (y si quieres desactiva los que no están listos) y cambia el perfil.
- **Buscar e instalar mods** de Modrinth desde la app (**+ Buscar en Modrinth**): solo salen los que funcionan con la versión y el loader del perfil, y se instalan también sus dependencias.
- Descargas verificadas, copia de seguridad de los mods sustituidos y respeto de los mods desactivados. Cualquier actualización se puede **deshacer** desde el botón **Copias**.
- **Dependencias que faltan**: si un mod (o su actualización) necesita otro que no tienes, como Fabric API, también se ofrece para instalarlo.
- **Ver qué cambia** antes de actualizar: clic derecho (o doble clic) en un mod para leer el changelog de cada versión entre la tuya y la nueva.
- **Dejar un mod como está**: clic derecho → *No actualizar este mod*, en cada perfil. O **elegir la versión exacta** que instalar (por ejemplo una anterior si la nueva da problemas): el mod queda fijado en ella.
- **Activar o desactivar mods** con clic derecho (los renombra a/desde `.disabled`).
- **Avisos de problemas**: mods instalados dos veces (dos versiones del mismo) o que sus autores marcan como incompatibles.
- **Minecraft tiene que estar cerrado** para sustituir mods: la app detecta si el juego (o un servidor) está usando la carpeta del perfil y te pide cerrarlo antes.
- **Modpacks**: exporta un perfil como `.mrpack` (Prism Launcher, Modrinth App, ATLauncher…) o instala un `.mrpack` como perfil nuevo; compara dos perfiles, por ejemplo el del cliente y el del servidor.
- **Resource packs, shaders y data packs** se actualizan igual: elige el tipo de contenido de cada perfil.
- **Avisos cliente/servidor**: marca un perfil como servidor y la app te avisa de los mods que solo sirven en el cliente (y al revés).
- **Importar de launchers**: crea perfiles a partir de las instancias de Prism Launcher, Modrinth App, CurseForge, ATLauncher y MultiMC.
- **Análisis rápidos**: los archivos que no han cambiado no se vuelven a calcular. Los mods que no están en Modrinth tal cual (por ejemplo una versión publicada solo en otro sitio) se reconocen igualmente por el ID del mod que llevan dentro.
- **Fiable**: las peticiones y descargas que fallan se reintentan, y todo lo que hace la app queda en un registro (**Ajustes → Abrir registro**).
- **Atajos de teclado**: F5 buscar, Ctrl+U actualizar, Ctrl+F filtrar, Ctrl+↑/↓ cambiar de perfil… (F1 los muestra; ⌘ en macOS).
- **Se actualiza sola**: al iniciarse comprueba en GitHub si hay una versión nueva y la instala automáticamente (Windows pide permiso de administrador). Se puede desactivar en Ajustes; entonces solo muestra un aviso con el botón **Actualizar ahora**.

## Descargar
| Sistema | Descarga | Instalación |
|---|---|---|
| Windows 10/11 | [MinecraftModUpdater_Setup.exe](https://github.com/CodeInIA/minecraft-mod-updater/releases/latest/download/MinecraftModUpdater_Setup.exe) | Ejecuta el instalador. |
| macOS (Apple Silicon) | [MinecraftModUpdater_macOS.dmg](https://github.com/CodeInIA/minecraft-mod-updater/releases/latest/download/MinecraftModUpdater_macOS.dmg) | Arrastra la app a Aplicaciones. No está firmada: la primera vez, clic derecho → Abrir (o Ajustes → Privacidad y seguridad → Abrir igualmente). |
| Linux x64 | [MinecraftModUpdater_Linux.tar.gz](https://github.com/CodeInIA/minecraft-mod-updater/releases/latest/download/MinecraftModUpdater_Linux.tar.gz) | Descomprime y ejecuta `./install.sh` (se instala para tu usuario, sin root). `./install.sh --uninstall` lo desinstala. |

**No** necesitas Python. Las versiones nuevas se publican automáticamente para los tres sistemas cuando pasan los tests, y la app las instala sola — consulta las [Releases](https://github.com/CodeInIA/minecraft-mod-updater/releases).

## Uso
1. Crea un perfil (o edita `client`), elige su carpeta de mods y, si quieres, un color.
2. Deja la versión y el loader en **Auto** para detectarlos de los mods de la carpeta, o elige una versión concreta para migrar los mods a ella.
3. Pulsa **Buscar actualizaciones**. Cada mod muestra su icono, la versión instalada, la disponible y su estado; haz clic en su nombre para abrirlo en Modrinth.
4. Marca los mods que quieras (o usa **Seleccionar todo**) y pulsa **Actualizar seleccionados**.

Con clic derecho en un mod: changelog, página de Modrinth, *Elegir versión…*, *No actualizar este mod*, *Desactivar*/*Activar* o *Mostrar en la carpeta*. **⇄ Cambiar versión** pasa el perfil a otra versión de Minecraft, **+ Buscar en Modrinth** instala mods nuevos y el menú **⋯** exporta el perfil como `.mrpack` o lo compara con otro. Importar (barra lateral) también instala archivos `.mrpack`.

## Desde el código fuente
Requiere Python 3.10 o superior.
```bash
pip install -r requirements.txt
python mod_updater.py
```

## Licencia
Copyright (c) 2025-2026 CodeInIA. Uso gratuito solo personal y no comercial; resto de derechos reservados. Consulta [LICENSE](LICENSE).
