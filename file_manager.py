import os
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog
import paramiko
from mutagen import File
import logging
from cryptography.fernet import Fernet
import json
import pygame

class FileManagerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("File Manager")

        # Server details
        self.server_ip = ""
        self.server_port = 22
        self.username = ""
        self.password = ""

        # UI Elements
        self.menu = tk.Menu(self.root)
        self.root.config(menu=self.menu)

        self.server_menu = tk.Menu(self.menu, tearoff=0)
        self.server_menu.add_command(label="Configure Server", command=self.configure_server)
        self.menu.add_cascade(label="Server", menu=self.server_menu)

        self.file_listbox = tk.Listbox(self.root, selectmode=tk.SINGLE, width=80, height=20)
        self.file_listbox.pack(pady=10)

        self.delete_button = tk.Button(self.root, text="Delete File", command=self.delete_file)
        self.delete_button.pack(pady=5)

        self.back_button = tk.Button(self.root, text="Back", command=self.go_to_parent_directory)
        self.back_button.pack(pady=5)

        self.select_directory_button = tk.Button(self.root, text="Select Directory", command=self.open_directory_window)
        self.select_directory_button.pack(pady=5)

        self.sftp = None

        # Configure logging
        logging.basicConfig(
            filename="file_manager.log",
            level=logging.INFO,
            format="%(asctime)s - %(levelname)s - %(message)s"
        )

        # Generate or load encryption key
        KEY_FILE = "encryption.key"
        if not os.path.exists(KEY_FILE):
            with open(KEY_FILE, "wb") as key_file:
                key_file.write(Fernet.generate_key())
        with open(KEY_FILE, "rb") as key_file:
            self.encryption_key = key_file.read()
        self.fernet = Fernet(self.encryption_key)

        self.server_details_file = "server_details.enc"

        pygame.init()

        # Initialize temp_directory
        self.temp_directory = os.path.expanduser("~")  # Default to user's home directory

    def configure_server(self):
        config_window = tk.Toplevel(self.root)
        config_window.title("Configure Server")

        tk.Label(config_window, text="Server IP:").grid(row=0, column=0, padx=10, pady=5, sticky="e")
        server_ip_entry = tk.Entry(config_window)
        server_ip_entry.grid(row=0, column=1, padx=10, pady=5)

        tk.Label(config_window, text="Server Port:").grid(row=1, column=0, padx=10, pady=5, sticky="e")
        server_port_entry = tk.Entry(config_window)
        server_port_entry.grid(row=1, column=1, padx=10, pady=5)

        tk.Label(config_window, text="Username:").grid(row=2, column=0, padx=10, pady=5, sticky="e")
        username_entry = tk.Entry(config_window)
        username_entry.grid(row=2, column=1, padx=10, pady=5)

        tk.Label(config_window, text="Password:").grid(row=3, column=0, padx=10, pady=5, sticky="e")
        password_entry = tk.Entry(config_window, show="*")
        password_entry.grid(row=3, column=1, padx=10, pady=5)

        def save_server_details():
            server_details = {
                "server_ip": server_ip_entry.get(),
                "server_port": server_port_entry.get(),
                "username": username_entry.get(),
                "password": password_entry.get()
            }
            encrypted_data = self.fernet.encrypt(json.dumps(server_details).encode())
            with open(self.server_details_file, "wb") as file:
                file.write(encrypted_data)
            logging.info("Server details saved and encrypted.")
            messagebox.showinfo("Success", "Server details saved successfully!")
            config_window.destroy()

        def load_saved_server():
            if os.path.exists(self.server_details_file):
                with open(self.server_details_file, "rb") as file:
                    encrypted_data = file.read()
                decrypted_data = self.fernet.decrypt(encrypted_data).decode()
                server_details = json.loads(decrypted_data)

                server_ip_entry.delete(0, tk.END)
                server_ip_entry.insert(0, server_details["server_ip"])

                server_port_entry.delete(0, tk.END)
                server_port_entry.insert(0, server_details["server_port"])

                username_entry.delete(0, tk.END)
                username_entry.insert(0, server_details["username"])

                password_entry.delete(0, tk.END)
                password_entry.insert(0, server_details["password"])

                logging.info("Loaded saved server details into the form.")
            else:
                messagebox.showerror("Error", "No saved server details found.")

        def connect_with_details():
            self.server_ip = server_ip_entry.get()
            self.server_port = int(server_port_entry.get())
            self.username = username_entry.get()
            self.password = password_entry.get()

            if self.server_ip and self.server_port and self.username and self.password:
                logging.info("Attempting to connect with provided server details.")
                config_window.destroy()
                self.connect_to_server()
            else:
                logging.error("Connection failed: Missing server details.")
                messagebox.showerror("Error", "All fields are required to connect to the server.")

        tk.Button(config_window, text="Load Saved Server", command=load_saved_server).grid(row=4, column=0, padx=10, pady=10)
        tk.Button(config_window, text="Save", command=save_server_details).grid(row=4, column=1, padx=10, pady=10)
        tk.Button(config_window, text="Connect", command=connect_with_details).grid(row=5, column=0, columnspan=2, pady=10)

    def connect_to_server(self):
        loading_screen = tk.Toplevel(self.root)
        loading_screen.title("Connecting...")
        tk.Label(loading_screen, text="Connecting to server, please wait...").pack(padx=20, pady=20)
        self.root.update()

        try:
            logging.info("Attempting to connect to server %s:%d", self.server_ip, self.server_port)
            transport = paramiko.Transport((self.server_ip, self.server_port))
            transport.connect(username=self.username, password=self.password)
            self.sftp = paramiko.SFTPClient.from_transport(transport)
            logging.info("Connected to server successfully")
            messagebox.showinfo("Success", "Connected to server successfully!")

            # Start with the root directory
            self.list_files("/")
        except Exception as e:
            logging.error("Connection error: %s", str(e))
            messagebox.showerror("Connection Error", str(e))
        finally:
            loading_screen.destroy()

    def list_files(self, remote_path="."):
        try:
            if not self.sftp:
                messagebox.showerror("Error", "Not connected to server.")
                return

            self.file_listbox.delete(0, tk.END)
            self.current_path = remote_path

            if remote_path != ".":
                self.file_listbox.insert(tk.END, "[PARENT DIR] ..")

            self.file_paths = []  # Store full paths of files and directories

            for entry in self.sftp.listdir_attr(remote_path):
                full_path = f"{remote_path.rstrip('/')}/{entry.filename}"
                self.file_paths.append(full_path)

                if entry.st_mode & 0o40000:  # Directory
                    self.file_listbox.insert(tk.END, f"[DIR] {entry.filename}")
                else:
                    self.file_listbox.insert(tk.END, entry.filename)

                # Log the file or directory being listed
                logging.info("Listed: %s", full_path)

            self.file_listbox.bind('<Button-1>', self.on_single_click)
            self.file_listbox.bind('<Double-1>', self.on_double_click)
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def on_single_click(self, event):
        try:
            selected_index = self.file_listbox.curselection()
            if selected_index:
                selected_item = self.file_listbox.get(selected_index)
                logging.info("Highlighted: %s", selected_item)
        except Exception as e:
            logging.error("Error on single click: %s", str(e))

    def on_double_click(self, event):
        try:
            selected_index = self.file_listbox.curselection()
            if selected_index:
                selected_item = self.file_listbox.get(selected_index)
                if selected_item == "[PARENT DIR] ..":
                    self.current_path = os.path.dirname(self.current_path.rstrip("/")) or "/"
                    self.list_files(self.current_path)
                elif selected_item.startswith("[DIR] "):
                    directory_name = selected_item[6:]
                    self.current_path = f"{self.current_path.rstrip('/')}/{directory_name}"
                    self.list_files(self.current_path)
        except Exception as e:
            logging.error("Error on double click: %s", str(e))

    def go_to_root(self):
        try:
            self.list_files(".")
        except Exception as e:
            logging.error("Error while returning to root directory: %s", str(e))

    def delete_file(self):
        try:
            selected_index = self.file_listbox.curselection()
            if not selected_index:
                messagebox.showerror("Error", "No file selected.")
                return

            selected_file = self.file_listbox.get(selected_index)
            full_path = self.file_paths[selected_index[0] - 1]  # Adjust for [PARENT DIR] ..

            if selected_file.startswith("[DIR]"):
                messagebox.showerror("Error", "Cannot delete a directory.")
                return

            self.sftp.remove(full_path)
            logging.info("Deleted: %s", full_path)  # Log the deleted file
            messagebox.showinfo("Success", f"Deleted {full_path} successfully!")
            self.list_files(self.current_path)
        except Exception as e:
            logging.error("Error while deleting file: %s", str(e))
            messagebox.showerror("Error", str(e))

    def go_to_parent_directory(self):
        try:
            if self.current_path and self.current_path != ".":
                self.current_path = os.path.dirname(self.current_path)
                self.list_files(self.current_path)
            else:
                messagebox.showinfo("Info", "Already at the root directory.")
        except Exception as e:
            logging.error("Error while navigating to parent directory: %s", str(e))

    def load_server_details(self):
        if os.path.exists(self.server_details_file):
            try:
                with open(self.server_details_file, "rb") as file:
                    encrypted_data = file.read()
                decrypted_data = self.fernet.decrypt(encrypted_data).decode()
                server_details = json.loads(decrypted_data)

                self.server_ip = server_details["server_ip"]
                self.server_port = int(server_details["server_port"])
                self.username = server_details["username"]
                self.password = server_details["password"]

                logging.info("Server details loaded successfully on startup.")
            except Exception as e:
                logging.error("Failed to load server details: %s", str(e))
                messagebox.showerror("Error", "Failed to load server details.")

    def auto_login(self):
        if os.path.exists(self.server_details_file):
            try:
                with open(self.server_details_file, "rb") as file:
                    encrypted_data = file.read()
                decrypted_data = self.fernet.decrypt(encrypted_data).decode()
                server_details = json.loads(decrypted_data)

                self.server_ip = server_details["server_ip"]
                self.server_port = int(server_details["server_port"])
                self.username = server_details["username"]
                self.password = server_details["password"]

                logging.info("Server details loaded successfully. Attempting auto-login.")
                self.connect_to_server()
            except Exception as e:
                logging.error("Auto-login failed: %s", str(e))
                messagebox.showerror("Error", "Auto-login failed. Please configure the server manually.")

    def open_directory_window(self):
        if not self.sftp:
            messagebox.showerror("Error", "Not connected to server.")
            return
        self.selection = self.file_listbox.get(self.file_listbox.curselection())
        self.curr_dir = self.current_path + '/' + self.selection[6:] if self.selection.startswith("[DIR] ") else ''
        print(self.curr_dir)
        def list_all_files_recursive(remote_path):
            try:
                files = []
                for entry in self.sftp.listdir_attr(remote_path):
                    full_path = f"{remote_path.rstrip('/')}/{entry.filename}"
                    if entry.st_mode & 0o40000:  # Directory
                        files.extend(list_all_files_recursive(full_path))
                    else:
                        files.append(full_path)
                return files
            except Exception as e:
                logging.error("Error while listing files: %s", str(e))
                return []

        def populate_file_list(selected_directory):
            file_listbox.delete(0, tk.END)
            all_files = list_all_files_recursive(selected_directory)
            for file in all_files:
                file_listbox.insert(tk.END, file)

        def delete_selected_files():
            selected_files = [file_listbox.get(i) for i in file_listbox.curselection()]
            for file in selected_files:
                try:
                    self.sftp.remove(file)
                    logging.info("Deleted: %s", file)
                except Exception as e:
                    logging.error("Error deleting file %s: %s", file, str(e))
            populate_file_list(self.curr_dir)
            messagebox.showinfo("Success", "Selected files deleted successfully!")

        def play_music():
            try:
                selected_file = file_listbox.get(file_listbox.curselection())
                local_file = os.path.join(self.temp_directory, os.path.basename(selected_file))
                self.sftp.get(selected_file, local_file)

                def update_slider():
                    if pygame.mixer.music.get_busy():
                        current_pos = pygame.mixer.music.get_pos() / 1000
                        if abs(music_slider.get() - current_pos) > 1:  # Avoid frequent resets
                            music_slider.set(current_pos)
                        music_popup.after(1000, update_slider)

                def stop_music():
                    pygame.mixer.music.stop()
                    music_popup.destroy()

                def set_music_position(event):
                    pos = music_slider.get()
                    pygame.mixer.music.stop()
                    pygame.mixer.music.play(loops=-1, start=pos)

                def play_with_windows_media_player():
                    os.startfile(local_file)
                    music_popup.destroy()

                pygame.mixer.init()
                pygame.mixer.music.load(local_file)
                pygame.mixer.music.play(loops=-1)  # Loop indefinitely

                music_popup = tk.Toplevel(dir_window)
                music_popup.title("Music Player")

                music_length = pygame.mixer.Sound(local_file).get_length()
                music_slider = tk.Scale(music_popup, from_=0, to=music_length, orient=tk.HORIZONTAL, length=300)
                music_slider.bind("<ButtonRelease-1>", set_music_position)
                music_slider.pack(pady=10)

                tk.Button(music_popup, text="Stop", command=stop_music).pack(pady=5)

                toggle_frame = tk.Frame(music_popup)
                toggle_frame.pack(pady=5)

                tk.Label(toggle_frame, text="Playback Mode:").pack(side=tk.LEFT, padx=5)
                playback_mode = tk.StringVar(value="in_app")

                def switch_playback_mode():
                    if playback_mode.get() == "in_app":
                        stop_music()
                        play_with_windows_media_player()

                tk.Radiobutton(toggle_frame, text="In-App", variable=playback_mode, value="in_app").pack(side=tk.LEFT)
                tk.Radiobutton(toggle_frame, text="Windows Media Player", variable=playback_mode, value="windows", command=switch_playback_mode).pack(side=tk.LEFT)

                update_slider()
            except Exception as e:
                messagebox.showerror("Error", str(e))

        dir_window = tk.Toplevel(self.root)
        dir_window.title("Server File Viewer")

        dir_window.rowconfigure(0, weight=1)
        dir_window.columnconfigure(0, weight=1)

        frame = tk.Frame(dir_window)
        frame.grid(row=0, column=0, sticky="nsew")

        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)

        file_listbox = tk.Listbox(frame, selectmode=tk.MULTIPLE, width=80, height=20)  # Allow multiple selection
        file_listbox.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)

        button_frame = tk.Frame(dir_window)
        button_frame.grid(row=1, column=0, sticky="ew")

        tk.Button(button_frame, text="Play Music", command=play_music).pack(side=tk.LEFT, padx=5, pady=5)
        tk.Button(button_frame, text="Delete Selected Files", command=delete_selected_files).pack(side=tk.LEFT, padx=5, pady=5)
        populate_file_list(self.curr_dir)
        # selected_directory = simpledialog.askstring("Select Directory", "Enter the remote directory path:")
        # if selected_directory:
        #     populate_file_list(selected_directory)

        # Set Temp Directory functionality
        def set_temp_directory():
            temp_dir = filedialog.askdirectory(title="Select Temporary Directory")
            if temp_dir:
                self.temp_directory = temp_dir
                logging.info("Temporary directory set to: %s", self.temp_directory)
                messagebox.showinfo("Success", f"Temporary directory set to: {self.temp_directory}")
            else:
                logging.warning("No directory selected for temporary files.")

        # Add a menu option to set the temporary directory
        self.menu.add_command(label="Set Temp Directory", command=set_temp_directory)

# Ensure the main loop is running
if __name__ == "__main__":
    root = tk.Tk()
    app = FileManagerApp(root)
    app.auto_login()  # Attempt auto-login if server details exist
    root.mainloop()  # Start the Tkinter main loop