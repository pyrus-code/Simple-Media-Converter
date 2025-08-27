import tkinterdnd2
import ttkbootstrap as ttk
import gui
import utils


def main():
    """
    The main entry point for the application.
    Initializes configuration, finds necessary executables, and launches the GUI.
    """
    # Load application configuration from the config file
    config = utils.load_config()

    # Find the paths to the required ffmpeg executables
    ffmpeg_path = utils.find_executable(config, 'ffmpeg', 'ffmpeg_path')
    ffprobe_path = utils.find_executable(config, 'ffprobe', 'ffprobe_path')
    ffplay_path = utils.find_executable(config, 'ffplay', 'ffplay_path')

    # Set up the main application window using tkinterdnd2 for drag-and-drop
    root = tkinterdnd2.Tk()
    root.title("Media Converter and Joiner")
    root.geometry("580x650")
    root.minsize(580, 600)

    # Load and apply the saved theme at startup
    saved_theme = config.get('Settings', 'theme', fallback='superhero')
    style = ttk.Style(theme=saved_theme)

    # Create and run the main application frame, passing the style object to it
    app_frame = gui.AudioConverterApp(master=root, config=config, style=style,
                                      ffmpeg_path=ffmpeg_path,
                                      ffprobe_path=ffprobe_path,
                                      ffplay_path=ffplay_path)
    root.mainloop()


if __name__ == "__main__":
    main()