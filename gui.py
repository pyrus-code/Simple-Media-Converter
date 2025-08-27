import tkinter as tk
from tkinter import filedialog, messagebox
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
import os
import platform
import subprocess
import threading
import queue
import re
import tkinterdnd2
import webbrowser
from ttkbootstrap.scrolled import ScrolledText
import logic
import utils


class FileManager:
    """Manages the file list, including the UI and all related logic."""

    def __init__(self, app, config):
        self.app = app
        self.config = config
        self.file_paths = []
        self.drag_start_index = None

        # --- Supported File Types ---
        self.supported_audio = ['.mp3', '.aac', '.m4a', '.ogg', '.wav', '.flac', '.alac', '.aiff', '.wma']
        self.supported_video = ['.mp4', '.mov', '.avi', '.webm', '.wmv', '.flv', '.mkv', '.mts', '.mpeg-4', '.avchd']
        self.supported_extensions = self.supported_audio + self.supported_video

        self.show_full_path_var = tk.BooleanVar(
            value=self.config.getboolean('Settings', 'show_full_path', fallback=True))

    def create_file_display_frame(self, parent):
        """Creates and returns the frame containing the file listbox and its controls."""
        file_frame = ttk.Labelframe(parent, text="Audio/Video Files (Drag & Drop Here)", padding=5)
        file_frame.columnconfigure(0, weight=1)
        file_frame.rowconfigure(0, weight=1)

        self.file_listbox = tk.Listbox(file_frame, selectmode=tk.SINGLE, height=8, borderwidth=0,
                                       highlightthickness=0)
        self.file_listbox.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        self.file_listbox.drop_target_register(tkinterdnd2.DND_FILES)
        self.file_listbox.dnd_bind('<<Drop>>', self.drop_files)

        # Bindings for drag-and-drop reordering
        self.file_listbox.bind('<Button-1>', self.on_drag_start)
        self.file_listbox.bind('<B1-Motion>', self.on_drag_motion)
        self.file_listbox.bind('<ButtonRelease-1>', self.on_drag_release)

        self.list_scrollbar = ttk.Scrollbar(file_frame, orient=VERTICAL, command=self.file_listbox.yview)
        self.list_scrollbar.grid(row=0, column=1, sticky="ns", pady=5)
        self.file_listbox.configure(yscrollcommand=self.list_scrollbar.set)

        self.path_check = ttk.Checkbutton(file_frame, text="Show full path",
                                          variable=self.show_full_path_var,
                                          command=self.on_path_check_change, bootstyle="primary")
        self.path_check.grid(row=1, column=0, sticky="w", padx=5, pady=(0, 5))

        return file_frame

    def add_files(self):
        """Open a file dialog to add files."""
        filetypes = (("All Media Files", ' '.join(f"*{ext}" for ext in self.supported_extensions)),
                     ("Audio Files", ' '.join(f"*{ext}" for ext in self.supported_audio)),
                     ("Video Files", ' '.join(f"*{ext}" for ext in self.supported_video)),
                     ("All files", "*.*"))
        files = filedialog.askopenfilenames(title="Select Audio or Video Files", filetypes=filetypes)
        if files: self.add_files_to_list(files)

    def add_files_to_list(self, files):
        """Add a list of file paths to the internal list and update the UI."""
        unsupported_files = []
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext not in self.supported_extensions:
                unsupported_files.append(os.path.basename(f))
                continue
            if len(self.file_paths) < 20 and f not in self.file_paths:
                self.file_paths.append(f)
            elif len(self.file_paths) >= 20:
                messagebox.showwarning("Limit Reached", "You can only add up to 20 files.")
                break
        if unsupported_files:
            messagebox.showwarning("Unsupported Files",
                                   "The following files have unsupported formats and were skipped:\n\n" + "\n".join(
                                       unsupported_files))
        self.update_file_list_view()

    def drop_files(self, event):
        """Handle files being dropped onto the listbox."""
        files = re.findall(r'\{[^{}]*\}|\S+', event.data)
        cleaned_files = [f.strip('{}') for f in files]
        self.add_files_to_list(cleaned_files)

    def update_file_list_view(self):
        """Refresh the file listbox with the current file paths."""
        self.file_listbox.delete(0, tk.END)
        show_full = self.show_full_path_var.get()
        for path in self.file_paths:
            display_text = path if show_full else os.path.basename(path)
            self.file_listbox.insert(tk.END, display_text)
        self.app.update_status(f"{len(self.file_paths)} files selected.")

    def on_path_check_change(self):
        """Handle toggling the 'Show full path' checkbox."""
        self.update_file_list_view()
        self.app.save_app_config()

    def remove_selected(self):
        """Remove selected files from the list."""
        selection = self.file_listbox.curselection()
        if not selection: return
        for i in reversed(selection):
            del self.file_paths[i]
        self.update_file_list_view()

    def clear_all(self):
        """Remove all files from the list."""
        self.file_paths.clear()
        self.update_file_list_view()

    def on_drag_start(self, event):
        """Records the starting index of a drag operation."""
        widget = event.widget
        index = widget.nearest(event.y)
        if index != -1:
            self.drag_start_index = index

    def on_drag_motion(self, event):
        """Provides visual feedback during a drag operation."""
        if self.drag_start_index is None:
            return
        widget = event.widget
        index = widget.nearest(event.y)
        if index != -1:
            widget.selection_clear(0, tk.END)
            widget.selection_set(index)
            widget.activate(index)

    def on_drag_release(self, event):
        """Completes the drag-and-drop reorder operation."""
        if self.drag_start_index is None:
            return
        widget = event.widget
        end_index = widget.nearest(event.y)

        if end_index != -1:
            moved_item = self.file_paths.pop(self.drag_start_index)
            self.file_paths.insert(end_index, moved_item)
            self.update_file_list_view()
            self.file_listbox.selection_set(end_index)

        self.drag_start_index = None

    def get_selected_file_path(self):
        """Returns the path of the currently selected file, or None."""
        selected_indices = self.file_listbox.curselection()
        if not selected_indices:
            return None
        return self.file_paths[selected_indices[0]]

    def get_all_file_paths(self):
        """Returns the list of all file paths."""
        return self.file_paths

    def get_settings(self):
        """Returns a dictionary of file-manager-related settings for saving."""
        return {'show_full_path': str(self.show_full_path_var.get())}

    def restore_defaults(self):
        """Resets file manager settings to their default values."""
        self.show_full_path_var.set(True)
        self.update_file_list_view()


class HardwareManager:
    """Manages all hardware acceleration settings, UI, and logic."""

    def __init__(self, app, config, ffmpeg_path_var, gui_queue):
        self.app = app
        self.config = config
        self.ffmpeg_path_var = ffmpeg_path_var
        self.gui_queue = gui_queue

        self.hw_encoders = []
        self.hw_accel_var = tk.BooleanVar(
            value=self.config.getboolean('Settings', 'hw_accel_enabled', fallback=True))
        self.advanced_hw_accel_var = tk.BooleanVar(
            value=self.config.getboolean('Settings', 'advanced_hw_accel', fallback=False))
        self.codec_test_run_var = tk.BooleanVar(
            value=self.config.getboolean('Settings', 'codec_test_run', fallback=False))
        self.advanced_hw_active_status_var = tk.StringVar(value="Inactive")
        self.codec_test_status_var = tk.StringVar(value="Status: Not Tested")
        self.nvidia_detected_var = tk.StringVar(value="Not Detected")
        self.amd_detected_var = tk.StringVar(value="Not Detected")
        self.intel_detected_var = tk.StringVar(value="Not Detected")
        self.gpu_selection_var = tk.StringVar(
            value=self.config.get('Settings', 'gpu_selection', fallback="Detect Automatically"))

        # Initialize radio button attributes to None
        self.auto_detect_radio = None
        self.nvidia_radio = None
        self.amd_radio = None
        self.intel_radio = None

        self.detect_hw_encoders()
        self.update_advanced_hw_status()

    def create_hw_accel_frame(self, parent):
        """Creates and returns the hardware acceleration frame for the options window."""
        hw_accel_frame = ttk.Labelframe(parent, text="Hardware Acceleration", padding=5)

        self.hw_accel_check = ttk.Checkbutton(hw_accel_frame, text="Enable Hardware Accelerated Encoding (Default)",
                                              variable=self.hw_accel_var, command=self.on_hw_accel_toggle,
                                              bootstyle="primary")
        self.hw_accel_check.pack(anchor="w", padx=10, pady=5)

        adv_hw_frame = ttk.Frame(hw_accel_frame)
        adv_hw_frame.pack(fill='x', padx=10, pady=(10, 2))

        self.advanced_hw_check = ttk.Checkbutton(adv_hw_frame, text="Advanced Hardware Acceleration (Prioritize GPU)",
                                                 variable=self.advanced_hw_accel_var,
                                                 command=self.on_advanced_hw_toggle,
                                                 bootstyle="primary")
        self.advanced_hw_check.pack(side=LEFT, anchor="w")

        active_status_label = ttk.Label(adv_hw_frame, textvariable=self.advanced_hw_active_status_var)
        active_status_label.pack(side=LEFT, anchor="w", padx=10)

        self.config_button = ttk.Button(hw_accel_frame, text="Configuration...",
                                        command=self.open_configuration_window, bootstyle="info-outline")
        self.config_button.pack(anchor="w", padx=10, pady=10)

        self.on_hw_accel_toggle()
        return hw_accel_frame

    def open_configuration_window(self):
        """Open the hardware acceleration configuration window."""
        config_window = ttk.Toplevel(master=self.app, title="Hardware Acceleration Configuration")
        config_window.geometry("550x450")
        config_window.transient(self.app)
        config_window.grab_set()

        main_frame = ttk.Frame(config_window, padding=10)
        main_frame.pack(fill='both', expand=True)

        detection_frame = ttk.Labelframe(main_frame, text="GPU Detection", padding=10)
        detection_frame.pack(fill='x', pady=5)
        ttk.Label(detection_frame, text="NVIDIA GPU:").grid(row=0, column=0, sticky='w', padx=5, pady=2)
        ttk.Label(detection_frame, textvariable=self.nvidia_detected_var).grid(row=0, column=1, sticky='w', padx=5,
                                                                               pady=2)
        ttk.Label(detection_frame, text="AMD GPU:").grid(row=1, column=0, sticky='w', padx=5, pady=2)
        ttk.Label(detection_frame, textvariable=self.amd_detected_var).grid(row=1, column=1, sticky='w', padx=5, pady=2)
        ttk.Label(detection_frame, text="INTEL GPU:").grid(row=2, column=0, sticky='w', padx=5, pady=2)
        ttk.Label(detection_frame, textvariable=self.intel_detected_var).grid(row=2, column=1, sticky='w', padx=5,
                                                                              pady=2)

        selection_frame = ttk.Labelframe(main_frame, text="GPU Selection", padding=10)
        selection_frame.pack(fill='x', pady=5)
        self.auto_detect_radio = ttk.Radiobutton(selection_frame, text="Detect Automatically",
                                                 variable=self.gpu_selection_var, value="Detect Automatically")
        self.auto_detect_radio.pack(anchor='w', padx=5)
        self.nvidia_radio = ttk.Radiobutton(selection_frame, text="NVIDIA GPU", variable=self.gpu_selection_var,
                                            value="NVIDIA")
        self.nvidia_radio.pack(anchor='w', padx=5)
        self.amd_radio = ttk.Radiobutton(selection_frame, text="AMD GPU", variable=self.gpu_selection_var, value="AMD")
        self.amd_radio.pack(anchor='w', padx=5)
        self.intel_radio = ttk.Radiobutton(selection_frame, text="INTEL GPU", variable=self.gpu_selection_var,
                                           value="INTEL")
        self.intel_radio.pack(anchor='w', padx=5)

        test_frame = ttk.Labelframe(main_frame, text="Codec Test", padding=10)
        test_frame.pack(fill='x', pady=5)
        test_status_frame = ttk.Frame(test_frame)
        test_status_frame.pack(fill='x', pady=5)
        self.hw_test_button = ttk.Button(test_status_frame, text="Run Codec Test", command=self.run_codec_test,
                                         bootstyle="info-outline")
        self.hw_test_button.pack(side=LEFT, anchor="w")
        codec_status_label = ttk.Label(test_status_frame, textvariable=self.codec_test_status_var)
        codec_status_label.pack(side=LEFT, anchor="w", padx=10)
        active_status_label = ttk.Label(test_status_frame, textvariable=self.advanced_hw_active_status_var)
        active_status_label.pack(side=LEFT, anchor="w", padx=10)

        footnote_text = "Advanced Acceleration prioritizes dedicated GPUs (Nvidia/AMD). This can improve speed but may cause errors before encoding begins if issues are found."
        footnote_label = ttk.Label(main_frame, text=footnote_text, wraplength=500, justify="left")
        footnote_label.pack(anchor="w", padx=5, pady=5)

        button_frame = ttk.Frame(main_frame)
        button_frame.pack(side=BOTTOM, fill='x', pady=10)
        save_button = ttk.Button(button_frame, text="Save", command=lambda: self.save_config_and_close(config_window),
                                 bootstyle="success")
        save_button.pack(side=RIGHT, padx=5)
        reset_button = ttk.Button(button_frame, text="Reset", command=self.reset_config_window,
                                  bootstyle="danger-outline")
        reset_button.pack(side=RIGHT, padx=5)

        self.update_gpu_radio_buttons()
        self.app.center_toplevel(config_window)

    def save_config_and_close(self, window):
        """Save configuration and close the provided window."""
        self.app.save_app_config()
        self.update_advanced_hw_status()
        window.destroy()

    def reset_config_window(self):
        """Reset settings in the configuration window to their defaults."""
        self.gpu_selection_var.set("Detect Automatically")
        self.nvidia_detected_var.set("Not Detected")
        self.amd_detected_var.set("Not Detected")
        self.intel_detected_var.set("Not Detected")
        self.codec_test_status_var.set("Status: Not Tested")
        self.codec_test_run_var.set(False)
        self.update_advanced_hw_status()
        self.update_gpu_radio_buttons()

    def update_gpu_radio_buttons(self):
        """Enable or disable GPU selection radio buttons based on detection status."""
        if self.nvidia_radio:
            self.nvidia_radio.config(state="normal" if self.nvidia_detected_var.get() == "Detected" else "disabled")
        if self.amd_radio:
            self.amd_radio.config(state="normal" if self.amd_detected_var.get() == "Detected" else "disabled")
        if self.intel_radio:
            self.intel_radio.config(state="normal" if self.intel_detected_var.get() == "Detected" else "disabled")

    def on_hw_accel_toggle(self):
        """Handle toggling of the main hardware acceleration checkbox."""
        if not self.hw_accel_var.get():
            self.advanced_hw_accel_var.set(False)
            self.advanced_hw_check.config(state="disabled")
            self.config_button.config(state="disabled")
        else:
            self.advanced_hw_check.config(state="normal")
            self.config_button.config(state="normal")

        self.on_advanced_hw_toggle()
        self.app.save_app_config()
        self.app.update_video_codec_options()

    def on_advanced_hw_toggle(self):
        """Handle toggling of the advanced hardware acceleration checkbox."""
        if not self.advanced_hw_accel_var.get():
            self.codec_test_run_var.set(False)
        self.update_advanced_hw_status()
        self.app.save_app_config()
        self.app.update_video_codec_options()

    def update_advanced_hw_status(self):
        """Update the 'Active/Inactive' status label for advanced HW accel."""
        if self.advanced_hw_accel_var.get() and self.codec_test_run_var.get():
            self.advanced_hw_active_status_var.set("Active")
        else:
            self.advanced_hw_active_status_var.set("Inactive")

    def run_codec_test(self):
        """Initiate the hardware codec detection test."""
        ffmpeg_exe = self.ffmpeg_path_var.get()
        if not ffmpeg_exe or not os.path.exists(ffmpeg_exe):
            messagebox.showerror("Error", "FFmpeg path is not set or the file does not exist.")
            return

        self.codec_test_status_var.set("Status: Testing...")
        self.nvidia_detected_var.set("Testing...")
        self.amd_detected_var.set("Testing...")
        self.intel_detected_var.set("Testing...")
        logic.run_encoder_detection(ffmpeg_exe, self.gui_queue, is_manual_test=True)

    def detect_hw_encoders(self):
        """Initiate hardware encoder detection in a background thread."""
        ffmpeg_exe = self.ffmpeg_path_var.get()
        if not ffmpeg_exe or not os.path.exists(ffmpeg_exe):
            self.hw_encoders = []
            self.gui_queue.put(('update_codecs', []))
            return
        logic.run_encoder_detection(ffmpeg_exe, self.gui_queue, is_manual_test=False)

    def handle_update_codecs(self, codecs):
        """Callback for when the codec list is updated from the logic thread."""
        self.hw_encoders = codecs
        self.app.update_video_codec_options()

    def handle_codec_test_finished(self, payload):
        """Callback for when the manual codec test finishes."""
        self.codec_test_status_var.set(payload[0])
        self.nvidia_detected_var.set(payload[1])
        self.amd_detected_var.set(payload[2])
        self.intel_detected_var.set(payload[3])
        self.codec_test_run_var.set(payload[4])
        self.hw_encoders = payload[5]
        self.update_advanced_hw_status()
        self.update_gpu_radio_buttons()
        self.app.update_video_codec_options()

    def get_settings(self):
        """Returns a dictionary of hardware-related settings for saving."""
        return {
            'hw_accel_enabled': str(self.hw_accel_var.get()),
            'advanced_hw_accel': str(self.advanced_hw_accel_var.get()),
            'codec_test_run': str(self.codec_test_run_var.get()),
            'gpu_selection': self.gpu_selection_var.get(),
        }

    def restore_defaults(self):
        """Resets all hardware settings to their default values."""
        self.hw_accel_var.set(True)
        self.advanced_hw_accel_var.set(False)
        self.codec_test_run_var.set(False)
        self.reset_config_window()
        self.app.update_video_codec_options()


class ThemeManager:
    """Manages the application's visual theme."""

    def __init__(self, app, style, config):
        self.app = app
        self.style = style
        self.config = config
        self.theme_var = tk.StringVar(
            value=self.config.get('Settings', 'theme', fallback='superhero')
        )

    def change_theme(self):
        """Applies the selected theme and triggers updates in the main app."""
        theme_name = self.theme_var.get()
        self.style.theme_use(theme_name)
        self.app.update_listbox_style()
        self.app.save_app_config()

    def create_theme_selection_frame(self, parent):
        """Creates and returns a frame with theme selection radio buttons."""
        theme_frame = ttk.Labelframe(parent, text="Appearance", padding=5)
        themes = {"Default (Dark)": "superhero", "Light": "litera", "Black": "darkly"}
        for text, theme in themes.items():
            rb = ttk.Radiobutton(
                theme_frame,
                text=text,
                variable=self.theme_var,
                value=theme,
                command=self.change_theme
            )
            rb.pack(anchor="w", padx=10, pady=2)
        return theme_frame

    def get_theme(self):
        """Returns the currently selected theme name."""
        return self.theme_var.get()

    def restore_default(self):
        """Restores the theme to its default setting."""
        self.theme_var.set("superhero")
        self.change_theme()


class FFmpegHelpWindow(ttk.Toplevel):
    """A Toplevel window that provides instructions on downloading and configuring FFmpeg."""

    def __init__(self, master):
        super().__init__(master)
        self.title("FFmpeg Configuration Help")
        self.geometry("650x580")
        self.transient(master)
        self.grab_set()

        self._create_widgets()
        master.center_toplevel(self)

    def _create_widgets(self):
        """Create and layout all widgets in the window."""
        main_frame = ttk.Frame(self, padding=15)
        main_frame.pack(fill="both", expand=True)
        main_frame.columnconfigure(0, weight=1)

        ttk.Label(main_frame, text="How to Download and Configure FFmpeg", font="-weight bold").pack(anchor="w",
                                                                                                     pady=(0, 10))
        instructions = (
            "This application requires the FFmpeg library to function. You need to download it and tell the program where to find the executable files.\n\n"
            "1. Download FFmpeg:\n"
            "   You can download a 'full build' from one of the websites below. Alternatively, you can use any other source you find suitable."
        )
        ttk.Label(main_frame, text=instructions, wraplength=600, justify="left").pack(anchor="w")

        self._create_link(main_frame, "Direct Download (Latest as of Aug 2025)",
                          "https://github.com/GyanD/codexffmpeg/releases/download/2025-08-25-git-1b62f9d3ae/ffmpeg-2025-08-25-git-1b62f9d3ae-full_build.zip",
                          comment="(Program tested with this version)")
        self._create_link(main_frame, "Gyan.dev FFmpeg Builds (Main Site)", "https://www.gyan.dev/ffmpeg/builds/")
        self._create_link(main_frame, "GitHub Releases Mirror", "https://github.com/GyanD/codexffmpeg/releases/")
        self._create_link(main_frame, "Official FFmpeg Website", "https://ffmpeg.org/")

        instructions2 = (
            "\n2. Unzip the File:\n"
            "   Extract the downloaded .zip file to a permanent location on your computer, for example, 'C:\\FFmpeg'.\n\n"
            "3. Configure the Paths in the Application:\n"
            "   - Click the 'FFmpeg Library' button in the main window.\n"
            "   - For each entry (FFmpeg, FFprobe, FFplay), click 'Browse...' and navigate to the 'bin' folder inside the location where you unzipped FFmpeg.\n"
            "   - Select the corresponding .exe file (e.g., 'ffmpeg.exe', 'ffprobe.exe').\n"
            "   - Click 'Test Libraries' to confirm everything is working."
        )
        ttk.Label(main_frame, text=instructions2, wraplength=600, justify="left").pack(anchor="w", pady=(10, 0))

        note_frame = ttk.Frame(main_frame)
        note_frame.pack(anchor="w", pady=(15, 0), fill='x')
        note_prefix = ttk.Label(note_frame, text="Note:", bootstyle="info")
        note_prefix.pack(side=LEFT)
        note_text = "Different FFmpeg builds may include different codecs. This can affect which conversion formats are available."
        note_content = ttk.Label(note_frame, text=note_text, wraplength=580, justify="left")
        note_content.pack(side=LEFT, padx=5)

        disclaimer_text = (
            "Disclaimer: The links provided direct to external, third-party websites, and their use is at your own risk. "
            "FFmpeg is a separate project with its own licensing. By downloading and using FFmpeg with this application, "
            "you agree to comply with the licenses of both this application and FFmpeg."
        )
        ttk.Label(main_frame, text=disclaimer_text, wraplength=600, justify="left", bootstyle="warning").pack(
            anchor="w", pady=(15, 0))

        ok_button = ttk.Button(main_frame, text="OK", command=self.destroy, bootstyle="primary")
        ok_button.pack(side=BOTTOM, pady=(10, 0))

    def _create_link(self, parent, text, url, comment=None):
        """Helper function to create a clickable hyperlink label."""
        container = ttk.Frame(parent)
        container.pack(anchor="w", fill='x', padx=20)
        link = ttk.Label(container, text=text, foreground="blue", cursor="hand2")
        link.pack(side=LEFT, anchor="w")
        link.bind("<Button-1>", lambda e: webbrowser.open_new(url))
        if comment:
            comment_label = ttk.Label(container, text=comment, bootstyle="secondary")
            comment_label.pack(side=LEFT, anchor="w", padx=5)


class HelpWindow(ttk.Toplevel):
    """A Toplevel window that displays the application's help and information."""

    def __init__(self, master, app_style):
        super().__init__(master)
        self.title("Help & Information")
        self.geometry("650x600")
        self.transient(master)
        self.grab_set()
        self.app_style = app_style

        self._create_widgets()
        master.center_toplevel(self)

    def _create_widgets(self):
        """Create and layout all widgets in the window."""
        main_frame = ttk.Frame(self)
        main_frame.pack(fill="both", expand=True)
        main_frame.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)

        text_area = ScrolledText(main_frame, padding=15, autohide=True)
        text_area.grid(row=0, column=0, sticky='nsew', padx=5, pady=5)

        bg_color = self.app_style.colors.get('bg')
        fg_color = self.app_style.colors.get('fg')
        primary_color = self.app_style.colors.get('primary')

        if hasattr(text_area, 'text'):
            text_area.text.configure(bg=bg_color, fg=fg_color, insertbackground=fg_color, wrap='word')

        text_area.tag_configure("heading", font="-weight bold -size 12", foreground=primary_color, spacing3=10)
        text_area.tag_configure("subheading", font="-weight bold", spacing1=5, spacing3=5)
        text_area.tag_configure("bold", font="-weight bold")
        text_area.tag_configure("indent", lmargin1=10, lmargin2=25)

        text_area.insert(tk.END, "Media Converter and Joiner Help\n", "heading")
        text_area.insert(tk.END, "This guide explains the main features of the application.\n\n")

        text_area.insert(tk.END, "1. Adding & Managing Files\n", "subheading")
        text_area.insert(tk.END,
                         "- Add Files: Drag files from your computer and drop them into the list area, or use the 'Add Files' button.\n"
                         "- Reorder Files: To change the order for joining, click and drag a file in the list to a new position.\n"
                         "- Remove/Clear: Use the 'Remove Selected' or 'Clear All' buttons to manage your list.\n"
                         "- Information: Select a file and click 'Information' to see technical details (requires FFprobe).\n"
                         "- Play: Select a file and click 'Play' to preview it (requires FFplay).\n\n",
                         "indent")

        text_area.insert(tk.END, "2. Choosing a Conversion Mode\n", "subheading")
        text_area.insert(tk.END,
                         "- Audio Mode: Use this to convert video or audio files into an audio-only format (e.g., MP4 to MP3).\n"
                         "- Video Mode: Use this to convert video files, allowing you to change the format, codec, resolution, and FPS.\n\n",
                         "indent")

        text_area.insert(tk.END, "3. Main Conversion Options\n", "subheading")
        text_area.insert(tk.END,
                         "- Join Files: Check this box to combine all files in the list into a single output file. The files will be joined in the order they appear in the list.\n"
                         "- Format: Select the output container format (e.g., MP3, MP4).\n"
                         "- Keep Metadata: If checked, the application will try to preserve tags like title, artist, and album.\n"
                         "- Quality Settings: Adjust bitrate (for audio) or codec/resolution (for video) to balance file size and quality.\n\n",
                         "indent")

        text_area.insert(tk.END, "4. Destination & Starting the Process\n", "subheading")
        text_area.insert(tk.END,
                         "- Output Folder: Choose where your converted files will be saved. Use 'Browse...' to select a folder and 'Open' to view it in your file explorer.\n"
                         "- Start Processing: Click this button to begin the conversion. A progress bar will show the status, and a cancel window will appear.\n\n",
                         "indent")

        text_area.insert(tk.END, "5. Advanced Features ('More Options...')\n", "subheading")
        text_area.insert(tk.END,
                         "- Appearance: Change the application's visual theme.\n"
                         "- Audio Normalization: When enabled, this adjusts the volume of all output audio to a standard level, making it great for creating consistent playlists.\n"
                         "- Hardware Acceleration: Can significantly speed up video encoding by using your GPU. Configuration may be needed for optimal performance.\n\n",
                         "indent")

        text_area.insert(tk.END, "6. FFmpeg Configuration\n", "subheading")
        text_area.insert(tk.END,
                         "This program requires the external FFmpeg software. Use the 'FFmpeg Library' button to set the paths to the required files, and the 'Help FFmpeg Config' button for download links and instructions.",
                         "indent")

        if hasattr(text_area, 'text'):
            text_area.text.configure(state="disabled")

        ok_button = ttk.Button(main_frame, text="OK", command=self.destroy, bootstyle="primary")
        ok_button.grid(row=1, column=0, pady=10)


class AudioConverterApp(ttk.Frame):
    """
    The main GUI class for the application. It handles the user interface
    and delegates processing tasks to the logic module.
    """

    def __init__(self, master, config, style, ffmpeg_path, ffprobe_path, ffplay_path):
        super().__init__(master, padding=(5, 5))
        self.master = master
        self.config = config
        self.style = style
        self.last_process_time = None

        self.ffmpeg_path = tk.StringVar(value=ffmpeg_path)
        self.ffprobe_path = tk.StringVar(value=ffprobe_path)
        self.ffplay_path = tk.StringVar(value=ffplay_path)
        self.ffmpeg_status_var = tk.StringVar(value="Unchecked")
        self.ffprobe_status_var = tk.StringVar(value="Unchecked")
        self.ffplay_status_var = tk.StringVar(value="Unchecked")
        self.cancel_event = threading.Event()
        self.cancel_window = None
        self.gui_queue = queue.Queue()

        self.theme_manager = ThemeManager(self, self.style, self.config)
        self.file_manager = FileManager(self, self.config)
        self.hardware_manager = HardwareManager(self, self.config, self.ffmpeg_path, self.gui_queue)

        self.audio_normalize_var = tk.BooleanVar(
            value=self.config.getboolean('Settings', 'audio_normalize', fallback=False))

        self.pack(fill=BOTH, expand=YES)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        self.create_widgets()

        self.toggle_mode()
        self.on_format_change()
        self.update_listbox_style()
        self.master.after(100, self.process_gui_queue)
        self.validate_ffmpeg_paths_on_startup()
        self.update_ffmpeg_help_button_style()

    def update_status(self, message):
        """Updates the text in the status bar."""
        self.status_var.set(message)

    def create_widgets(self):
        """Create and grid all the widgets for the application."""
        # --- File Listbox and Drag & Drop Frame ---
        file_frame = self.file_manager.create_file_display_frame(self)
        file_frame.grid(row=0, column=0, columnspan=2, sticky="nsew", pady=(0, 5))

        button_frame = ttk.Frame(self)
        button_frame.grid(row=1, column=0, columnspan=2, pady=2)

        self.add_button = ttk.Button(button_frame, text="Add Files", command=self.file_manager.add_files,
                                     bootstyle="primary")
        self.add_button.pack(side=LEFT, padx=2)
        self.remove_button = ttk.Button(button_frame, text="Remove Selected", command=self.file_manager.remove_selected,
                                        bootstyle="danger-outline")
        self.remove_button.pack(side=LEFT, padx=2)
        self.clear_button = ttk.Button(button_frame, text="Clear All", command=self.file_manager.clear_all,
                                       bootstyle="danger-outline")
        self.clear_button.pack(side=LEFT, padx=2)

        self.info_button = ttk.Button(button_frame, text="Information", command=self.show_file_info,
                                      bootstyle="info-outline", state="disabled")
        self.info_button.pack(side=LEFT, padx=2)

        self.play_button = ttk.Button(button_frame, text="Play", command=self.play_selected_file,
                                      bootstyle="success-outline", state="disabled")
        self.play_button.pack(side=LEFT, padx=2)

        main_options_frame = ttk.Labelframe(self, text="Conversion Options", padding=5)
        main_options_frame.grid(row=2, column=0, sticky="nsew", pady=5)
        main_options_frame.columnconfigure(0, weight=1)

        self.mode_var = tk.StringVar(value=self.config.get('Settings', 'mode', fallback='Audio'))
        mode_frame = ttk.Frame(main_options_frame)
        mode_frame.grid(row=0, column=0, sticky="ew", pady=2, padx=5)
        audio_radio = ttk.Radiobutton(mode_frame, text="Audio", variable=self.mode_var, value="Audio",
                                      command=self.toggle_mode)
        audio_radio.pack(side=LEFT, padx=5)
        video_radio = ttk.Radiobutton(mode_frame, text="Video", variable=self.mode_var, value="Video",
                                      command=self.toggle_mode)
        video_radio.pack(side=LEFT, padx=5)

        separator = ttk.Separator(main_options_frame, orient=HORIZONTAL)
        separator.grid(row=1, column=0, sticky="ew", pady=5, padx=5)

        self.audio_options_frame = ttk.Frame(main_options_frame)
        self.audio_options_frame.grid(row=2, column=0, sticky="nsew")
        self.audio_options_frame.columnconfigure(1, weight=1)
        self.create_audio_options(self.audio_options_frame)

        self.video_options_frame = ttk.Frame(main_options_frame)
        self.video_options_frame.grid(row=2, column=0, sticky="nsew")
        self.video_options_frame.columnconfigure(1, weight=1)
        self.create_video_options(self.video_options_frame)

        dest_frame = ttk.Labelframe(self, text="Output Folder", padding=5)
        dest_frame.grid(row=3, column=0, sticky="ew", pady=5)
        dest_frame.columnconfigure(0, weight=1)

        self.dest_path_var = tk.StringVar(
            value=self.config.get('Settings', 'dest_path', fallback=os.path.join(os.path.expanduser("~"), "Desktop")))
        self.dest_entry = ttk.Entry(dest_frame, textvariable=self.dest_path_var)
        self.dest_entry.grid(row=0, column=0, sticky="ew", padx=5, pady=2)

        dest_button_frame = ttk.Frame(dest_frame)
        dest_button_frame.grid(row=0, column=1, padx=(0, 5), pady=2)
        self.dest_browse_button = ttk.Button(dest_button_frame, text="Browse...", command=self.browse_dest_folder,
                                             bootstyle="secondary")
        self.dest_browse_button.pack(side=tk.LEFT, padx=(0, 2))
        self.open_folder_button = ttk.Button(dest_button_frame, text="Open", command=self.open_dest_folder,
                                             bootstyle="secondary")
        self.open_folder_button.pack(side=tk.LEFT)

        bottom_button_frame = ttk.Frame(self)
        bottom_button_frame.grid(row=4, column=0, sticky="w", padx=5, pady=(0, 5))

        self.more_options_button = ttk.Button(bottom_button_frame, text="More Options...",
                                              command=self.open_more_options, bootstyle="primary-outline")
        self.more_options_button.pack(side=tk.LEFT, padx=(0, 2))

        self.ffmpeg_library_button = ttk.Button(bottom_button_frame, text="FFmpeg Library",
                                                command=self.open_ffmpeg_library_window, bootstyle="primary-outline")
        self.ffmpeg_library_button.pack(side=tk.LEFT, padx=2)

        self.ffmpeg_help_button = ttk.Button(bottom_button_frame, text="Help FFmpeg Config",
                                             command=self.open_ffmpeg_help_window, bootstyle="info-outline")
        self.ffmpeg_help_button.pack(side=tk.LEFT, padx=2)

        self.help_button = ttk.Button(bottom_button_frame, text="Help & Info",
                                      command=self.open_help_window, bootstyle="info-outline")
        self.help_button.pack(side=tk.LEFT, padx=2)

        self.always_ask_var = tk.BooleanVar(
            value=self.config.getboolean('Settings', 'always_ask_destination', fallback=False))

        progress_frame = ttk.Frame(self)
        progress_frame.grid(row=5, column=0, columnspan=2, sticky="ew", pady=2)
        progress_frame.columnconfigure(0, weight=1)
        self.process_button = ttk.Button(progress_frame, text="Start Processing",
                                         command=self.start_processing_thread, bootstyle="success")
        self.process_button.pack(fill=X, ipady=5, pady=2)

        self.progressbar = ttk.Progressbar(progress_frame, bootstyle="success-striped")
        self.progressbar.pack(fill=X, pady=2)

        self.status_var = tk.StringVar(value="Ready.")
        self.status_bar = ttk.Label(self.master, textvariable=self.status_var, anchor="w")
        self.status_bar.pack(side=BOTTOM, fill=X, padx=10, pady=(0, 5))

    def create_audio_options(self, parent_frame):
        """Create the widgets for the audio options section."""
        left_audio_opts = ttk.Frame(parent_frame)
        left_audio_opts.grid(row=0, column=0, sticky="nw", padx=5, pady=2)
        right_audio_opts = ttk.Frame(parent_frame)
        right_audio_opts.grid(row=0, column=2, sticky="nw", padx=5, pady=2)

        separator_audio = ttk.Separator(parent_frame, orient=VERTICAL)
        separator_audio.grid(row=0, column=1, sticky='ns', padx=10, pady=2)

        self.join_files_var_audio = tk.BooleanVar(
            value=self.config.getboolean('Settings', 'join_files_audio', fallback=False))
        self.join_check_audio = ttk.Checkbutton(left_audio_opts, text="Join files into a single output",
                                                variable=self.join_files_var_audio, command=self.save_app_config,
                                                bootstyle="primary")
        self.join_check_audio.grid(row=0, column=0, columnspan=2, sticky="w", pady=2)
        ttk.Label(left_audio_opts, text="Format:").grid(row=1, column=0, sticky="w", pady=2)
        self.output_format_audio = tk.StringVar(
            value=self.config.get('Settings', 'output_format_audio', fallback='mp3'))
        self.format_menu_audio = ttk.Combobox(left_audio_opts, textvariable=self.output_format_audio,
                                              values=["mp3", "wav", "aac", "flac", "aiff", "ogg", "alac"],
                                              state="readonly")
        self.format_menu_audio.bind("<<ComboboxSelected>>", self.on_format_change)
        self.format_menu_audio.grid(row=1, column=1, sticky="w", pady=2)

        self.metadata_var = tk.BooleanVar(value=self.config.getboolean('Settings', 'keep_metadata', fallback=True))
        self.metadata_check = ttk.Checkbutton(left_audio_opts, text="Keep Metadata", variable=self.metadata_var,
                                              command=self.save_app_config, bootstyle="primary")
        self.metadata_check.grid(row=2, column=0, columnspan=2, sticky="w", pady=2)

        self.vbr_mode_var = tk.BooleanVar(value=self.config.getboolean('Settings', 'vbr_mode', fallback=False))
        self.vbr_check = ttk.Checkbutton(right_audio_opts, text="Use Variable Bitrate (VBR)",
                                         variable=self.vbr_mode_var, command=self.toggle_bitrate_mode,
                                         bootstyle="primary")
        self.vbr_check.grid(row=0, column=0, columnspan=2, sticky="w", pady=2)
        self.cbr_label = ttk.Label(right_audio_opts, text="Bitrate (CBR):")
        self.cbr_label.grid(row=1, column=0, sticky="w", pady=2)
        self.bitrate = tk.StringVar(value=self.config.get('Settings', 'bitrate', fallback='192k'))
        self.bitrate_menu = ttk.Combobox(right_audio_opts, textvariable=self.bitrate,
                                         values=["320k", "256k", "192k", "160k", "128k", "112k", "96k",
                                                 "64k", "32k", "16k"], state="readonly")
        self.bitrate_menu.bind("<<ComboboxSelected>>", lambda e: self.save_app_config())
        self.bitrate_menu.grid(row=1, column=1, sticky="w", pady=2)
        self.vbr_label = ttk.Label(right_audio_opts, text="Quality (VBR):", state="disabled")
        self.vbr_label.grid(row=2, column=0, sticky="w", pady=2)
        self.vbr_quality = tk.IntVar(value=self.config.getint('Settings', 'vbr_quality', fallback=4))
        self.vbr_menu = ttk.Combobox(right_audio_opts, textvariable=self.vbr_quality,
                                     values=[str(i) for i in range(0, 10)], state="disabled")
        self.vbr_menu.bind("<<ComboboxSelected>>", lambda e: self.save_app_config())
        self.vbr_menu.grid(row=2, column=1, sticky="w", pady=2)

    def create_video_options(self, parent_frame):
        """Create the widgets for the video options section."""
        left_video_opts = ttk.Frame(parent_frame)
        left_video_opts.grid(row=0, column=0, sticky="nw", padx=5, pady=2)
        right_video_opts = ttk.Frame(parent_frame)
        right_video_opts.grid(row=0, column=2, sticky="nw", padx=5, pady=2)

        separator_video = ttk.Separator(parent_frame, orient=VERTICAL)
        separator_video.grid(row=0, column=1, sticky='ns', padx=10, pady=2)

        self.join_files_var_video = tk.BooleanVar(
            value=self.config.getboolean('Settings', 'join_files_video', fallback=False))
        self.join_check_video = ttk.Checkbutton(left_video_opts, text="Join files into a single output",
                                                variable=self.join_files_var_video, command=self.save_app_config,
                                                bootstyle="primary")
        self.join_check_video.grid(row=0, column=0, columnspan=2, sticky="w", pady=2)

        ttk.Label(left_video_opts, text="Format:").grid(row=1, column=0, sticky="w", pady=2)
        self.output_format_video = tk.StringVar(
            value=self.config.get('Settings', 'output_format_video', fallback='mp4'))
        self.format_menu_video = ttk.Combobox(left_video_opts, textvariable=self.output_format_video,
                                              values=["mp4", "mkv", "avi", "mov", "webm"],
                                              state="readonly")
        self.format_menu_video.bind("<<ComboboxSelected>>", lambda e: self.save_app_config())
        self.format_menu_video.grid(row=1, column=1, sticky="w", pady=2)

        self.metadata_check_video = ttk.Checkbutton(left_video_opts, text="Keep Metadata", variable=self.metadata_var,
                                                    command=self.save_app_config, bootstyle="primary")
        self.metadata_check_video.grid(row=2, column=0, columnspan=2, sticky="w", pady=2)

        ttk.Label(right_video_opts, text="Video Codec:").grid(row=0, column=0, sticky="w", pady=2)
        self.video_codec = tk.StringVar(value=self.config.get('Settings', 'video_codec', fallback='libx265'))
        self.video_codec_menu = ttk.Combobox(right_video_opts, textvariable=self.video_codec,
                                             values=["libx265", "libx264", "mpeg4"],
                                             state="readonly")
        self.video_codec_menu.bind("<<ComboboxSelected>>", lambda e: self.save_app_config())
        self.video_codec_menu.grid(row=0, column=1, sticky="w", pady=2)

        ttk.Label(right_video_opts, text="Resolution:").grid(row=1, column=0, sticky="w", pady=2)
        self.video_resolution = tk.StringVar(
            value=self.config.get('Settings', 'video_resolution', fallback='Keep Original'))
        resolutions = ["Keep Original", "4320p (8K)", "2160p (4K)", "1440p (2K)", "1080p (Full HD)", "720p (HD)",
                       "480p", "360p", "240p"]
        self.video_resolution_menu = ttk.Combobox(right_video_opts, textvariable=self.video_resolution,
                                                  values=resolutions, state="readonly")
        self.video_resolution_menu.bind("<<ComboboxSelected>>", lambda e: self.save_app_config())
        self.video_resolution_menu.grid(row=1, column=1, sticky="w", pady=2)

        ttk.Label(right_video_opts, text="FPS:").grid(row=2, column=0, sticky="w", pady=2)
        self.video_fps = tk.StringVar(value=self.config.get('Settings', 'video_fps', fallback='Keep Original'))
        fps_options = ["Keep Original", "60", "30", "25", "24"]
        self.video_fps_menu = ttk.Combobox(right_video_opts, textvariable=self.video_fps,
                                           values=fps_options, state="readonly")
        self.video_fps_menu.bind("<<ComboboxSelected>>", lambda e: self.save_app_config())
        self.video_fps_menu.grid(row=2, column=1, sticky="w", pady=2)

    def browse_dest_folder(self):
        """Open a dialog to select the destination folder."""
        path = filedialog.askdirectory(title="Select Output Folder")
        if path:
            self.dest_path_var.set(path)
            self.save_app_config()

    def open_dest_folder(self):
        """Open the destination folder in the system's file explorer."""
        path = self.dest_path_var.get()
        if not path or not os.path.isdir(path):
            messagebox.showerror("Error", "The destination folder does not exist.")
            return
        try:
            if platform.system() == "Windows":
                os.startfile(path)
            elif platform.system() == "Darwin":  # macOS
                subprocess.Popen(["open", path])
            else:  # Linux
                subprocess.Popen(["xdg-open", path])
        except Exception as e:
            messagebox.showerror("Error", f"Could not open folder: {e}")

    # --- UI Interaction and Event Handlers ---

    def center_toplevel(self, toplevel):
        """Center a toplevel window relative to the main application window."""
        toplevel.update_idletasks()
        parent = self.master
        parent_x, parent_y = parent.winfo_x(), parent.winfo_y()
        parent_width, parent_height = parent.winfo_width(), parent.winfo_height()
        win_width, win_height = toplevel.winfo_width(), toplevel.winfo_height()
        x = parent_x + (parent_width - win_width) // 2
        y = parent_y + (parent_height - win_height) // 2
        toplevel.geometry(f'+{x}+{y}')

    def toggle_mode(self):
        """Switch between Audio and Video conversion modes."""
        if self.mode_var.get() == "Audio":
            self.video_options_frame.grid_remove()
            self.audio_options_frame.grid()
        else:
            self.audio_options_frame.grid_remove()
            self.video_options_frame.grid()
        self.save_app_config()

    def update_listbox_style(self):
        """Update listbox colors to match the current ttkbootstrap theme."""
        style = ttk.Style.get_instance()
        bg_color = style.colors.get('bg')
        text_color = style.colors.get('fg')
        select_bg_color = style.colors.get('primary')
        self.file_manager.file_listbox.configure(bg=bg_color, fg=text_color, selectbackground=select_bg_color,
                                                 selectforeground=text_color)

    def open_more_options(self):
        """Open the advanced options window."""
        opts_window = ttk.Toplevel(master=self, title="Advanced Options")
        opts_window.geometry("500x480")
        opts_window.transient(self)
        opts_window.grab_set()

        main_opts_frame = ttk.Frame(opts_window, padding=10)
        main_opts_frame.pack(fill="both", expand=True)
        main_opts_frame.columnconfigure(0, weight=1)

        # --- Theme Options ---
        theme_frame = self.theme_manager.create_theme_selection_frame(main_opts_frame)
        theme_frame.grid(row=0, column=0, sticky="ew", pady=5)

        # --- Destination Options ---
        dest_opts_frame = ttk.Labelframe(main_opts_frame, text="Destination Options", padding=5)
        dest_opts_frame.grid(row=1, column=0, sticky="ew", pady=5)
        always_ask_check = ttk.Checkbutton(dest_opts_frame, text="Ask for destination before each process",
                                           variable=self.always_ask_var, command=self.save_app_config,
                                           bootstyle="primary")
        always_ask_check.pack(anchor="w", padx=10, pady=5)

        # --- Audio Processing Options ---
        audio_proc_frame = ttk.Labelframe(main_opts_frame, text="Audio Processing", padding=5)
        audio_proc_frame.grid(row=2, column=0, sticky="ew", pady=5)
        normalize_check = ttk.Checkbutton(audio_proc_frame, text="Enable Audio Normalization (LUFS)",
                                          variable=self.audio_normalize_var, command=self.save_app_config,
                                          bootstyle="primary")
        normalize_check.pack(anchor="w", padx=10, pady=5)

        # --- Hardware Acceleration ---
        hw_accel_frame = self.hardware_manager.create_hw_accel_frame(main_opts_frame)
        hw_accel_frame.grid(row=3, column=0, sticky="ew", pady=5)

        bottom_frame = ttk.Frame(main_opts_frame)
        bottom_frame.grid(row=4, column=0, pady=10)
        restore_button = ttk.Button(bottom_frame, text="Restore All Defaults", command=self.restore_defaults,
                                    bootstyle="danger-outline")
        restore_button.pack(side=LEFT, padx=5)
        close_button = ttk.Button(bottom_frame, text="Close", command=opts_window.destroy, bootstyle="primary")
        close_button.pack(side=LEFT, padx=5)

        self.center_toplevel(opts_window)

    def open_ffmpeg_library_window(self):
        """Open the window for setting FFmpeg executable paths."""
        lib_window = ttk.Toplevel(master=self, title="FFmpeg Library Paths")
        lib_window.geometry("600x400")
        lib_window.transient(self)
        lib_window.grab_set()

        main_frame = ttk.Frame(lib_window, padding=10)
        main_frame.pack(fill="both", expand=True)

        def create_path_entry(parent, label_text, text_variable, status_variable):
            frame = ttk.Labelframe(parent, text=f"{label_text} Path", padding=5)
            frame.pack(fill="x", pady=2)
            frame.columnconfigure(0, weight=1)

            entry = ttk.Entry(frame, textvariable=text_variable)
            entry.grid(row=0, column=0, sticky="ew", padx=5, pady=5)
            entry.bind("<KeyRelease>", lambda e, var=status_variable: (
                var.set("Unchecked"), self.update_ffmpeg_help_button_style()
            ))

            browse_button = ttk.Button(frame, text="Browse...",
                                       command=lambda: self.browse_for_exe(text_variable, status_variable))
            browse_button.grid(row=0, column=1, padx=5, pady=5)

            status_label = ttk.Label(frame, textvariable=status_variable)
            status_label.grid(row=0, column=2, padx=5, pady=5)

        create_path_entry(main_frame, "FFmpeg (Mandatory)", self.ffmpeg_path, self.ffmpeg_status_var)
        create_path_entry(main_frame, "FFprobe (Optional)", self.ffprobe_path, self.ffprobe_status_var)
        create_path_entry(main_frame, "FFplay (Optional)", self.ffplay_path, self.ffplay_status_var)

        # --- Note on optional libraries ---
        note_frame = ttk.Frame(main_frame)
        note_frame.pack(anchor="w", padx=10, pady=(5, 0), fill='x')

        note_prefix = ttk.Label(note_frame, text="Note:", bootstyle="info")
        note_prefix.pack(side=LEFT, anchor='nw')

        note_text = (
            "The following functionalities will not work if the optional libraries are not provided:\n"
            "  - FFprobe: View media file details ('Information' button) and calculate ETA.\n"
            "  - FFplay: Play audio or video ('Play' button)."
        )
        note_content = ttk.Label(note_frame, text=note_text, justify="left")
        note_content.pack(side=LEFT, anchor='w', padx=5)

        # --- Button Frame ---
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(pady=10, fill='x', side=BOTTOM)

        test_button = ttk.Button(button_frame, text="Test Libraries", command=self.test_ffmpeg_library,
                                 bootstyle="info")
        test_button.pack(side=tk.LEFT, padx=5)

        reset_button = ttk.Button(button_frame, text="Reset Paths", command=self.reset_ffmpeg_paths,
                                  bootstyle="danger-outline")
        reset_button.pack(side=tk.LEFT, padx=(10, 5))

        close_button = ttk.Button(button_frame, text="Close", command=lib_window.destroy, bootstyle="primary")
        close_button.pack(side=tk.RIGHT, padx=5)

        self.center_toplevel(lib_window)

    def open_ffmpeg_help_window(self):
        """Opens a window with instructions on how to download and configure FFmpeg."""
        FFmpegHelpWindow(master=self)

    def open_help_window(self):
        """Open the help and information window."""
        HelpWindow(master=self, app_style=self.style)

    def restore_defaults(self):
        """Restore all application settings to their default values."""
        if not messagebox.askyesno("Confirm", "Are you sure you want to restore all settings to their defaults?"):
            return

        # Restore all variables to default
        self.file_manager.restore_defaults()
        self.mode_var.set("Audio")
        self.join_files_var_audio.set(False)
        self.output_format_audio.set("mp3")
        self.metadata_var.set(True)
        self.vbr_mode_var.set(False)
        self.bitrate.set("192k")
        self.vbr_quality.set(4)
        self.join_files_var_video.set(False)
        self.output_format_video.set("mp4")
        self.video_codec.set("libx265")
        self.video_resolution.set("Keep Original")
        self.video_fps.set("Keep Original")
        self.dest_path_var.set(os.path.join(os.path.expanduser("~"), "Desktop"))
        self.always_ask_var.set(False)
        self.audio_normalize_var.set(False)

        self.hardware_manager.restore_defaults()
        self.theme_manager.restore_default()
        self.toggle_mode()
        self.on_format_change()
        self.save_app_config()
        messagebox.showinfo("Success", "All settings have been restored to their defaults.")

    def test_ffmpeg_library(self):
        """Run a simplified test on the configured FFmpeg executables and show in new window."""
        test_window = ttk.Toplevel(master=self, title="FFmpeg Test Results")
        test_window.geometry("500x520")  # Increased height
        test_window.transient(self)
        test_window.grab_set()

        results_text = ScrolledText(test_window, padding=10, autohide=True)
        results_text.pack(fill="both", expand=True, padx=10, pady=10)
        results_text.insert(tk.END, "Testing libraries... Please wait.")

        ok_button = ttk.Button(test_window, text="OK", command=test_window.destroy, bootstyle="primary")
        ok_button.pack(pady=10)

        self.center_toplevel(test_window)

        paths = {
            'ffmpeg': self.ffmpeg_path.get(),
            'ffprobe': self.ffprobe_path.get(),
            'ffplay': self.ffplay_path.get()
        }

        supported_audio = [ext.strip('.') for ext in self.file_manager.supported_audio]
        supported_video = [ext.strip('.') for ext in self.file_manager.supported_video]

        logic.run_simplified_ffmpeg_test(paths, supported_audio, supported_video, self.gui_queue, results_text)

    def browse_for_exe(self, string_var, status_var):
        """Open a file dialog to select an executable file and update status."""
        # Define filetypes based on the operating system for better compatibility.
        if platform.system() == "Windows":
            filetypes = (("Executable", "*.exe"), ("All Files", "*.*"))
        else:
            # On macOS and Linux, executables often don't have extensions.
            filetypes = (("All Files", "*.*"),)

        # Use askopenfilename (singular) to ensure a single string path is returned.
        path = filedialog.askopenfilename(title="Select Executable", filetypes=filetypes)

        if path:
            string_var.set(path)
            status_var.set("Unchecked")  # Reset status on change
            self.save_app_config()
            # If the main ffmpeg path is changed, re-detect hardware encoders.
            if string_var == self.ffmpeg_path:
                self.hardware_manager.detect_hw_encoders()
            # Update button states based on the new paths.
            self.update_info_button_state()
            self.update_play_button_state()
            self.update_ffmpeg_help_button_style()

    def save_app_config(self):
        """Collect all settings from the UI and save them to the config file."""
        settings = {
            'ffmpeg_path': self.ffmpeg_path.get(),
            'ffprobe_path': self.ffprobe_path.get(),
            'ffplay_path': self.ffplay_path.get(),
            'dest_path': self.dest_path_var.get(),
            'always_ask_destination': str(self.always_ask_var.get()),
            'keep_metadata': str(self.metadata_var.get()),
            'join_files_audio': str(self.join_files_var_audio.get()),
            'join_files_video': str(self.join_files_var_video.get()),
            'output_format_audio': self.output_format_audio.get(),
            'output_format_video': self.output_format_video.get(),
            'video_codec': self.video_codec.get(),
            'video_resolution': self.video_resolution.get(),
            'video_fps': self.video_fps.get(),
            'vbr_mode': str(self.vbr_mode_var.get()),
            'bitrate': self.bitrate.get(),
            'vbr_quality': str(self.vbr_quality.get()),
            'mode': self.mode_var.get(),
            'audio_normalize': str(self.audio_normalize_var.get()),
            'theme': self.theme_manager.get_theme()
        }
        hw_settings = self.hardware_manager.get_settings()
        settings.update(hw_settings)
        fm_settings = self.file_manager.get_settings()
        settings.update(fm_settings)
        utils.save_config(settings)

    def create_info_dialog(self, title, message, width=550, height=500):
        """Creates a themed, scrollable dialog with an OK button."""
        dialog = ttk.Toplevel(self.master)
        dialog.title(title)
        dialog.geometry(f"{width}x{height}")
        dialog.transient(self.master)
        dialog.grab_set()

        text_area = ScrolledText(dialog, padding=10, autohide=True)
        text_area.pack(expand=True, fill=BOTH, padx=10, pady=10)

        style = ttk.Style.get_instance()
        bg_color = style.colors.get('bg')
        fg_color = style.colors.get('fg')
        if hasattr(text_area, 'text'):
            text_area.text.configure(bg=bg_color, fg=fg_color, insertbackground=fg_color)

        text_area.insert(tk.END, message)

        if hasattr(text_area, 'text'):
            text_area.text.configure(state="disabled")

        ok_button = ttk.Button(dialog, text="OK", command=dialog.destroy, bootstyle="primary")
        ok_button.pack(pady=10)

        self.center_toplevel(dialog)

    def create_completion_dialog(self, title, message):
        """Creates a styled dialog for the 'Processing Complete' message."""
        dialog = ttk.Toplevel(self.master)
        dialog.title(title)
        dialog.geometry("500x250")
        dialog.transient(self.master)
        dialog.grab_set()

        main_frame = ttk.Frame(dialog, padding=15)
        main_frame.pack(expand=True, fill=BOTH)
        main_frame.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)

        border_frame = ttk.Frame(main_frame, bootstyle="secondary", padding=2)
        border_frame.grid(row=0, column=0, sticky="nsew")
        border_frame.rowconfigure(0, weight=1)
        border_frame.columnconfigure(0, weight=1)

        content_frame = ttk.Frame(border_frame, padding=20)
        content_frame.grid(row=0, column=0, sticky="nsew")
        content_frame.rowconfigure(0, weight=1)
        content_frame.columnconfigure(0, weight=1)

        message_label = ttk.Label(content_frame, text=message, justify="center", anchor="center")
        message_label.grid(row=0, column=0, sticky="nsew", pady=(0, 10))

        ok_button = ttk.Button(content_frame, text="OK", command=dialog.destroy, bootstyle="primary")
        ok_button.grid(row=1, column=0, pady=(10, 0))

        self.center_toplevel(dialog)

    def process_gui_queue(self):
        """Process messages from the background threads to update the GUI safely."""
        try:
            message = self.gui_queue.get(block=False)
            msg_type, *payload = message
            if msg_type == 'status':
                self.update_status(payload[0])
            elif msg_type == 'progress':
                self.progressbar['value'] = payload[0]
            elif msg_type == 'progress_mode':
                if payload[0] == 'indeterminate':
                    self.progressbar.start()
                else:
                    self.progressbar.stop()
                    self.progressbar['value'] = 0
            elif msg_type == 'total_time':
                self.last_process_time = payload[0]
            elif msg_type == 'showinfo':
                title, msg_text = payload
                if title == "Processing Complete":
                    if self.last_process_time is not None:
                        msg_text += f"\n\nTotal time: {self.last_process_time:.2f} seconds"
                        self.last_process_time = None
                    self.create_completion_dialog(title, msg_text)
                else:
                    self.create_info_dialog(title, msg_text)
            elif msg_type == 'showerror':
                messagebox.showerror(payload[0], payload[1])
            elif msg_type == 'processing_done':
                self.process_button.configure(state="normal")
                self.progressbar['value'] = 0
                self.update_status("Ready.")
                if self.cancel_window:
                    self.cancel_window.destroy()
                    self.cancel_window = None
            elif msg_type == 'simplified_test_result':
                results, widget = payload
                self.ffmpeg_status_var.set(results['ffmpeg']['status'])
                self.ffprobe_status_var.set(results['ffprobe']['status'])
                self.ffplay_status_var.set(results['ffplay']['status'])
                widget.delete("1.0", tk.END)
                widget.insert(tk.END, results['report'])
                self.update_info_button_state()
                self.update_play_button_state()
                self.update_ffmpeg_help_button_style()
            elif msg_type == 'update_codecs':
                self.hardware_manager.handle_update_codecs(payload[0])
            elif msg_type == 'codec_test_finished':
                self.hardware_manager.handle_codec_test_finished(payload)

        except queue.Empty:
            pass
        finally:
            self.master.after(100, self.process_gui_queue)

    def on_format_change(self, event=None):
        """Handle changes in the selected audio output format."""
        self.save_app_config()
        selected_format = self.output_format_audio.get()
        if selected_format in ['aac', 'alac', 'wav', 'aiff', 'flac']:
            self.vbr_mode_var.set(False)
            self.vbr_check.configure(state="disabled")
        else:
            self.vbr_check.configure(state="normal")
        self.toggle_bitrate_mode()

    def toggle_bitrate_mode(self):
        """Switch between Constant Bitrate (CBR) and Variable Bitrate (VBR) modes."""
        self.save_app_config()
        if self.vbr_mode_var.get():
            self.cbr_label.configure(state="disabled")
            self.bitrate_menu.configure(state="disabled")
            self.vbr_label.configure(state="normal")
            self.vbr_menu.configure(state="readonly")
        else:
            self.cbr_label.configure(state="normal")
            self.bitrate_menu.configure(state="readonly")
            self.vbr_label.configure(state="disabled")
            self.vbr_menu.configure(state="disabled")

    def start_processing_thread(self):
        """Start the file processing in a new thread to keep the GUI responsive."""
        if not self.ffmpeg_path.get() or not os.path.exists(self.ffmpeg_path.get()):
            messagebox.showerror("FFmpeg Not Found",
                                 "The FFmpeg library was not found.\n\nPlease set the correct path in the 'FFmpeg Library' window.\n\n"
                                 "For more information, follow the steps in 'Help FFmpeg Config'.")
            return

        file_paths = self.file_manager.get_all_file_paths()
        if not file_paths:
            messagebox.showerror("Error", "No files selected.")
            return

        self.cancel_event.clear()
        self.show_cancel_popup()
        self.process_button.configure(state="disabled")
        self.progressbar['value'] = 0

        settings = self.get_current_settings()

        threading.Thread(target=logic.process_files,
                         args=(file_paths, settings, self.gui_queue, self.cancel_event),
                         daemon=True).start()

    def show_cancel_popup(self):
        """Display a small window with a cancel button during processing."""
        self.cancel_window = ttk.Toplevel(master=self.master, title="Processing...")
        self.cancel_window.geometry("300x100")
        self.cancel_window.transient(self.master)
        label = ttk.Label(self.cancel_window, text="Processing files, please wait...")
        label.pack(pady=20)
        cancel_button = ttk.Button(self.cancel_window, text="Cancel", command=self.cancel_processing,
                                   bootstyle="danger")
        cancel_button.pack(pady=5)
        self.cancel_window.protocol("WM_DELETE_WINDOW", lambda: None)  # Prevent closing
        self.center_toplevel(self.cancel_window)

    def cancel_processing(self):
        """Signal the background thread to cancel the current operation."""
        if messagebox.askyesno("Cancel", "Are you sure you want to cancel the current process?"):
            self.cancel_event.set()
            self.gui_queue.put(('status', "Cancelling..."))

    def get_current_settings(self):
        """Package all current UI settings into a dictionary."""
        return {
            'mode': self.mode_var.get(),
            'join_files_audio': self.join_files_var_audio.get(),
            'join_files_video': self.join_files_var_video.get(),
            'output_format_audio': self.output_format_audio.get(),
            'output_format_video': self.output_format_video.get(),
            'always_ask_destination': self.always_ask_var.get(),
            'dest_path': self.dest_path_var.get(),
            'ffmpeg_path': self.ffmpeg_path.get(),
            'ffprobe_path': self.ffprobe_path.get(),
            'metadata': self.metadata_var.get(),
            'vbr_mode': self.vbr_mode_var.get(),
            'vbr_quality': self.vbr_quality.get(),
            'bitrate': self.bitrate.get(),
            'video_codec': self.video_codec.get(),
            'video_resolution': self.video_resolution.get(),
            'video_fps': self.video_fps.get(),
            'audio_normalize': self.audio_normalize_var.get(),
        }

    def update_video_codec_options(self):
        """Update the video codec dropdown with available software and hardware codecs."""
        base_codecs = ["libx265", "libx264", "mpeg4"]
        codecs_to_remove = {'h264_nvenc', 'hevc_amf', 'hevc_nvenc'}

        available_codecs = base_codecs.copy()

        if self.hardware_manager.hw_accel_var.get() and self.hardware_manager.hw_encoders:
            filtered_hw_encoders = sorted([
                c for c in self.hardware_manager.hw_encoders if c not in codecs_to_remove
            ])
            available_codecs.extend(filtered_hw_encoders)

        current_codec = self.video_codec.get()
        self.video_codec_menu['values'] = available_codecs

        if current_codec not in available_codecs:
            self.video_codec.set(base_codecs[0])
        else:
            self.video_codec.set(current_codec)

    def reset_ffmpeg_paths(self):
        """Reset all FFmpeg paths to empty strings after confirmation."""
        if messagebox.askyesno("Confirm Reset",
                               "Are you sure you want to delete all FFmpeg library paths? This action is irreversible."):
            self.ffmpeg_path.set("")
            self.ffprobe_path.set("")
            self.ffplay_path.set("")
            self.ffmpeg_status_var.set("Unchecked")
            self.ffprobe_status_var.set("Unchecked")
            self.ffplay_status_var.set("Unchecked")
            self.save_app_config()
            self.update_info_button_state()
            self.update_play_button_state()
            self.update_ffmpeg_help_button_style()

    def validate_ffmpeg_paths_on_startup(self):
        """Check the validity of FFmpeg paths when the application starts."""
        if os.path.exists(self.ffmpeg_path.get()):
            self.ffmpeg_status_var.set("Checked")
        else:
            self.ffmpeg_status_var.set("Not Found")

        if os.path.exists(self.ffprobe_path.get()):
            self.ffprobe_status_var.set("Checked")
        if os.path.exists(self.ffplay_path.get()):
            self.ffplay_status_var.set("Checked")

        self.update_info_button_state()
        self.update_play_button_state()
        self.update_ffmpeg_help_button_style()

    def update_ffmpeg_help_button_style(self):
        """Changes the FFmpeg help button color to red if the path is not valid."""
        if self.ffmpeg_status_var.get() != "Checked":
            self.ffmpeg_help_button.config(bootstyle="danger")
        else:
            self.ffmpeg_help_button.config(bootstyle="info-outline")

    def update_info_button_state(self):
        """Enable or disable the 'Information' button based on ffprobe status."""
        if self.ffprobe_status_var.get() == "Checked":
            self.info_button.config(state="normal")
        else:
            self.info_button.config(state="disabled")

    def update_play_button_state(self):
        """Enable or disable the 'Play' button based on ffplay status."""
        if self.ffplay_status_var.get() == "Checked":
            self.play_button.config(state="normal")
        else:
            self.play_button.config(state="disabled")

    def show_file_info(self):
        """Gets and displays detailed information for the selected file."""
        file_path = self.file_manager.get_selected_file_path()
        if not file_path:
            messagebox.showwarning("No File Selected", "Please select a file from the list to see its information.")
            return

        ffprobe_path = self.ffprobe_path.get()

        threading.Thread(target=logic.get_file_information,
                         args=(file_path, ffprobe_path, self.gui_queue),
                         daemon=True).start()

    def play_selected_file(self):
        """Plays the selected media file using ffplay."""
        file_path = self.file_manager.get_selected_file_path()
        if not file_path:
            messagebox.showwarning("No File Selected", "Please select a file from the list to play.")
            return

        ffplay_path = self.ffplay_path.get()
        ffprobe_path = self.ffprobe_path.get()

        logic.play_file(file_path, ffplay_path, ffprobe_path, self.gui_queue)