import os
import configparser
import shutil
import sys
import platform


def get_config_path():
    """
    Gets the path to the application's configuration file.
    Creates the directory if it doesn't exist.
    """
    # Store config in a hidden folder in the user's home directory
    app_data_path = os.path.join(os.path.expanduser("~"), ".MediaConverter")
    if not os.path.exists(app_data_path):
        os.makedirs(app_data_path)
    return os.path.join(app_data_path, 'config.ini')


def load_config():
    """
    Loads the application settings from the config.ini file.
    """
    config_path = get_config_path()
    config = configparser.ConfigParser()
    if os.path.exists(config_path):
        config.read(config_path)
    return config


def save_config(settings):
    """
    Saves the provided dictionary of settings to the config.ini file.
    """
    config_path = get_config_path()
    config = load_config()
    if 'Settings' not in config:
        config['Settings'] = {}

    for key, value in settings.items():
        config['Settings'][key] = value

    with open(config_path, 'w') as configfile:
        config.write(configfile)


def find_executable(config, name, key):
    """
    Finds an executable's path in a specific order:
    1. The path saved in the user's configuration.
    2. In the same directory as the application (for portable builds).
    3. In the system's PATH environment variable.
    """
    # 1. Check user-defined path from config
    user_path = config.get('Settings', key, fallback=None)
    if user_path and os.path.exists(user_path):
        return user_path

    exe_name = f"{name}.exe" if platform.system() == "Windows" else name

    # 2. Check local application directory
    if getattr(sys, 'frozen', False):
        application_path = os.path.dirname(sys.executable)
    else:
        application_path = os.path.dirname(os.path.abspath(__file__))

    local_path = os.path.join(application_path, exe_name)
    if os.path.exists(local_path):
        return local_path

    # 3. Check system PATH
    return shutil.which(name) or ""