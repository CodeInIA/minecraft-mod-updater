# 🧩 Minecraft Mod Updater

<img src="updater-logo.png" alt="Mod Updater Logo" width="150" />

A desktop app to keep your Minecraft mods up to date with the latest versions from [Modrinth](https://modrinth.com).

## ✨ Features

- **Works with every Minecraft version**, including the new year-based versions (`26.1`, `26.3`, snapshots…). The version list comes live from Modrinth, nothing is hard-coded.
- **Any loader**: Fabric, NeoForge, Forge, Quilt (also uses Fabric mods) and every other loader Modrinth supports.
- **Graphical interface** with light/dark theme, mod list, filter and per-mod selection.
- **14 languages**: English, Spanish, Portuguese, French, German, Italian, Dutch, Polish, Russian, Ukrainian, Turkish, Japanese, Korean and Chinese. The app and the Windows installer use the operating system's language automatically (English if it is not available); the app language can also be changed in Settings.
- **Multiple profiles** (client, server, modpacks…), each with its own folder, Minecraft version and loader.
- **Automatic detection** (default): the Minecraft version and loader are detected from the mods already in the profile folder every time you check for updates.
- **Migrate a modpack to a new Minecraft version**: pick the new version and every mod is swapped for its build for that version.
- **Safe updates**: downloads are verified by SHA-512, replaced files are moved to a backup folder, and disabled mods (`.jar.disabled`) stay disabled.

## 📥 Download

| System | Download | How to install |
|---|---|---|
| Windows 10/11 | [MinecraftModUpdater_Setup.exe](https://github.com/CodeInIA/minecraft-mod-updater/releases/latest/download/MinecraftModUpdater_Setup.exe) | Run the installer. |
| macOS (Apple Silicon) | [MinecraftModUpdater_macOS.dmg](https://github.com/CodeInIA/minecraft-mod-updater/releases/latest/download/MinecraftModUpdater_macOS.dmg) | Drag the app to Applications. The app is not signed: the first time, right-click → Open (or System Settings → Privacy & Security → Open Anyway). |
| Linux x64 | [MinecraftModUpdater_Linux.tar.gz](https://github.com/CodeInIA/minecraft-mod-updater/releases/latest/download/MinecraftModUpdater_Linux.tar.gz) | Extract it and run `./install.sh` (installs for your user, no root). `./install.sh --uninstall` removes it. |

Python is **not** required. Every commit to `main` automatically publishes a new release for all three systems — see [Releases](https://github.com/CodeInIA/minecraft-mod-updater/releases).

## 🚀 Running from source

Requires Python 3.10 or newer.

```bash
pip install -r requirements.txt
python mod_updater.py
```

## 💻 Usage

1. Create a profile (or edit the default `client` one) and choose its mods folder. The default is the official launcher's `mods` folder (`%APPDATA%\.minecraft\mods` on Windows, `~/Library/Application Support/minecraft/mods` on macOS, `~/.minecraft/mods` on Linux).
2. Leave Minecraft version and loader on **Auto** to detect them from the mods in the folder, or choose a specific version to migrate your mods to it.
3. Press **Check for updates**. Each mod shows its installed version, the available version and its status.
4. Tick the mods you want and press **Update selected**.

Settings (⚙): backups on/off, allow beta/alpha mod versions, show Minecraft snapshots, theme and language.

Backups are stored next to the mods folder, in `mod_updater_backups/<date>/`.
Configuration is stored in `minecraft_mod_updater/mod_updater_config.json` inside `%APPDATA%` (Windows), `~/Library/Application Support` (macOS) or `~/.config` (Linux); configs from version 1.x are migrated automatically.

## 📝 How it works

1. Each `.jar` in the folder is hashed (SHA-512) and identified on Modrinth.
2. Modrinth is asked for the newest version of each mod for the selected Minecraft version and loader.
3. A mod is updated when that version is different from the installed one and is either newer or the installed file was built for another Minecraft version or loader. Version numbers are never parsed, so any versioning scheme works.

Mods not published on Modrinth are listed as "not on Modrinth" and left untouched.

## 🛠️ Building

Locally: `pip install -r requirements.txt pyinstaller`, then `pyinstaller --noconfirm mod_updater.spec`. On Windows, `build_installer.bat` also builds the installer (requires [Inno Setup 6](https://jrsoftware.org/isinfo.php)) into `installer/`.

On GitHub: `.github/workflows/release.yml` runs on every push to `main`. It builds the app with PyInstaller on Windows, macOS and Linux, packages it (Inno Setup installer, `.dmg`, `.tar.gz` with `packaging/linux/install.sh`) and publishes release `vMAJOR.MINOR.N`, where `MAJOR.MINOR` is `VERSION_BASE` in the workflow and `N` is the workflow run number.

## 📜 License

Copyright (c) 2025-2026 CodeInIA. Free for personal, non-commercial use; all other rights reserved. See [LICENSE](LICENSE).

---

# Minecraft Mod Updater (Español)

Aplicación de escritorio para mantener tus mods de Minecraft actualizados desde Modrinth.

## Características
- Funciona con **todas las versiones de Minecraft**, incluidas las nuevas (`26.1`, `26.3`, snapshots…).
- Fabric, NeoForge, Forge, Quilt y el resto de loaders de Modrinth.
- Interfaz gráfica con tema claro/oscuro, lista de mods, filtro y selección individual.
- **14 idiomas**: inglés, español, portugués, francés, alemán, italiano, neerlandés, polaco, ruso, ucraniano, turco, japonés, coreano y chino. La app y el instalador de Windows usan automáticamente el idioma del sistema operativo (inglés si no está disponible); el idioma de la app también se puede cambiar en Ajustes.
- Varios perfiles, cada uno con su carpeta, versión de Minecraft y loader.
- Detección automática (por defecto) de la versión de Minecraft y el loader a partir de los mods de la carpeta del perfil.
- Migración de un modpack a otra versión de Minecraft.
- Descargas verificadas, copia de seguridad de los mods sustituidos y respeto de los mods desactivados.

## Descargar
| Sistema | Descarga | Instalación |
|---|---|---|
| Windows 10/11 | [MinecraftModUpdater_Setup.exe](https://github.com/CodeInIA/minecraft-mod-updater/releases/latest/download/MinecraftModUpdater_Setup.exe) | Ejecuta el instalador. |
| macOS (Apple Silicon) | [MinecraftModUpdater_macOS.dmg](https://github.com/CodeInIA/minecraft-mod-updater/releases/latest/download/MinecraftModUpdater_macOS.dmg) | Arrastra la app a Aplicaciones. No está firmada: la primera vez, clic derecho → Abrir (o Ajustes → Privacidad y seguridad → Abrir igualmente). |
| Linux x64 | [MinecraftModUpdater_Linux.tar.gz](https://github.com/CodeInIA/minecraft-mod-updater/releases/latest/download/MinecraftModUpdater_Linux.tar.gz) | Descomprime y ejecuta `./install.sh` (se instala para tu usuario, sin root). `./install.sh --uninstall` lo desinstala. |

**No** necesitas Python. Cada commit a `main` publica automáticamente una release nueva para los tres sistemas.

## Uso
1. Crea un perfil (o edita `client`) y elige su carpeta de mods.
2. Deja la versión y el loader en **Auto** para detectarlos de los mods de la carpeta, o elige una versión concreta para migrar los mods a ella.
3. Pulsa **Buscar actualizaciones**.
4. Marca los mods que quieras y pulsa **Actualizar seleccionados**.

## Desde el código fuente
```bash
pip install -r requirements.txt
python mod_updater.py
```

## Licencia
Copyright (c) 2025-2026 CodeInIA. Uso gratuito solo personal y no comercial; resto de derechos reservados. Consulta [LICENSE](LICENSE).
