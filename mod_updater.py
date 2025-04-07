import os
import json
import hashlib
import requests
import re
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from packaging import version
import shutil
from rich.console import Console
from rich.progress import Progress, TextColumn, BarColumn, SpinnerColumn, TimeElapsedColumn, TaskProgressColumn
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.prompt import Prompt, Confirm
from rich.box import ROUNDED
from rich.layout import Layout
from rich.align import Align
from rich.live import Live

# Palabra clave para cancelar la configuración
CANCEL_KEYWORD = "cancel"

# Constants
CONFIG_FILE = os.path.join(os.getenv("APPDATA"), "minecraft_mod_updater", "mod_updater_config.json")

# Asegúrate de crear el directorio si no existe
os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)

# Ruta por defecto para el perfil "client"
DEFAULT_MINECRAFT_MODS = os.path.join(os.getenv("APPDATA"), ".minecraft", "mods")

MODRINTH_API_URL = "https://api.modrinth.com/v2"
HASH_ALGORITHM = "sha512"
VERSION_FILE_ENDPOINT = f"{MODRINTH_API_URL}/version_files"
VERSION_UPDATE_ENDPOINT = f"{MODRINTH_API_URL}/version_files/update"
DEFAULT_LOADERS = ["fabric"]
DEFAULT_GAME_VERSIONS = ["1.21.5"]

# Configuration data structure
default_config = {
    "mod_folders": {
        "client": DEFAULT_MINECRAFT_MODS,
        "server": "mods-server"
    },
    "current_folder": "client",
    "game_versions": DEFAULT_GAME_VERSIONS,
    "loaders": DEFAULT_LOADERS,
    "auto_update": True,
    "backup_mods": True,
    "check_interval_days": 7,
    "last_check": None
}

# Initialize console
console = Console()

def clear_screen() -> None:
    """Clear the terminal screen."""
    # For Windows
    if os.name == 'nt':
        os.system('cls')
    # For Unix/Linux/MacOS
    else:
        os.system('clear')

def load_config() -> Dict:
    """Load configuration from file or create a default one if it doesn't exist."""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
                # Update with any new default keys
                for key, value in default_config.items():
                    if key not in config:
                        config[key] = value
                return config
        except Exception as e:
            console.print(f"[bold red]Error loading config file: {e}[/bold red]")
            return default_config
    else:
        return default_config

def save_config(config: Dict) -> None:
    """Save configuration to file."""
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=4)

def calculate_hash(file_path: str) -> str:
    """Calculate SHA-512 hash of a file."""
    h = hashlib.sha512()
    with open(file_path, 'rb') as f:
        # Read in chunks to handle large files
        for chunk in iter(lambda: f.read(4096), b''):
            h.update(chunk)
    return h.hexdigest()

def get_mod_files(mod_folder: str) -> List[str]:
    """Get list of all jar files in the mod folder."""
    if not os.path.exists(mod_folder):
        return []
    return [os.path.join(mod_folder, f) for f in os.listdir(mod_folder) if f.endswith('.jar')]

def calculate_hashes(mod_files: List[str], progress=None) -> Dict[str, str]:
    """Calculate hashes for multiple mod files with progress tracking."""
    hashes = {}
    
    if progress:
        task = progress.add_task("[cyan]Calculating hashes...", total=len(mod_files))
        
    for mod_file in mod_files:
        try:
            file_hash = calculate_hash(mod_file)
            hashes[file_hash] = mod_file
            if progress:
                progress.update(task, advance=1, description=f"[cyan]Hashing: {os.path.basename(mod_file)}")
        except Exception as e:
            console.print(f"[yellow]Error calculating hash for {mod_file}: {e}[/yellow]")
    
    return hashes

def check_current_versions(hashes: List[str]) -> Dict:
    """Check current versions of mods by hashes."""
    data = {
        "hashes": hashes,
        "algorithm": HASH_ALGORITHM
    }
    
    response = requests.post(VERSION_FILE_ENDPOINT, json=data)
    if response.status_code == 200:
        return response.json()
    else:
        console.print(f"[bold red]Error checking current versions: {response.status_code} - {response.text}[/bold red]")
        return {}

def check_latest_versions(hashes: List[str], loaders: List[str], game_versions: List[str]) -> Dict:
    """Check latest available versions of mods by hashes."""
    data = {
        "hashes": hashes,
        "algorithm": HASH_ALGORITHM,
        "loaders": loaders,
        "game_versions": game_versions
    }
    
    response = requests.post(VERSION_UPDATE_ENDPOINT, json=data)
    if response.status_code == 200:
        return response.json()
    else:
        console.print(f"[bold red]Error checking latest versions: {response.status_code} - {response.text}[/bold red]")
        return {}

def download_file(url: str, destination: str) -> bool:
    """Download a file from URL to destination."""
    try:
        response = requests.get(url, stream=True)
        if response.status_code == 200:
            with open(destination, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            return True
        else:
            console.print(f"[yellow]Failed to download {url}: {response.status_code}[/yellow]")
            return False
    except Exception as e:
        console.print(f"[yellow]Error downloading {url}: {e}[/yellow]")
        return False

def extract_version_from_filename(filename: str) -> Optional[str]:
    """Extract version string from filename."""
    # Match patterns like: mod-1.2.3.jar or mod-1.2.3-fabric.jar
    patterns = [
        r'-(\d+\.\d+\.\d+(?:-[a-z0-9.]+)?)(?:-[a-z]+)?\.jar$',  # matches -1.2.3.jar or -1.2.3-fabric.jar
        r'-(\d+\.\d+(?:-[a-z0-9.]+)?)(?:-[a-z]+)?\.jar$',        # matches -1.2.jar or -1.2-fabric.jar
        r'[_-]v?(\d+\.\d+\.\d+(?:-[a-z0-9.]+)?)(?:-[a-z]+)?\.jar$', # matches _v1.2.3.jar or -v1.2.3-fabric.jar
        r'[_-]v?(\d+\.\d+(?:-[a-z0-9.]+)?)(?:-[a-z]+)?\.jar$',      # matches _v1.2.jar or -v1.2-fabric.jar
    ]
    
    for pattern in patterns:
        match = re.search(pattern, filename)
        if match:
            return match.group(1)
    return None

def compare_versions(current_version: str, latest_version: str) -> bool:
    """Compare two version strings. Returns True if latest is newer than current."""
    try:
        # Clean versions to ensure compatibility with packaging.version
        current_clean = re.sub(r'[^0-9.]', '', current_version.split('-')[0])
        latest_clean = re.sub(r'[^0-9.]', '', latest_version.split('-')[0])
        
        # Asegurar que haya al menos una versión válida
        if not current_clean or not latest_clean:
            return current_version != latest_version
            
        return version.parse(latest_clean) > version.parse(current_clean)
    except Exception:
        # Fall back to string comparison if version parsing fails
        return current_version != latest_version

def create_backup(mod_folder: str) -> str:
    """Create a backup of the mods folder."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_folder = f"{mod_folder}_backup_{timestamp}"
    
    try:
        shutil.copytree(mod_folder, backup_folder)
        return backup_folder
    except Exception as e:
        console.print(f"[bold red]Error creating backup: {e}[/bold red]")
        return ""

def update_mods(current_versions: Dict, latest_versions: Dict, hash_to_file: Dict, 
                mod_folder: str, backup: bool = True) -> Tuple[List[str], List[str], List[str]]:
    """Update mods to latest versions. Returns lists of updated, failed, and skipped mods."""
    updated_mods = []
    failed_mods = []
    skipped_mods = []
    backup_folder = ""
    
    # Create backup if requested
    if backup and any(h in latest_versions and h in current_versions for h in hash_to_file.keys()):
        backup_folder = create_backup(mod_folder)
        if backup_folder:
            console.print(f"[green]Created backup at: {backup_folder}[/green]")
        else:
            # Don't proceed if backup was requested but failed
            return [], [], list(hash_to_file.values())
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn()
    ) as progress:
        update_task = progress.add_task("[cyan]Updating mods...", total=len(hash_to_file))
        
        for file_hash, file_path in hash_to_file.items():
            mod_name = os.path.basename(file_path)
            progress.update(update_task, description=f"[cyan]Processing: {mod_name}")
            
            # Skip if no info about current version or latest version
            if file_hash not in current_versions or file_hash not in latest_versions:
                skipped_mods.append(file_path)
                progress.update(update_task, advance=1)
                continue
                
            current_version_info = current_versions[file_hash]
            latest_version_info = latest_versions[file_hash]
            
            current_version = current_version_info.get("version_number", "0.0.0")
            latest_version = latest_version_info.get("version_number", "0.0.0")
            
            # Check if versions are different by file
            filename_current_version = extract_version_from_filename(mod_name)
            
            # Determine if update is needed
            needs_update = False
            
            # First check based on version numbers from API
            if current_version and latest_version and compare_versions(current_version, latest_version):
                needs_update = True
            # Also check if the versions appear to be different based on filename
            elif filename_current_version and latest_version and compare_versions(filename_current_version, latest_version):
                needs_update = True
            
            if not needs_update:
                skipped_mods.append(file_path)
                progress.update(update_task, advance=1)
                continue
            
            # Get download URL for the latest version
            download_url = None
            for file_info in latest_version_info.get("files", []):
                if file_info.get("primary", False):
                    download_url = file_info.get("url")
                    break
            
            if not download_url:
                skipped_mods.append(file_path)
                progress.update(update_task, advance=1)
                continue
            
            # Create temp file name for download
            new_file_name = os.path.join(mod_folder, f"UPDATING_{mod_name}")
            
            # Download the new version
            if download_file(download_url, new_file_name):
                # Remove old file and rename new one
                try:
                    os.remove(file_path)
                    
                    # Construct new filename based on mod name and version
                    base_name = mod_name
                    for pattern in [r'-\d+\.\d+\.\d+.*\.jar$', r'-\d+\.\d+.*\.jar$', r'_v\d+\.\d+\.\d+.*\.jar$', r'_v\d+\.\d+.*\.jar$']:
                        base_name = re.sub(pattern, '.jar', base_name)
                    
                    # Determine loader suffix if present in the original filename
                    loader_suffix = ""
                    for loader in DEFAULT_LOADERS:
                        if f"-{loader}" in mod_name.lower():
                            loader_suffix = f"-{loader}"
                            break
                    
                    # Create the new filename with the updated version
                    new_mod_name = base_name.replace('.jar', f'-{latest_version}{loader_suffix}.jar')
                    final_path = os.path.join(mod_folder, new_mod_name)
                    
                    os.rename(new_file_name, final_path)
                    updated_mods.append(f"{mod_name} → {new_mod_name}")
                except Exception as e:
                    failed_mods.append(file_path)
                    console.print(f"[bold red]Error updating {mod_name}: {e}[/bold red]")
            else:
                failed_mods.append(file_path)
            
            progress.update(update_task, advance=1)
    
    return updated_mods, failed_mods, skipped_mods

def print_update_summary(current_versions: Dict, latest_versions: Dict, hash_to_file: Dict) -> bool:
    """Print a summary of available updates and return whether updates are available."""
    updates_available = False
    
    # Create a beautiful table for the summary
    table = Table(
        title="📊 Mod Update Summary",
        box=ROUNDED,
        border_style="cyan",
        header_style="bold cyan",
        expand=True
    )
    
    table.add_column("Mod", style="cyan")
    table.add_column("Current Version", style="yellow")
    table.add_column("Latest Version", style="green")
    table.add_column("Status", style="magenta")
    
    for file_hash, file_path in hash_to_file.items():
        mod_name = os.path.basename(file_path)
        
        if file_hash not in current_versions:
            table.add_row(mod_name, "Unknown", "Unknown", "❓ Not found in Modrinth")
            continue
            
        current_version_info = current_versions[file_hash]
        current_version = current_version_info.get("version_number", "Unknown")
        
        if file_hash not in latest_versions:
            table.add_row(mod_name, current_version, "Unknown", "❓ No update info")
            continue
            
        latest_version_info = latest_versions[file_hash]
        latest_version = latest_version_info.get("version_number", "Unknown")
        
        # Check if versions are different
        if current_version != "Unknown" and latest_version != "Unknown":
            try:
                if compare_versions(current_version, latest_version):
                    status = "⬆️ Update Available"
                    updates_available = True
                else:
                    status = "✅ Up to date"
            except Exception:
                status = "⚠️ Version comparison error"
        else:
            status = "❓ Unknown status"
            
        table.add_row(mod_name, current_version, latest_version, status)
    
    console.print(table)
    return updates_available

def setup_config() -> Dict:
    """Setup or modify configuration interactively."""
    config = load_config()
    
    display_header()
    console.print(Panel(
        Text("🔧 Configuration Settings", style="bold cyan", justify="center"),
        border_style="cyan",
        box=ROUNDED,
        padding=(1, 2)
    ))
    
    # Mostrar indicación de que se puede cancelar con la palabra clave
    console.print(Panel(
        Text(f"📝 Escribe '{CANCEL_KEYWORD}' en cualquier momento para cancelar y volver al menú principal", 
             style="yellow", justify="center"),
        border_style="yellow",
        box=ROUNDED
    ))
    
    # Create form-like layout
    config_table = Table(box=ROUNDED, show_header=False, border_style="cyan", expand=True)
    config_table.add_column("Setting", style="cyan")
    config_table.add_column("Value")
    
    # Mod folders
    config_table.add_row("", "")
    config_table.add_row("[bold cyan]📁 Mod Folders[/bold cyan]", "")
    
    # Get existing mod folders or create empty dict
    mod_folders = config.get("mod_folders", {})
    if not mod_folders:
        mod_folders = {}
    
    # Profile management
    new_mod_folders = {}
    profile_count = 0
    max_profiles = 10
    
    console.print("\n[bold cyan]Profile Configuration[/bold cyan]")
    console.print("[italic]You can configure up to 10 different mod folder profiles[/italic]\n")
    
    # Add or edit profiles
    adding_profiles = True
    
    while adding_profiles and profile_count < max_profiles:
        # If we already have profiles, ask to edit existing ones first
        if profile_count > 0:
            continue_adding = Confirm.ask(
                f"\n[cyan]Would you like to add another profile?[/cyan] ({profile_count}/{max_profiles})",
                default=True if profile_count < 2 else False
            )
            if not continue_adding:
                adding_profiles = False
                continue
        
        # Profile name - Primer perfil es "client" por defecto
        if profile_count == 0:
            profile_name = Prompt.ask(
                "\n[cyan]Enter profile name[/cyan] (e.g. client, server, modpack1)",
                default="client"  # Primer perfil tiene nombre por defecto "client"
            )
        elif profile_count == 1:
            profile_name = Prompt.ask(
                "\n[cyan]Enter profile name[/cyan] (e.g. client, server, modpack1)",
                default="server"  # Segundo perfil tiene nombre por defecto "server"
            )
        else:
            profile_name = Prompt.ask(
                "\n[cyan]Enter profile name[/cyan] (e.g. client, server, modpack1)",
                default=f"profile{profile_count+1}"  # Los demás perfiles no tienen nombre por defecto
            )
        
        # Check for cancellation
        if profile_name.lower() == CANCEL_KEYWORD:
            console.print(Panel(
                Text("🚫 Configuración cancelada. Volviendo al menú principal...", 
                     style="bold yellow", justify="center"),
                border_style="yellow",
                box=ROUNDED
            ))
            return config  # Volver al menú principal sin guardar cambios
            
        # Check for duplicate names
        if profile_name in new_mod_folders:
            console.print(f"[yellow]Profile '{profile_name}' already exists. Please use a different name.[/yellow]")
            continue
            
        # Mod folder path for this profile - Solo el primer perfil "client" tiene ruta por defecto
        if profile_count == 0 and profile_name.lower() == "client":
            # Ruta por defecto para el perfil "client" usando la carpeta .minecraft/mods del usuario
            default_path = DEFAULT_MINECRAFT_MODS
        elif profile_count == 1 and profile_name.lower() == "server":
            # El segundo perfil no tiene ruta por defecto específica
            default_path = mod_folders.get(profile_name, f"mods-{profile_name}")
        else:
            # Los demás perfiles no tienen ruta por defecto
            default_path = mod_folders.get(profile_name, f"mods-{profile_name}")
            
        folder_path = Prompt.ask(
            f"[cyan]Enter mod folder path for profile '{profile_name}'[/cyan] (relative or absolute path)",
            default=default_path
        )
        
        # Check for cancellation
        if folder_path.lower() == CANCEL_KEYWORD:
            console.print(Panel(
                Text("🚫 Configuración cancelada. Volviendo al menú principal...", 
                     style="bold yellow", justify="center"),
                border_style="yellow",
                box=ROUNDED
            ))
            return config  # Volver al menú principal sin guardar cambios
            
        # Success message with fancy styling
        new_mod_folders[profile_name] = folder_path
        profile_count += 1
        
        console.print(Panel(
            f"✅ Profile [bold cyan]{profile_name}[/bold cyan] configured with path: [green]{folder_path}[/green]",
            border_style="green",
            box=ROUNDED,
            padding=(0, 1)
        ))
    
    # Display summary of profiles
    profile_summary = Table(title="[bold cyan]Configured Profiles[/bold cyan]", box=ROUNDED, border_style="cyan")
    profile_summary.add_column("Profile", style="bold cyan")
    profile_summary.add_column("Path", style="green")
    
    for profile, path in new_mod_folders.items():
        profile_summary.add_row(profile, path)
    
    console.print(profile_summary)
    
    # Set current folder
    current = config.get("current_folder", next(iter(new_mod_folders)) if new_mod_folders else "client")
    if current not in new_mod_folders and new_mod_folders:
        current = next(iter(new_mod_folders))
        
    profile_choices = list(new_mod_folders.keys())
    selected = Prompt.ask(
        "\n[cyan]🎯 Select active profile[/cyan]",
        choices=profile_choices,
        default=current if current in profile_choices else profile_choices[0]
    )
    config_table.add_row("Active profile", f"[bold cyan]{selected}[/bold cyan]")
    
    # Check for cancellation
    if selected.lower() == CANCEL_KEYWORD:
        console.print(Panel(
            Text("🚫 Configuración cancelada. Volviendo al menú principal...", 
                 style="bold yellow", justify="center"),
            border_style="yellow",
            box=ROUNDED
        ))
        return config  # Volver al menú principal sin guardar cambios
        
    # Game versions
    config_table.add_row("", "")
    config_table.add_row("[bold cyan]🎮 Game Settings[/bold cyan]", "")
    
    current_game_versions = config.get("game_versions", DEFAULT_GAME_VERSIONS)
    game_versions_str = ", ".join(current_game_versions)
    new_game_versions_str = Prompt.ask(
        "\n[cyan]🔢 Game versions[/cyan] (comma-separated)",
        default=game_versions_str
    )
    
    # Check for cancellation
    if new_game_versions_str.lower() == CANCEL_KEYWORD:
        console.print(Panel(
            Text("🚫 Configuración cancelada. Volviendo al menú principal...", 
                 style="bold yellow", justify="center"),
            border_style="yellow",
            box=ROUNDED
        ))
        return config  # Volver al menú principal sin guardar cambios
        
    new_game_versions = [v.strip() for v in new_game_versions_str.split(",")]
    config_table.add_row("Game versions", f"[green]{new_game_versions_str}[/green]")
    
    # Loaders
    current_loaders = config.get("loaders", DEFAULT_LOADERS)
    loaders_str = ", ".join(current_loaders)
    new_loaders_str = Prompt.ask(
        "[cyan]🧩 Mod loaders[/cyan] (comma-separated)",
        default=loaders_str
    )
    
    # Check for cancellation
    if new_loaders_str.lower() == CANCEL_KEYWORD:
        console.print(Panel(
            Text("🚫 Configuración cancelada. Volviendo al menú principal...", 
                 style="bold yellow", justify="center"),
            border_style="yellow",
            box=ROUNDED
        ))
        return config  # Volver al menú principal sin guardar cambios
        
    new_loaders = [l.strip() for l in new_loaders_str.split(",")]
    config_table.add_row("Mod loaders", f"[green]{new_loaders_str}[/green]")
    
    # Auto-update
    config_table.add_row("", "")
    config_table.add_row("[bold cyan]🔧 Update Settings[/bold cyan]", "")
    
    auto_update = config.get("auto_update", True)
    new_auto_update = Confirm.ask(
        "\n[cyan]🔄 Automatically update mods[/cyan]",
        default=auto_update
    )
    config_table.add_row("Auto-update", "[green]Yes[/green]" if new_auto_update else "[yellow]No[/yellow]")
    
    # Check for cancellation
    if new_auto_update.lower() == CANCEL_KEYWORD:
        console.print(Panel(
            Text("🚫 Configuración cancelada. Volviendo al menú principal...", 
                 style="bold yellow", justify="center"),
            border_style="yellow",
            box=ROUNDED
        ))
        return config  # Volver al menú principal sin guardar cambios
        
    # Backup mods
    backup_mods = config.get("backup_mods", True)
    new_backup_mods = Confirm.ask(
        "[cyan]💾 Create backups before updating[/cyan]",
        default=backup_mods
    )
    config_table.add_row("Create backups", "[green]Yes[/green]" if new_backup_mods else "[yellow]No[/yellow]")
    
    # Check for cancellation
    if new_backup_mods.lower() == CANCEL_KEYWORD:
        console.print(Panel(
            Text("🚫 Configuración cancelada. Volviendo al menú principal...", 
                 style="bold yellow", justify="center"),
            border_style="yellow",
            box=ROUNDED
        ))
        return config  # Volver al menú principal sin guardar cambios
        
    # Check interval
    check_interval = config.get("check_interval_days", 7)
    new_check_interval = int(Prompt.ask(
        "[cyan]⏱️ Check interval (days)[/cyan]",
        default=str(check_interval)
    ))
    
    # Check for cancellation
    if str(new_check_interval).lower() == CANCEL_KEYWORD:
        console.print(Panel(
            Text("🚫 Configuración cancelada. Volviendo al menú principal...", 
                 style="bold yellow", justify="center"),
            border_style="yellow",
            box=ROUNDED
        ))
        return config  # Volver al menú principal sin guardar cambios
        
    config_table.add_row("Check interval", f"[green]{new_check_interval} days[/green]")
    
    # Update config
    config["mod_folders"] = new_mod_folders
    config["current_folder"] = selected
    config["game_versions"] = new_game_versions
    config["loaders"] = new_loaders
    config["auto_update"] = new_auto_update
    config["backup_mods"] = new_backup_mods
    config["check_interval_days"] = new_check_interval
    
    # Show summary
    console.print("\n")
    console.print(Panel(
        config_table,
        title="[bold cyan]Configuration Summary[/bold cyan]",
        border_style="cyan",
        box=ROUNDED,
        padding=(1, 2)
    ))
    
    # Save config
    save_config(config)
    console.print(Panel(
        Text("✅ Configuration saved successfully!", style="bold green", justify="center"),
        border_style="green",
        box=ROUNDED
    ))
    
    input("\nPress Enter to continue...")
    return config

def display_header() -> None:
    """Display application header."""
    clear_screen()
    header_text = Text("✨ Minecraft Mod Updater ✨", style="bold cyan", justify="center")
    subtitle_text = Text("Keep your mods up to date automatically", style="italic dim cyan", justify="center")
    author_text = Text("By CodeInIA", style="bold magenta", justify="center")
    
    console.print("\n")
    console.print(Panel(
        Text.assemble(
            header_text, 
            "\n", 
            subtitle_text,
            "\n",
            author_text
        ),
        border_style="cyan",
        box=ROUNDED,
        padding=(1, 4)
    ))
    console.print("\n")

def display_footer() -> None:
    """Display application footer."""
    console.print("\n")
    console.print(Panel(
        Text("Press Ctrl+C to exit at any time", style="dim", justify="center"),
        border_style="dim",
        box=ROUNDED
    ))

def main() -> None:
    """Main application function."""
    display_header()
    
    try:
        config = load_config()
        
        # Check if config exists or needs setup
        if not os.path.exists(CONFIG_FILE):
            console.print(Panel("[yellow]No configuration found. Let's set up your preferences.[/yellow]", 
                               border_style="yellow", box=ROUNDED))
            config = setup_config()
        
        # Get the mod folders
        mod_folders = config.get("mod_folders", {"client": "mods-client", "server": "mods-server"})
        
        # Show menu with options
        while True:
            display_header()
            console.print(Panel(
                Text("🧩 Main Menu", style="bold cyan", justify="center"),
                border_style="cyan", 
                box=ROUNDED
            ))
            
            # Create a table for menu options with fixed width to ensure proper alignment
            menu_table = Table(
                box=ROUNDED, 
                show_header=False, 
                border_style="cyan", 
                expand=True
            )
            menu_table.add_column("Option", style="cyan", justify="center", width=5)
            menu_table.add_column("Description", style="white")
            
            # Option for each profile
            option_num = 1
            profile_options = {}
            
            for profile, folder in mod_folders.items():
                # Choose appropriate icon based on profile name
                if profile.lower() == "client":
                    icon = "👤"
                elif profile.lower() == "server":
                    icon = "💻"
                else:
                    icon = "📁"
                    
                text = f"{icon} [green]Check updates for {profile} profile[/green] ([cyan]{folder}[/cyan])"
                menu_table.add_row(f"{option_num}", text)
                profile_options[str(option_num)] = profile
                option_num += 1
            
            # Configuration and exit options
            config_option = str(option_num)
            menu_table.add_row(f"{option_num}", f"🔧 [yellow]Configure settings[/yellow]")
            option_num += 1
            
            exit_option = str(option_num)
            menu_table.add_row(f"{option_num}", f"🚪 [red]Exit[/red]")
            
            console.print(menu_table)
            
            # Get user choice
            all_options = list(profile_options.keys()) + [config_option, exit_option]
            choice = Prompt.ask("\n💬 Choose an option", choices=all_options, default="1")
            
            # Process user choice
            if choice == exit_option:
                clear_screen()
                console.print(Panel(
                    Text("👋 Thanks for using Minecraft Mod Updater!", style="cyan", justify="center"),
                    border_style="cyan",
                    box=ROUNDED
                ))
                break
            elif choice == config_option:
                config = setup_config()
                # Update mod_folders after config change
                mod_folders = config.get("mod_folders", {"client": "mods-client", "server": "mods-server"})
            else:
                # User selected a profile, set as active and proceed with update check
                selected_profile = profile_options[choice]
                config["current_folder"] = selected_profile
                save_config(config)
                
                clear_screen()
                check_for_updates(config, selected_profile)
                
                # Pause after update check
                input("\nPress Enter to return to the main menu...")
    
    except KeyboardInterrupt:
        clear_screen()
        console.print(Panel(
            Text("👋 Operation cancelled by user", style="yellow", justify="center"),
            border_style="yellow",
            box=ROUNDED
        ))
    except Exception as e:
        console.print(Panel(
            Text(f"❌ An error occurred: {e}", style="bold red", justify="center"),
            border_style="red",
            box=ROUNDED
        ))
        # Add more detailed log for debugging
        import traceback
        console.print(f"[dim]{traceback.format_exc()}[/dim]", highlight=False)
        input("\nPress Enter to continue...")
    
    display_footer()

def check_for_updates(config: Dict, active_profile: str) -> None:
    """Check for mod updates for the specified profile."""
    display_header()
    
    # Get the active mod folder
    mod_folders = config.get("mod_folders", {"client": "mods-client", "server": "mods-server"})
    mod_folder = mod_folders.get(active_profile, "mods-client")
    
    # Choose appropriate icon based on profile name
    profile_icon = "👤" if active_profile.lower() == "client" else "💻" if active_profile.lower() == "server" else "📁"
    
    console.print(Panel(
        Text(f"{profile_icon} Checking updates for: [bold cyan]{active_profile}[/bold cyan] profile ([cyan]{mod_folder}[/cyan])", justify="center"),
        border_style="cyan",
        box=ROUNDED,
        title="[bold cyan]Update Checker[/bold cyan]"
    ))
    
    # Check if we should check for updates based on last check time
    last_check = config.get("last_check")
    check_interval = config.get("check_interval_days", 7)
    
    if last_check:
        last_check_date = datetime.fromisoformat(last_check)
        days_since_check = (datetime.now() - last_check_date).days
        
        if days_since_check < check_interval:
            console.print(Panel(
                Text.assemble(
                    "⏰ ", 
                    Text(f"Last check was {days_since_check} days ago.", style="yellow"),
                    "\n",
                    Text(f"Your check interval is set to {check_interval} days.", style="yellow")
                ),
                border_style="yellow",
                box=ROUNDED
            ))
            should_check = Confirm.ask("Do you want to check for updates anyway?", default=False)
            
            if not should_check:
                return
    
    # Update last check time
    config["last_check"] = datetime.now().isoformat()
    save_config(config)
    
    # Start the update process
    mod_files = get_mod_files(mod_folder)
    
    if not mod_files:
        console.print(Panel(
            Text(f"❌ No mod files found in the profile folder!\n\nPath: {mod_folder}", style="bold red", justify="center"),
            border_style="red",
            box=ROUNDED,
            title="[bold red]Error[/bold red]"
        ))
        return
    
    console.print(Panel(
        Text(f"📦 Found {len(mod_files)} mod files in the profile folder", style="green", justify="center"),
        border_style="green",
        box=ROUNDED
    ))
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        console=console
    ) as progress:
        # Calculate hashes
        hash_to_file = calculate_hashes(mod_files, progress)
        
        if not hash_to_file:
            console.print(Panel(
                Text("❌ Failed to calculate hashes for any mods", style="bold red", justify="center"),
                border_style="red",
                box=ROUNDED
            ))
            return
        
        # Check current versions
        check_task = progress.add_task("[cyan]Checking current versions...", total=1)
        current_versions = check_current_versions(list(hash_to_file.keys()))
        progress.update(check_task, completed=1)
        
        # Check latest versions
        update_task = progress.add_task("[cyan]Checking for updates...", total=1)
        latest_versions = check_latest_versions(
            list(hash_to_file.keys()),
            config.get("loaders", DEFAULT_LOADERS),
            config.get("game_versions", DEFAULT_GAME_VERSIONS)
        )
        progress.update(update_task, completed=1)
    
    # Print update summary
    updates_available = print_update_summary(current_versions, latest_versions, hash_to_file)
    
    if not updates_available:
        console.print(Panel(
            Text("✅ All mods are up to date!", style="bold green", justify="center"),
            border_style="green",
            box=ROUNDED,
            title="[bold green]Status[/bold green]"
        ))
        return
    
    # Ask to update if auto-update is disabled
    should_update = config.get("auto_update", True)
    if not should_update:
        should_update = Confirm.ask("🔄 Do you want to update the mods?", default=True)
    
    if should_update:
        console.print("\n")
        if config.get("backup_mods", True):
            console.print(Panel(
                "💾 Backups will be created before updating",
                border_style="cyan",
                box=ROUNDED
            ))
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeElapsedColumn(),
            console=console
        ) as progress:
            update_task = progress.add_task("[cyan]Updating mods...", total=1)
            updated, failed, skipped = update_mods(
                current_versions,
                latest_versions,
                hash_to_file,
                mod_folder,
                config.get("backup_mods", True)
            )
            progress.update(update_task, completed=1)
        
        # Show results in a beautiful summary panel
        result_table = Table(box=ROUNDED, show_header=False, expand=True)
        result_table.add_column("Category", style="cyan")
        result_table.add_column("Count", style="bold")
        
        result_table.add_row("✅ Updated", f"[green]{len(updated)} mods[/green]")
        result_table.add_row("❌ Failed", f"[red]{len(failed)} mods[/red]")
        result_table.add_row("⏭️ Skipped", f"[yellow]{len(skipped)} mods[/yellow]")
        
        console.print(Panel(
            result_table,
            title="[bold cyan]Update Results[/bold cyan]",
            border_style="cyan",
            box=ROUNDED
        ))
        
        if updated:
            updated_table = Table(box=ROUNDED, show_header=True, expand=True)
            updated_table.add_column("Updated Mods", style="green")
            
            for mod in updated:
                updated_table.add_row(f"✅ {mod}")
            
            console.print(Panel(
                updated_table,
                title="[bold green]Updated Mods[/bold green]",
                border_style="green",
                box=ROUNDED
            ))
        
        if failed:
            failed_table = Table(box=ROUNDED, show_header=True, expand=True)
            failed_table.add_column("Failed Mods", style="red")
            
            for mod in failed:
                failed_table.add_row(f"❌ {os.path.basename(mod)}")
            
            console.print(Panel(
                failed_table,
                title="[bold red]Failed Updates[/bold red]",
                border_style="red",
                box=ROUNDED
            ))
        
        console.print(Panel(
            Text("✨ Update process completed!", style="bold cyan", justify="center"),
            border_style="cyan",
            box=ROUNDED
        ))

if __name__ == "__main__":
    main()