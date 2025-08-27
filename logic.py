import ffmpeg
import os
import shutil
import platform
import threading
import subprocess
import time
import re
import tempfile
import json
from tkinter import filedialog


# --- Main Processing Orchestrator ---

def process_files(file_paths, settings, gui_queue, cancel_event):
    """
    Main function to orchestrate file processing based on the selected mode.
    This function is run in a separate thread.
    """
    start_time = time.time()
    try:
        mode = settings['mode']
        join_audio = settings['join_files_audio']
        join_video = settings['join_files_video']

        if mode == "Audio" and join_audio:
            process_joined_audio(file_paths, settings, gui_queue, cancel_event)
        elif mode == "Video" and join_video:
            process_joined_video(file_paths, settings, gui_queue, cancel_event)
        else:
            process_individual(file_paths, settings, gui_queue, cancel_event)
    finally:
        duration = time.time() - start_time
        gui_queue.put(('total_time', duration))
        gui_queue.put(('processing_done',))


# --- FFmpeg Command Execution and Helpers ---

def get_output_path(settings, for_join=False):
    """
    Determines the output path, asking the user if necessary.
    Returns a directory path for individual files, or a file path for joined files.
    """
    mode = settings['mode']
    output_format = settings['output_format_audio'] if mode == "Audio" else settings['output_format_video']

    if for_join:
        return filedialog.asksaveasfilename(
            title="Save Joined File As",
            defaultextension=f".{output_format}",
            filetypes=((f"{output_format.upper()} files", f"*.{output_format}"), ("All files", "*.*"))
        )
    elif settings['always_ask_destination'] or not settings['dest_path']:
        return filedialog.askdirectory(title="Select Output Folder")
    else:
        return settings['dest_path']


def run_ffmpeg_cancellable(args, gui_queue, cancel_event, total_duration=None):
    """
    Runs an FFmpeg command as a subprocess, monitors for cancellation,
    and reports progress and estimated time remaining.
    """
    creation_flags = subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0

    process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               universal_newlines=True, text=True, creationflags=creation_flags)

    start_time = time.time()

    def read_pipe(pipe):
        """Reads output from stderr and processes progress information."""
        for line in iter(pipe.readline, ''):
            if total_duration and total_duration > 0:
                match = re.search(r"time=(\d{2}):(\d{2}):(\d{2})\.(\d{2})", line)
                if match:
                    h, m, s, hs = map(int, match.groups())
                    current_time = h * 3600 + m * 60 + s + hs / 100

                    elapsed_time = time.time() - start_time
                    progress = (current_time / total_duration) * 100

                    if current_time > 0 and elapsed_time > 1:  # Avoid division by zero and initial fluctuations
                        speed = current_time / elapsed_time
                        remaining_duration = total_duration - current_time
                        eta_seconds = remaining_duration / speed
                        eta_str = time.strftime('%H:%M:%S', time.gmtime(eta_seconds))
                        gui_queue.put(('status', f"Processing... ETA: {eta_str}"))

                    gui_queue.put(('progress', min(progress, 100)))

    # Start a thread to read stderr without blocking
    stderr_thread = threading.Thread(target=read_pipe, args=(process.stderr,))
    stderr_thread.start()

    while process.poll() is None:
        if cancel_event.is_set():
            process.terminate()
            break
        time.sleep(0.1)

    stderr_thread.join()

    stdout, stderr = process.communicate()

    if cancel_event.is_set():
        raise InterruptedError("Process was cancelled by user.")
    if process.returncode != 0:
        raise ffmpeg.Error('ffmpeg', stdout, stderr)


def get_ffmpeg_args(settings):
    """Constructs a dictionary of FFmpeg arguments based on UI settings."""
    args = {}

    # --- Metadata Handling ---
    if not settings['metadata']:
        # To explicitly remove metadata, set map_metadata to -1
        args['map_metadata'] = -1
    else:
        # To keep metadata, map all streams from the source
        args['map'] = '0'

    # --- Audio Arguments (apply to both Audio and Video mode) ---
    if settings['audio_normalize']:
        args['af'] = 'loudnorm=I=-16:TP=-1.5:LRA=11'

    # --- Mode-Specific Arguments ---
    if settings['mode'] == "Video":
        args['vcodec'] = settings['video_codec']
        args['format'] = settings['output_format_video']

        resolution = settings['video_resolution']
        if resolution != "Keep Original":
            height = re.search(r'(\d+)', resolution).group(1)
            args['vf'] = f'scale=-2:{height}'

        fps = settings['video_fps']
        if fps != "Keep Original": args['r'] = fps
    else:
        args['format'] = settings['output_format_audio']

        if settings['vbr_mode']:
            args['q:a'] = settings['vbr_quality']
        else:
            args['audio_bitrate'] = settings['bitrate']

        args['vn'] = None

    return args


def handle_ffmpeg_error(e, gui_queue):
    """Formats and sends FFmpeg error messages to the GUI queue."""
    error_message = f"An unexpected error occurred: {e}"
    error_title = "FFmpeg Error"
    if hasattr(e, 'stderr') and e.stderr:
        stderr_text = e.stderr.decode('utf-8', errors='ignore') if isinstance(e.stderr, bytes) else e.stderr

        # --- CHANGE: Refined error message for codec issues ---
        if "Unknown encoder" in stderr_text or "Unknown decoder" in stderr_text:
            error_title = "Unsupported Codec"
            error_message = (
                "FFmpeg could not process the file because a required audio or video codec is not supported by your current FFmpeg build.\n\n"
                "What you can do:\n"
                "1. Try converting to a different output format.\n"
                "2. Ensure you are using a 'full build' of FFmpeg, which includes more codecs. You can find download links in the 'Help FFmpeg Config' window.\n"
                "3. Use the 'Test Libraries' button in the 'FFmpeg Library' window to check which formats your build supports."
            )
        else:
            error_message = f"An error occurred with FFmpeg:\n{stderr_text}"

    gui_queue.put(('showerror', error_title, error_message))
    gui_queue.put(('status', "Error during processing."))


# --- Processing Modes (Join, Individual) ---

def process_joined_audio(files, settings, gui_queue, cancel_event):
    """
    Joins multiple audio files into a single output file using a reliable
    intermediate format method.
    """
    gui_queue.put(('status', "Joining audio files..."))
    gui_queue.put(('progress_mode', 'indeterminate'))

    output_file = get_output_path(settings, for_join=True)
    if not output_file:
        gui_queue.put(('status', "Save cancelled."))
        gui_queue.put(('progress_mode', 'determinate'))
        return

    temp_dir = tempfile.mkdtemp()
    intermediate_files = []
    try:
        # 1. Convert all input files to a uniform intermediate format (MPEG-TS with AAC audio).
        for i, file_path in enumerate(files):
            if cancel_event.is_set(): raise InterruptedError
            gui_queue.put(('status', f"Preparing file {i + 1}/{len(files)} for joining..."))
            intermediate_file = os.path.join(temp_dir, f'{i}.ts')
            intermediate_files.append(intermediate_file)
            (
                ffmpeg.input(file_path)
                .output(intermediate_file, acodec='aac', vn=None, f='mpegts')
                .run(cmd=settings['ffmpeg_path'], quiet=True, overwrite_output=True)
            )

        if cancel_event.is_set(): raise InterruptedError

        # 2. Concatenate the intermediate files using the 'concat' protocol.
        gui_queue.put(('status', "Concatenating files..."))
        concat_input_string = f"concat:{'|'.join(intermediate_files)}"

        # 3. Take the concatenated stream and encode it to the user's final desired format.
        ffmpeg_args = get_ffmpeg_args(settings)
        stream = ffmpeg.input(concat_input_string, f='mpegts').output(output_file, **ffmpeg_args)

        args = stream.compile(settings['ffmpeg_path'], overwrite_output=True)
        gui_queue.put(('status', f"Exporting to {os.path.basename(output_file)}..."))
        run_ffmpeg_cancellable(args, gui_queue, cancel_event)

        if not cancel_event.is_set():
            gui_queue.put(('showinfo', "Processing Complete", f"Successfully joined and saved to {output_file}"))
            gui_queue.put(('status', "Join complete."))

    except InterruptedError:
        gui_queue.put(('status', "Join process cancelled."))
    except Exception as e:
        handle_ffmpeg_error(e, gui_queue)
    finally:
        shutil.rmtree(temp_dir)  # Clean up temporary files
        gui_queue.put(('progress_mode', 'determinate'))


def process_joined_video(files, settings, gui_queue, cancel_event):
    """Joins multiple video files. Requires re-encoding to an intermediate format."""
    gui_queue.put(('status', "Joining video files..."))
    gui_queue.put(('progress_mode', 'indeterminate'))

    output_file = get_output_path(settings, for_join=True)
    if not output_file:
        gui_queue.put(('status', "Save cancelled."))
        gui_queue.put(('progress_mode', 'determinate'))
        return

    temp_dir = tempfile.mkdtemp()
    intermediate_files = []
    try:
        # 1. Convert all files to an intermediate transport stream (.ts) format
        for i, file_path in enumerate(files):
            if cancel_event.is_set(): raise InterruptedError
            gui_queue.put(('status', f"Preparing file {i + 1}/{len(files)} for joining..."))
            intermediate_file = os.path.join(temp_dir, f'{i}.ts')
            intermediate_files.append(intermediate_file)
            (ffmpeg.input(file_path)
             .output(intermediate_file, vcodec='libx264', acodec='aac', f='mpegts')
             .run(cmd=settings['ffmpeg_path'], quiet=True, overwrite_output=True))

        if cancel_event.is_set(): raise InterruptedError

        # 2. Concatenate the intermediate files and apply final encoding settings
        gui_queue.put(('status', "Concatenating files..."))
        concat_input = f"concat:{'|'.join(intermediate_files)}"
        ffmpeg_args = get_ffmpeg_args(settings)

        stream = ffmpeg.input(concat_input, f='mpegts').output(output_file, **ffmpeg_args)

        args = stream.compile(settings['ffmpeg_path'], overwrite_output=True)
        run_ffmpeg_cancellable(args, gui_queue, cancel_event)

        if not cancel_event.is_set():
            gui_queue.put(('showinfo', "Processing Complete", f"Successfully joined and saved to {output_file}"))
            gui_queue.put(('status', "Join complete."))

    except InterruptedError:
        gui_queue.put(('status', "Join process cancelled."))
    except Exception as e:
        handle_ffmpeg_error(e, gui_queue)
    finally:
        shutil.rmtree(temp_dir)  # Clean up temporary files
        gui_queue.put(('progress_mode', 'determinate'))


def process_individual(files, settings, gui_queue, cancel_event):
    """Converts a list of files individually."""
    output_dir = get_output_path(settings, for_join=False)
    if not output_dir:
        gui_queue.put(('status', "Operation cancelled."))
        return

    gui_queue.put(('progress_mode', 'determinate'))
    total_files, failed_files = len(files), []

    for i, file_path in enumerate(files):
        if cancel_event.is_set():
            gui_queue.put(('status', "Conversion process cancelled."))
            break
        try:
            base_name = os.path.splitext(os.path.basename(file_path))[0]
            output_format = settings['output_format_audio'] if settings['mode'] == "Audio" else settings[
                'output_format_video']
            output_file = os.path.join(output_dir, f"{base_name}.{output_format}")

            gui_queue.put(('status', f"Converting ({i + 1}/{total_files}): {os.path.basename(file_path)}"))

            duration = None
            if settings['ffprobe_path'] and os.path.exists(settings['ffprobe_path']):
                try:
                    probe = ffmpeg.probe(file_path, cmd=settings['ffprobe_path'])
                    duration = float(probe['format']['duration'])
                except Exception:
                    gui_queue.put(('status', f"Converting ({i + 1}/{total_files})... (ETA not available)"))

            input_stream = ffmpeg.input(file_path)
            ffmpeg_args = get_ffmpeg_args(settings)
            stream = ffmpeg.output(input_stream, output_file, **ffmpeg_args)

            args = stream.compile(settings['ffmpeg_path'], overwrite_output=True)
            run_ffmpeg_cancellable(args, gui_queue, cancel_event, total_duration=duration)

        except InterruptedError:
            break
        except Exception as e:
            handle_ffmpeg_error(e, gui_queue)
            failed_files.append(os.path.basename(file_path))
            continue

    if not cancel_event.is_set():
        success_count = total_files - len(failed_files)
        summary_message = f"Finished processing.\n\nSuccessfully converted: {success_count}\nFailed: {len(failed_files)}"
        if failed_files: summary_message += "\n\nFailed files:\n" + "\n".join(failed_files)
        gui_queue.put(('showinfo', "Processing Complete", summary_message))
        gui_queue.put(('status', "Individual conversion complete."))


# --- Hardware and FFmpeg Library Testing ---

def run_encoder_detection(ffmpeg_exe, gui_queue, is_manual_test=False):
    """
    Runs `ffmpeg -encoders` to find available hardware encoders.
    This is run in a thread to avoid blocking the GUI.
    """

    def task():
        try:
            encoders_info = subprocess.check_output([ffmpeg_exe, "-encoders"], text=True, stderr=subprocess.STDOUT)
            found_encoders = []
            hw_patterns = [r'h264_nvenc', r'hevc_nvenc', r'h264_amf', r'hevc_amf',
                           r'h264_qsv', r'hevc_qsv', r'h264_videotoolbox', r'hevc_videotoolbox']
            for line in encoders_info.splitlines():
                if 'encoder' in line:
                    match = re.search(r'^\s*V.....\s+([a-zA-Z0-9_]+)', line)
                    if match:
                        encoder = match.group(1)
                        if any(p in encoder for p in hw_patterns):
                            found_encoders.append(encoder)

            hw_encoders = sorted(list(set(found_encoders)))

            if is_manual_test:
                nvidia_status = "Detected" if any('_nvenc' in e for e in hw_encoders) else "Not Detected"
                amd_status = "Detected" if any('_amf' in e for e in hw_encoders) else "Not Detected"
                intel_status = "Detected" if any('_qsv' in e for e in hw_encoders) else "Not Detected"
                test_successful = any(s == "Detected" for s in [nvidia_status, amd_status, intel_status])
                status_msg = "Status: Test Complete" if test_successful else "Status: No Supported GPU Detected"
                gui_queue.put(
                    ('codec_test_finished', status_msg, nvidia_status, amd_status, intel_status, test_successful,
                     hw_encoders))
            else:
                gui_queue.put(('update_codecs', hw_encoders))

        except Exception:
            if is_manual_test:
                gui_queue.put(('codec_test_finished', "Status: Test Failed", "Failed", "Failed", "Failed", False, []))
            gui_queue.put(('update_codecs', []))

    threading.Thread(target=task, daemon=True).start()


def run_simplified_ffmpeg_test(paths, audio_formats, video_formats, gui_queue, result_widget):
    """
    Runs a series of checks on the provided FFmpeg executables and formats.
    """

    def task():
        results = {
            'ffmpeg': {'status': 'Not Detected', 'version': ''},
            'ffprobe': {'status': 'Not Detected', 'version': ''},
            'ffplay': {'status': 'Not Detected', 'version': ''},
            'report': ''
        }
        report_lines = []

        # 1. Check executable versions and names
        for name, path in paths.items():
            if path and os.path.exists(path):
                if name in os.path.basename(path).lower():
                    try:
                        version_output = subprocess.check_output([path, "-version"], text=True,
                                                                 stderr=subprocess.STDOUT)
                        version_match = re.search(r"version\s+([^\s]+)", version_output)
                        if version_match:
                            results[name]['version'] = version_match.group(1)
                        results[name]['status'] = 'Checked'
                    except Exception:
                        results[name]['status'] = 'Error'
                else:
                    results[name]['status'] = 'Wrong File'

            version_str = f" - Version {results[name]['version']}" if results[name]['version'] else ""
            report_lines.append(f"{name.capitalize()}: {results[name]['status']}{version_str}")

        report_lines.append("\n--- Format Support ---")

        # 2. Check format support if ffmpeg is found and correct
        if results['ffmpeg']['status'] == 'Checked':
            try:
                formats_output = subprocess.check_output([paths['ffmpeg'], "-formats"], text=True,
                                                         stderr=subprocess.STDOUT)

                report_lines.append("\nAudio Formats:")
                for fmt in audio_formats:
                    if re.search(r"^\s.E\s+.*?\b" + re.escape(fmt) + r"\b", formats_output, re.MULTILINE):
                        report_lines.append(f"  {fmt.upper()} - Detected")
                    else:
                        report_lines.append(f"  {fmt.upper()} - Not Detected")

                report_lines.append("\nVideo Formats:")
                for fmt in video_formats:
                    if re.search(r"^\s.E\s+.*?\b" + re.escape(fmt) + r"\b", formats_output, re.MULTILINE):
                        report_lines.append(f"  {fmt.upper()} - Detected")
                    else:
                        report_lines.append(f"  {fmt.upper()} - Not Detected")

            except Exception as e:
                report_lines.append(f"\nCould not check formats: {e}")
        else:
            report_lines.append("\nFFmpeg not detected or incorrect file. Cannot check format support.")

        results['report'] = "\n".join(report_lines)
        gui_queue.put(('simplified_test_result', results, result_widget))

    threading.Thread(target=task, daemon=True).start()


def get_file_information(file_path, ffprobe_path, gui_queue):
    """
    Uses ffprobe to get detailed technical and metadata information about a media file.
    """
    try:
        if not ffprobe_path or not os.path.exists(ffprobe_path):
            raise FileNotFoundError("ffprobe executable not found.")

        cmd = [ffprobe_path, "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", file_path]

        result = subprocess.run(cmd, capture_output=True, text=True, check=True,
                                creationflags=subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0)
        info = json.loads(result.stdout)

        info_str = f"--- File Information for: {os.path.basename(file_path)} ---\n\n"

        # --- Technical Information ---
        if 'format' in info:
            fmt = info['format']
            duration = float(fmt.get('duration', 0))
            info_str += f"Duration: {time.strftime('%H:%M:%S', time.gmtime(duration))}.{int((duration % 1) * 100)}\n"
            info_str += f"Size: {float(fmt.get('size', 0)) / 1048576:.2f} MB\n"
            info_str += f"Bitrate: {float(fmt.get('bit_rate', 0)) / 1000:.0f} kb/s\n"
            info_str += f"Format: {fmt.get('format_long_name', 'N/A')}\n"

        # --- Stream Details ---
        if 'streams' in info:
            for stream in info['streams']:
                codec_type = stream.get('codec_type', 'N/A')
                info_str += f"\n--- {codec_type.capitalize()} Stream ---\n"
                info_str += f"  Codec: {stream.get('codec_long_name', 'N/A')}\n"

                if codec_type == 'video':
                    info_str += f"  Resolution: {stream.get('width')}x{stream.get('height')}\n"
                    if 'avg_frame_rate' in stream and stream['avg_frame_rate'] != '0/0':
                        num, den = map(int, stream['avg_frame_rate'].split('/'))
                        info_str += f"  Frame Rate: {num / den:.2f} fps\n"

                if codec_type == 'audio':
                    info_str += f"  Sample Rate: {stream.get('sample_rate')} Hz\n"
                    info_str += f"  Channels: {stream.get('channels')}\n"
                    info_str += f"  Channel Layout: {stream.get('channel_layout', 'N/A')}\n"

        tags = info.get('format', {}).get('tags', {})
        if tags:
            info_str += "\n--- Metadata Tags ---\n"
            tag_order = [
                'title', 'artist', 'album_artist', 'album', 'genre',
                'date', 'creation_time', 'track', 'synopsis', 'comment'
            ]
            for tag in tag_order:
                if tag in tags:
                    info_str += f"  {tag.replace('_', ' ').capitalize()}: {tags[tag]}\n"
            for key, value in tags.items():
                if key.lower() not in tag_order:
                    info_str += f"  {key.capitalize()}: {value}\n"

        subtitle_streams = [s for s in info.get('streams', []) if s.get('codec_type') == 'subtitle']
        audio_streams = [s for s in info.get('streams', []) if s.get('codec_type') == 'audio']

        if len(subtitle_streams) > 0:
            info_str += "\n--- Subtitle Tracks ---\n"
            for i, stream in enumerate(subtitle_streams):
                lang = stream.get('tags', {}).get('language', 'unknown')
                title = stream.get('tags', {}).get('title', f'Track {i + 1}')
                info_str += f"  {title} ({lang})\n"

        if len(audio_streams) > 1:
            info_str += "\n--- Audio Tracks ---\n"
            for i, stream in enumerate(audio_streams):
                lang = stream.get('tags', {}).get('language', 'unknown')
                title = stream.get('tags', {}).get('title', f'Track {i + 1}')
                info_str += f"  {title} ({lang})\n"

        gui_queue.put(('showinfo', "Media File Information", info_str))

    except FileNotFoundError as e:
        gui_queue.put(('showerror', "Error", str(e)))
    except subprocess.CalledProcessError as e:
        gui_queue.put(('showerror', "ffprobe Error", f"Could not get file information:\n{e.stderr}"))
    except Exception as e:
        gui_queue.put(('showerror', "Error", f"An unexpected error occurred while getting file info:\n{e}"))


def play_file(file_path, ffplay_path, ffprobe_path, gui_queue):
    """
    Plays a media file using ffplay in a separate process, with standardized window sizes.

    ffplay includes built-in controls that can be used with the keyboard and mouse:
    - Seeking: Use the Left/Right arrow keys to seek backward/forward by 10 seconds.
               Use the Up/Down arrow keys to seek by 60 seconds.
               You can also click on the seek bar at the bottom of the player.
    - Play/Pause: Press the SPACEBAR or 'p' to pause and resume playback.
    - Fullscreen: Press 'f' to toggle fullscreen mode.
    - Close: Press 'q' or ESC to close the player window.
    """
    try:
        if not ffplay_path or not os.path.exists(ffplay_path):
            raise FileNotFoundError("ffplay executable not found or path is incorrect.")

        # Determine if the file has a video stream to decide the window size.
        has_video = False
        try:
            # First, try to use ffprobe for an accurate check
            if ffprobe_path and os.path.exists(ffprobe_path):
                probe = ffmpeg.probe(file_path, cmd=ffprobe_path)
                if any(s['codec_type'] == 'video' for s in probe.get('streams', [])):
                    has_video = True
            else:
                video_extensions = ['.mp4', '.mov', '.avi', '.webm', '.wmv', '.flv', '.mkv', '.mts', '.mpeg-4',
                                    '.avchd']
                if any(file_path.lower().endswith(ext) for ext in video_extensions):
                    has_video = True
        except Exception as e:
            print(f"Could not probe file {os.path.basename(file_path)}: {e}")
            video_extensions = ['.mp4', '.mov', '.avi', '.webm', '.wmv', '.flv', '.mkv', '.mts', '.mpeg-4', '.avchd']
            if any(file_path.lower().endswith(ext) for ext in video_extensions):
                has_video = True

        # Base command for ffplay
        cmd = [ffplay_path, "-autoexit"]

        if has_video:
            cmd.extend(["-x", "1280", "-y", "720"])
            cmd.extend(["-window_title", f"Video Player - {os.path.basename(file_path)}"])
        else:
            cmd.extend(["-x", "720", "-y", "200"])
            cmd.extend(["-window_title", f"Audio Player - {os.path.basename(file_path)}"])
            cmd.extend(["-showmode", "1"])

        # Add the file to play at the end of the command
        cmd.append(file_path)

        # Run ffplay in a new process. It will open its own window.
        subprocess.Popen(cmd,
                         creationflags=subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0)

    except FileNotFoundError as e:
        gui_queue.put(('showerror', "Error", str(e)))
    except Exception as e:
        gui_queue.put(('showerror', "Error", f"Could not play file:\n{e}"))