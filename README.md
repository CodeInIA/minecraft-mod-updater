# 🧩 Minecraft Mod Updater

<img src="updater-logo.png" alt="Mod Updater Logo" width="150" />

A powerful Python tool to automatically keep your Minecraft mods up to date with the latest versions from Modrinth.

## ✨ Features

- **Multiple Profile Support**: Manage up to 10 different mod folder profiles (client, server, modpacks, etc.)
- **Automatic Updates**: Automatically detect and update outdated mods
- **Version Control**: Filter updates by Minecraft version and mod loader
- **Backup System**: Create backups of your mods before updating
- **Customizable Settings**: Configure update intervals, automatic updates, and more
- **User-Friendly Interface**: Beautiful terminal UI with progress indicators and status information

## 📥 Download

**[Download v1.0.0 Release](https://github.com/CodeInIA/minecraft-mod-updater/releases/tag/v1.0.0)**

Available as a Windows Installer with start menu shortcuts and desktop integration.

## 🚀 Installation

### Option 1: Windows Installer
1. Download the installer (`MinecraftModUpdater_Setup.exe`) from the [releases page](https://github.com/CodeInIA/minecraft-mod-updater/releases)
2. Run the installer and follow the on-screen instructions
3. Launch from the Start Menu or desktop shortcut

### Option 2: From Source Code
1. Install Python from [python.org](https://www.python.org/downloads/) (version 3.7 or higher)
2. Install the required packages:
```bash
pip install requests rich packaging
```
3. Download and extract the source code
4. Run the updater:
```bash
python mod_updater.py
```

## 💻 Usage

When you first run the tool, it will guide you through the configuration process:

1. **Profile Configuration**: Set up one or more mod folder profiles
   - Enter a name for each profile (e.g., "client", "server", "fabric115")
   - Specify the path to the mod folder for each profile (relative or absolute)
   - Choose which profile should be active by default

2. **Game Settings**:
   - Set your Minecraft game version(s)
   - Specify your mod loader(s) (fabric, forge, quilt)

3. **Update Settings**:
   - Choose whether to automatically update mods
   - Enable/disable backups before updating
   - Set the update check interval

After configuration, use the main menu to:
- Check for updates for any of your configured profiles
- Modify your configuration settings
- Exit the application

## ⚙️ Configuration

The configuration is stored in `mod_updater_config.json` and includes:

- `mod_folders`: Dictionary of profile names and their mod folder paths
- `current_folder`: The active profile
- `game_versions`: List of Minecraft versions to check for updates
- `loaders`: List of mod loaders (fabric, forge, quilt)
- `auto_update`: Whether to update mods automatically
- `backup_mods`: Whether to create backups before updating
- `check_interval_days`: How often to check for updates (in days)
- `last_check`: When the last update check was performed

## 📝 How It Works

The updater works by:

1. Calculating unique hashes for each mod file
2. Querying the Modrinth API to identify the mods and their current versions
3. Checking if newer versions are available for your specified game version and mod loader
4. Downloading and replacing outdated mods with their newest versions

## 🔒 Privacy & Security

- This tool only communicates with the official Modrinth API
- No personal data is collected or transmitted
- All operations are performed locally on your machine

## 🔍 Troubleshooting

- **Mod Not Updating**: The mod might not be hosted on Modrinth, or the hash might not be recognized
- **Update Errors**: Make sure you have write permissions to the mod folder

## 🤝 Contributing

Suggestions and bug reports are welcome through issues.

## 📜 License

Copyright (c) 2025-2026 CodeInIA. Free for personal, non-commercial use; all other rights reserved. See [LICENSE](LICENSE).

---

Created with ❤️ for the Minecraft modding community

# Minecraft Mod Updater (Español)

Minecraft Mod Updater es una herramienta diseñada para facilitar la actualización automática de mods en Minecraft. Con esta herramienta, puedes mantener tus mods actualizados sin complicaciones.

## Características
- Actualización automática de mods desde Modrinth
- Soporte para múltiples perfiles (cliente, servidor, modpacks)
- Configuración sencilla
- Compatible con múltiples versiones de Minecraft y cargadores de mods

## Descargar

**[Descargar versión v1.0.0](https://github.com/CodeInIA/minecraft-mod-updater/releases/tag/v1.0.0)**

Disponible como instalador para Windows con accesos directos en el menú inicio e integración con el escritorio.

## Instalación

### Opción 1: Instalador para Windows
1. Descarga el instalador (`MinecraftModUpdater_Setup.exe`) desde la sección [Releases](https://github.com/CodeInIA/minecraft-mod-updater/releases)
2. Ejecuta el instalador y sigue las instrucciones en pantalla
3. Abre la aplicación desde el menú Inicio o el escritorio

### Opción 2: Desde el código fuente
1. Instala Python desde [python.org](https://www.python.org/downloads/) (versión 3.7 o superior)
2. Instala las dependencias necesarias:
```bash
pip install requests rich packaging
```
3. Descarga y extrae el código fuente
4. Ejecuta:
```bash
python mod_updater.py
```

## Uso

1. Abre la aplicación Minecraft Mod Updater
2. En el primer uso, se te guiará por el proceso de configuración:
   - Configura las carpetas de mods para tus perfiles
   - Selecciona las versiones de Minecraft y cargadores de mods
   - Establece las preferencias de actualización
3. Usa el menú principal para verificar actualizaciones o cambiar la configuración

## Requisitos
- Windows 7 o superior para las versiones precompiladas
- Python 3.7 o superior (solo para ejecutar desde el código fuente)

## Contribuir
Si deseas contribuir al proyecto:

1. Clona este repositorio:
```bash
git clone https://github.com/CodeInIA/minecraft-mod-updater.git
```
2. Instala las dependencias necesarias:
```bash
pip install requests rich packaging
```
3. Realiza tus cambios y envía un pull request

## Licencia
Copyright (c) 2025-2026 CodeInIA. Uso gratuito solo personal y no comercial; resto de derechos reservados. Consulta [LICENSE](LICENSE).

---

¡Gracias por usar Minecraft Mod Updater! Si tienes alguna pregunta o problema, no dudes en abrir un [issue](https://github.com/CodeInIA/minecraft-mod-updater/issues).