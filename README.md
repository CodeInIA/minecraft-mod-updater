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

## 📋 Requirements

- Python 3.7 or higher
- Required Python packages:
  - requests
  - rich
  - packaging

## 🚀 Installation

1. Install Python from [python.org](https://www.python.org/downloads/)
2. Install the required packages:

```bash
pip install requests rich packaging
```

3. Download and extract the tool to your desired location
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

Feel free to fork this project and submit pull requests with improvements!

## 📜 License

This project is released under the MIT License.

---

Created with ❤️ for the Minecraft modding community

# Minecraft Mod Updater

Minecraft Mod Updater es una herramienta diseñada para facilitar la actualización automática de mods en Minecraft. Con esta herramienta, puedes mantener tus mods actualizados sin complicaciones.

## Características
- Actualización automática de mods.
- Configuración sencilla.
- Compatible con múltiples versiones de Minecraft.

## Instalación

1. Descarga la última versión del instalador desde la sección [Releases](https://github.com/tu-usuario/minecraft-mod-updater/releases) en GitHub.
2. Ejecuta el instalador `MinecraftModUpdater_Setup.exe` y sigue las instrucciones en pantalla.

## Uso

1. Abre la aplicación Minecraft Mod Updater.
2. Configura la carpeta de mods y las opciones deseadas.
3. Haz clic en "Actualizar mods" para comenzar.

## Requisitos
- Windows 7 o superior.
- Python 3.8 o superior (solo para desarrolladores).

## Contribuir
Si deseas contribuir al proyecto:

1. Clona este repositorio:
   ```bash
   git clone https://github.com/tu-usuario/minecraft-mod-updater.git
   ```
2. Instala las dependencias necesarias:
   ```bash
   pip install -r requirements.txt
   ```
3. Realiza tus cambios y envía un pull request.

## Licencia
Este proyecto está licenciado bajo la [MIT License](LICENSE).

---

¡Gracias por usar Minecraft Mod Updater! Si tienes alguna pregunta o problema, no dudes en abrir un [issue](https://github.com/tu-usuario/minecraft-mod-updater/issues).