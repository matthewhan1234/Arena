import socket
import json
import threading
import tkinter as tk
import random
from pathlib import Path
import os, sys
from pathlib import Path


try:
    from PIL import Image, ImageTk

    PIL_AVAILABLE = True
except Exception:
    PIL_AVAILABLE = False

# =========================
# Sprite configuration
# =========================
SPRITE_DIR = "assets"  # 存放贴图的文件夹（自行创建）
SPRITE_EXT = ".png"  # 贴图后缀
SPRITE_SIZE = (64, 64)  # 统一缩放尺寸（需要 PIL 才能缩放）
SPRITE_ANCHOR = "center"  # 图像锚点（中心）
SPRITE_REFS = []  # 防止贴图被 GC 回收

# =========================
# Server configuration 修改贴图
# =========================
SERVER_HOST = "127.0.0.1"
SERVER_PORT = 1212  # Default port for the server, can be changed if needed
HOW_TO_PLAY_TEXT = (
    "How to Play:\n"
    "• Objective: Reduce the opponent's health to 0 to win.\n"
    "• Movement: Arrow keys ← ↑ → ↓ to move your hero.\n"
    "• Skills: Press keys 1 / 2 / 3 to cast skills.\n"
    "• Health Bars: Green text above heads shows current HP.\n"
    "• Connection: The client connects to the server automatically.\n\n"
    "Tips:\n"
    "• Keep moving to avoid skills.\n"
    "• Time your skills for maximum impact.\n"
    "• Watch both your own and the opponent's HP.\n"
)

# 放到文件顶部附近（clientC.py / server_run.py 都建议加）
def resource_path(rel_path: str) -> str:
    """兼容 PyInstaller 的资源定位：先取 _MEIPASS，再退回脚本目录"""
    base = getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)
    return str(Path(base) / rel_path)


def _sprite_path_for(hero_name: str) -> str:
    """
    Build a path to sprite file from hero name (lowercase, remove spaces/hyphens).
    """
    safe = hero_name.lower().replace(" ", "").replace("-", "_")
    #return str(Path(SPRITE_DIR) / f"{safe}{SPRITE_EXT}")
    path = resource_path(str(Path("assets") / f"{safe}{SPRITE_EXT}"))
    return path


def load_sprite_image(hero_name: str, size=SPRITE_SIZE):
    """
    Load a sprite (PNG) for the given hero name.

    Args:
        hero_name (str): Hero name, e.g., 'zhaoyun'.
        size (tuple[int,int]): (w,h) to scale to when PIL is available.

    Returns:
        object: A Tk-compatible image object (PhotoImage or ImageTk.PhotoImage).
    """
    path = _sprite_path_for(hero_name)
    if PIL_AVAILABLE:
        img = Image.open(path).convert("RGBA")
        if size:
            img = img.resize(size, Image.LANCZOS)
        return ImageTk.PhotoImage(img)
    else:
        # Tk 8.6 一般支持 PNG；若你的 Tk 版本不支持 PNG，请安装 Pillow
        import tkinter as tk
        return tk.PhotoImage(file=path)


# Global variables to store local and peer character data
character_data = {}
peer_character_data = {}
character = {}
peer_character = {}
canvas = None  # Declare canvas as a global variable

send_buffer = ""
recv_buffer = ""


def shutdown_client(root=None, sock=None, exit_code=0):
    """
    Gracefully close the server connection, destroy the UI, and exit.

    Args:
        root (tk.Tk|tk.Toplevel|None): Root or toplevel window to destroy.
        sock (socket.socket|None): Connected socket to close.
        exit_code (int): Process exit code.

    Returns:
        None
    """
    import sys
    import socket as _socket

    # 1) Close network socket gracefully
    if sock is not None:
        try:
            try:
                sock.shutdown(_socket.SHUT_RDWR)  # stop both send/recv
            except Exception:
                pass
            sock.close()
        except Exception:
            pass

    # 2) Destroy UI
    try:
        if root is not None:
            root.destroy()
    except Exception:
        pass

    # 3) Exit process
    try:
        sys.exit(exit_code)
    except SystemExit:
        raise


def _connect_to_server_once(host, port, timeout=5):
    """
    Try to connect once to the server.

    Args:
        host (str): Server host.
        port (int): Server port.
        timeout (int): Seconds to wait before timing out.

    Returns:
        socket.socket: Connected socket.

    Raises:
        ConnectionRefusedError, socket.timeout, OSError: On failure.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect((host, port))
        s.settimeout(None)  # back to blocking for normal recv
        return s
    except Exception:
        s.close()
        raise


def connect_to_server_with_ui(default_host, default_port):
    """
    Connect to server with a GUI error prompt and retry flow.

    Args:
        default_host (str): Default server host.
        default_port (int): Default server port.

    Returns:
        socket.socket: Connected socket.

    Raises:
        SystemExit: If the user cancels.
    """
    import tkinter as tk
    from tkinter import messagebox, simpledialog

    host = default_host
    port = default_port

    # 建一个临时隐藏的根窗口，确保弹窗正常工作（如果此时没有任何 Tk 主窗口）
    temp_root = None
    try:
        temp_root = tk.Tk()
        temp_root.withdraw()
    except tk.TclError:
        temp_root = None

    while True:
        try:
            sock = _connect_to_server_once(host, port, timeout=5)
            # 连接成功就销毁临时 root
            if temp_root is not None:
                temp_root.destroy()
            return sock
        except Exception as e:
            # connect error, pop up a message, reconnection or cancel
            err_msg = f"Cannot connect to server at {host}:{port}\n\n{e.__class__.__name__}: {e}"
            retry = messagebox.askretrycancel("Connection Error", err_msg)
            if retry:
                # if change address or port
                change = messagebox.askyesno("Connection Settings", "Do you want to edit host/port before retry?")
                if change:
                    new_host = simpledialog.askstring("Server Host", "Enter server host:", initialvalue=host)
                    if new_host:
                        host = new_host.strip()
                    new_port = simpledialog.askinteger("Server Port", "Enter server port:", initialvalue=port,
                                                       minvalue=1, maxvalue=65535)
                    if new_port:
                        port = int(new_port)
                continue
            else:
                if temp_root is not None:
                    temp_root.destroy()
                raise SystemExit("User canceled connection.")


def show_welcome_screen(heroes):
    """
    Show a startup 'Home / How to Play' screen with instructions and hero selection.

    Args:
        heroes (list[dict]): List of hero dicts loaded from JSON. Each dict must include 'name'.

    Returns:
        str: The selected hero name.

    Raises:
        SystemExit: If the user closes the window or clicks Exit without selecting a hero.
    """
    import tkinter as tk
    from tkinter import ttk, messagebox

    chosen = {"name": None}

    # Wider window & resizable to avoid clipping on HiDPI or large fonts
    root = tk.Tk()
    root.title("Arena — Home")
    root.geometry("720x520")  # was 520x480 → widened
    root.minsize(640, 480)
    root.resizable(True, True)

    # Header
    header = ttk.Frame(root)
    header.pack(fill="x", padx=12, pady=(12, 6))
    ttk.Label(header, text="Arena", font=("Arial", 18, "bold")).pack(anchor="w")
    ttk.Label(header, text="Home / How to Play", font=("Arial", 11)).pack(anchor="w", pady=(2, 0))

    # Main two-column area
    main = ttk.Frame(root, padding=(12, 8))
    main.pack(fill="both", expand=True)
    # Give left column more weight but ensure right column has a minimum width
    main.columnconfigure(0, weight=3, minsize=340)
    main.columnconfigure(1, weight=2, minsize=260)
    main.rowconfigure(0, weight=1)

    # Left: instructions
    left = ttk.Frame(main)
    left.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
    ttk.Label(left, text="How to Play", font=("Arial", 12, "bold")).pack(anchor="w", pady=(0, 6))
    text = tk.Text(left, height=18, wrap="word")
    text.insert("1.0", HOW_TO_PLAY_TEXT)
    text.configure(state="disabled")
    text.pack(fill="both", expand=True)

    # Right: hero selection (LabelFrame title avoids label width clipping)
    right = ttk.Frame(main)
    right.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
    group = ttk.LabelFrame(right, text="Select Your Hero", labelanchor="n", padding=8)
    group.pack(fill="both", expand=True)

    # Listbox + vertical scrollbar
    lb_wrap = ttk.Frame(group)
    lb_wrap.pack(fill="both", expand=True)
    lb_wrap.columnconfigure(0, weight=1)
    lb_wrap.rowconfigure(0, weight=1)

    scrollbar = ttk.Scrollbar(lb_wrap, orient="vertical")
    listbox = tk.Listbox(
        lb_wrap,
        height=min(12, max(6, len(heroes))),
        yscrollcommand=scrollbar.set,
        exportselection=False
    )
    scrollbar.config(command=listbox.yview)
    listbox.grid(row=0, column=0, sticky="nsew")
    scrollbar.grid(row=0, column=1, sticky="ns", padx=(6, 0))

    for h in heroes:
        listbox.insert(tk.END, h["name"])
    if heroes:
        listbox.select_set(0)

    selected_label = ttk.Label(group, text="Selected: (none)")
    selected_label.pack(anchor="w", pady=(8, 0))

    def on_select(_evt=None):
        idxs = listbox.curselection()
        if idxs:
            selected_label.config(text=f"Selected: {heroes[idxs[0]]['name']}")

    listbox.bind("<<ListboxSelect>>", on_select)
    on_select()

    # Bottom buttons
    btns = ttk.Frame(root)
    btns.pack(pady=10)

    def start_game():
        idxs = listbox.curselection()
        if not idxs:
            messagebox.showwarning("Start Game", "Please choose a hero.")
            return
        chosen["name"] = heroes[idxs[0]]["name"]
        root.destroy()

    ttk.Button(btns, text="Start Game", command=start_game).pack(side="left", padx=6)
    ttk.Button(btns, text="Exit", command=root.destroy).pack(side="left", padx=6)

    root.mainloop()

    if not chosen["name"]:
        raise SystemExit("Game closed before starting.")
    return chosen["name"]


def load_heroes():
    """
    Load hero data from JSON file.

    Returns:
        list: A list of hero dictionaries.
    """
    # with open('property.json', 'r', encoding='utf-8') as base_file:
    with open(resource_path('property.json'), 'r', encoding='utf-8') as base_file:
        data = json.load(base_file)
    return data['heroes']


def select_hero(heroes):
    """
    Prompt the user to select a hero.

    Args:
        heroes (list): List of available heroes.

    Returns:
        str: The selected hero name.
    """
    print("Please choose a hero:")
    for i, hero in enumerate(heroes):
        print(f"{i + 1}. {hero['name']}")
    choice = int(input("Enter hero number: ")) - 1
    if 0 <= choice < len(heroes):
        return heroes[choice]['name']
    else:
        print("Invalid choice, please try again.")
        return select_hero(heroes)


def select_hero_ui(heroes):
    """
    Show a GUI dialog to select a hero.

    Args:
        heroes (list[dict]): List of hero dicts loaded from JSON. Each hero dict contains at least a 'name' key.

    Returns:
        str: The selected hero name.

    Raises:
        SystemExit: If the user closes the dialog without making a selection.
    """
    import tkinter as tk
    from tkinter import ttk, messagebox

    selection = {"value": None}

    # Build a small modal-like window for hero selection
    root = tk.Tk()
    root.title("Select Hero")
    root.geometry("360x320")
    root.resizable(False, False)

    ttk.Label(root, text="Please select a hero:", font=("Arial", 12)).pack(pady=10)

    # Listbox for hero names
    listbox = tk.Listbox(root, height=min(10, len(heroes)))
    for hero in heroes:
        listbox.insert(tk.END, hero["name"])
    listbox.pack(fill="both", expand=True, padx=12)
    if len(heroes) > 0:
        listbox.select_set(0)

    # Buttons
    def on_confirm():
        idxs = listbox.curselection()
        if not idxs:
            messagebox.showwarning("Select Hero", "Please choose a hero.")
            return
        selection["value"] = heroes[idxs[0]]["name"]
        root.destroy()

    def on_cancel():
        root.destroy()

    btn_frame = ttk.Frame(root)
    btn_frame.pack(pady=10)
    ttk.Button(btn_frame, text="OK", command=on_confirm).pack(side="left", padx=6)
    ttk.Button(btn_frame, text="Cancel", command=on_cancel).pack(side="left", padx=6)

    # Enter the dialog loop
    root.mainloop()

    if selection["value"] is None:
        raise SystemExit("Hero selection canceled by user.")
    return selection["value"]


def load_character_data(hero_name):
    """
    Load base stats of a selected hero.

    Args:
        hero_name (str): The name of the chosen hero.

    Returns:
        dict: Character data including name, position, health, and skills.
    """
    # with open('property.json', 'r', encoding='utf-8') as base_file:
    with open(resource_path('property.json'), 'r', encoding='utf-8') as base_file:
        data = json.load(base_file)

    for hero in data['heroes']:
        if hero['name'] == hero_name:
            base_stats = hero
            break
    else:
        raise ValueError(f"Hero '{hero_name}' not found")

    character_data.update({
        "name": base_stats['name'],
        "x": 650,  # Initial X position
        "y": 100,  # Initial Y position
        "health": base_stats['base_health'],
        "skills": base_stats['skills']
    })

    return character_data


def initialize_peer_character(peer_name):
    """
    Initialize peer character data with default values.

    Args:
        peer_name (str): The name of the peer hero.

    Returns:
        dict: Updated peer character data.
    """
    peer_character_data.update({
        'name': peer_name,
        'x': 150,  # Initial X position
        'y': 100,  # Initial Y position
        'health': 1000,  # Default health
        'skills': [{"base_damage": 0}] * 3  # Initialize skills list
    })
    return character_data


def send_data(client_socket, opr_type, hero_name, hero_x="", hero_y="", hero_skill="", peer_hero="", damage=0):
    """
    Send data to the server.

    Args:
        client_socket (socket.socket): The client socket.
        opr_type (str): Operation type ("0" login, "1" movement, "2" skill).
        hero_name (str): Name of the local hero.
        hero_x (str): X coordinate.
        hero_y (str): Y coordinate.
        hero_skill (str): Skill index.
        peer_hero (str): Peer hero name.
        damage (int): Damage value.

    Returns:
        None
    """
    global send_buffer
    try:
        data = {
            "opr_type": opr_type,
            "hero_name": hero_name,
            "hero_x": hero_x,
            "hero_y": hero_y,
            "hero_skill": hero_skill,
            "peer_hero": peer_hero,
        }
        json_data = json.dumps(data).encode('utf-8')
        send_buffer += json_data.decode('utf-8')
        client_socket.send(json_data)
        print(f"Sent data: {json.dumps(data, indent=4, ensure_ascii=False)}")
    except Exception as e:
        print(f"Error sending data: {e}")


def send_login_data(client_socket, hero_name):
    """Send login data to the server."""
    send_data(client_socket, "0", hero_name)


def send_position(client_socket, x, y):
    """Send position update to the server."""
    send_data(client_socket, "1", character_data['name'], hero_x=str(x), hero_y=str(y))


def send_skill(client_socket, skill_index):
    """Send skill usage to the server and display visual effect."""
    skill = character_data['skills'][skill_index]
    damage = random.randint(skill['base_damage'] - 20, skill['base_damage'] + 20)
    send_data(client_socket, "2", character_data['name'], hero_skill=str(skill_index),
              peer_hero=peer_character_data['name'], damage=damage)
    display_skill_effect(character_data['x'], character_data['y'], peer_character_data['x'], peer_character_data['y'],
                         skill_index)


def receive_data(client_socket, canvas, peer_character, peer_health_text, health_text):
    """
    Continuously receive data from the server and update the UI accordingly.

    Args:
        client_socket (socket.socket): Client socket.
        canvas (tk.Canvas): Tkinter canvas object.
        peer_character (dict): Peer character drawing elements.
        peer_health_text (int): Peer health text element.
        health_text (int): Local health text element.

    Returns:
        None
    """
    global recv_buffer
    try:
        while True:
            response = client_socket.recv(4096).decode('utf-8')
            if response:
                recv_buffer += response
                while True:
                    try:
                        data, index = json.JSONDecoder().raw_decode(recv_buffer)
                        print(f"Received data: {json.dumps(data, indent=4, ensure_ascii=False)}")
                        if 's_resp_type' in data:
                            s_resp_type = data['s_resp_type']
                            if s_resp_type == "0":
                                initialize_hero_status(data, canvas, health_text, peer_health_text)
                            elif s_resp_type == "1":
                                update_positions(data, canvas, health_text, peer_health_text)
                            elif s_resp_type == "2":
                                handle_skill_update(data, canvas, health_text, peer_health_text)
                        recv_buffer = recv_buffer[index:].lstrip()
                    except json.JSONDecodeError:
                        break
            else:
                break
    except Exception as e:
        print(f"Error receiving data: {e}")


def initialize_hero_status(data, canvas, health_text, peer_health_text):
    """
    Initialize hero and peer hero health and update UI.

    Args:
        data (dict): Data from the server.
        canvas (tk.Canvas): Tkinter canvas object.
        health_text (int): Local health text.
        peer_health_text (int): Peer health text.

    Returns:
        None
    """
    character_data['name'] = data['s_hero1_name']
    character_data['health'] = int(data['s_hero1_health']) if data['s_hero1_health'] else 0
    peer_character_data['name'] = data['s_hero2_name']
    peer_character_data['health'] = int(data['s_hero2_health']) if data['s_hero2_health'] else 0

    canvas.itemconfig(health_text, text=f"{character_data['name']} Health: {character_data['health']}")
    canvas.itemconfig(peer_health_text, text=f"{peer_character_data['name']} Health: {peer_character_data['health']}")


def update_positions2(data, canvas, health_text, peer_health_text):
    """
    Update hero and peer hero positions on the canvas.

    Args:
        data (dict): Data from the server.
        canvas (tk.Canvas): Tkinter canvas object.
        health_text (int): Local health text.
        peer_health_text (int): Peer health text.

    Returns:
        None
    """
    character_data['x'] = int(data['s_hero1_x']) if data['s_hero1_x'] else character_data['x']
    character_data['y'] = int(data['s_hero1_y']) if data['s_hero1_y'] else character_data['y']
    peer_character_data['x'] = int(data['s_hero2_x']) if data['s_hero2_x'] else peer_character_data['x']
    peer_character_data['y'] = int(data['s_hero2_y']) if data['s_hero2_y'] else peer_character_data['y']

    # Update local character parts
    canvas.coords(character['head'], character_data['x'] - 10, character_data['y'] - 10, character_data['x'] + 10,
                  character_data['y'] + 10)
    canvas.coords(character['body'], character_data['x'], character_data['y'] + 10, character_data['x'],
                  character_data['y'] + 50)
    canvas.coords(character['left_arm'], character_data['x'], character_data['y'] + 20, character_data['x'] - 15,
                  character_data['y'] + 30)
    canvas.coords(character['right_arm'], character_data['x'], character_data['y'] + 20, character_data['x'] + 15,
                  character_data['y'] + 30)
    canvas.coords(character['left_leg'], character_data['x'], character_data['y'] + 50, character_data['x'] - 15,
                  character_data['y'] + 70)
    canvas.coords(character['right_leg'], character_data['x'], character_data['y'] + 50, character_data['x'] + 15,
                  character_data['y'] + 70)
    canvas.coords(health_text, character_data['x'], character_data['y'] - 30)

    # Update peer character parts
    canvas.coords(peer_character['head'], peer_character_data['x'] - 10, peer_character_data['y'] - 10,
                  peer_character_data['x'] + 10, peer_character_data['y'] + 10)
    canvas.coords(peer_character['body'], peer_character_data['x'], peer_character_data['y'] + 10,
                  peer_character_data['x'], peer_character_data['y'] + 50)
    canvas.coords(peer_character['left_arm'], peer_character_data['x'], peer_character_data['y'] + 20,
                  peer_character_data['x'] - 15, peer_character_data['y'] + 30)
    canvas.coords(peer_character['right_arm'], peer_character_data['x'], peer_character_data['y'] + 20,
                  peer_character_data['x'] + 15, peer_character_data['y'] + 30)
    canvas.coords(peer_character['left_leg'], peer_character_data['x'], peer_character_data['y'] + 50,
                  peer_character_data['x'] - 15, peer_character_data['y'] + 70)
    canvas.coords(peer_character['right_leg'], peer_character_data['x'], peer_character_data['y'] + 50,
                  peer_character_data['x'] + 15, peer_character_data['y'] + 70)
    canvas.coords(peer_health_text, peer_character_data['x'], peer_character_data['y'] - 30)


def update_positions(data, canvas, health_text, peer_health_text):
    """
    Update local and peer hero sprite positions based on server data.
    """
    character_data['x'] = int(data['s_hero1_x']) if data['s_hero1_x'] else character_data['x']
    character_data['y'] = int(data['s_hero1_y']) if data['s_hero1_y'] else character_data['y']
    peer_character_data['x'] = int(data['s_hero2_x']) if data['s_hero2_x'] else peer_character_data['x']
    peer_character_data['y'] = int(data['s_hero2_y']) if data['s_hero2_y'] else peer_character_data['y']

    # Sprite centers
    canvas.coords(character['sprite'], character_data['x'], character_data['y'])
    canvas.coords(peer_character['sprite'], peer_character_data['x'], peer_character_data['y'])

    # Text above heads (use sprite half height if available)
    hh = (SPRITE_SIZE[1] // 2) if 'sprite' in character else 10
    phh = (SPRITE_SIZE[1] // 2) if 'sprite' in peer_character else 10
    canvas.coords(health_text, character_data['x'], character_data['y'] - (hh + 10))
    canvas.coords(peer_health_text, peer_character_data['x'], peer_character_data['y'] - (phh + 10))


def handle_skill_update(data, canvas, health_text, peer_health_text):
    """
    Handle skill effect updates and health changes.

    Args:
        data (dict): Data from the server.
        canvas (tk.Canvas): Tkinter canvas object.
        health_text (int): Local health text.
        peer_health_text (int): Peer health text.

    Returns:
        None
    """
    character_data['health'] = int(data['s_hero1_health']) if data['s_hero1_health'] else character_data['health']
    peer_character_data['health'] = int(data['s_hero2_health']) if data['s_hero2_health'] else peer_character_data[
        'health']

    canvas.itemconfig(health_text, text=f"{character_data['name']} Health: {character_data['health']}")
    canvas.itemconfig(peer_health_text, text=f"{peer_character_data['name']} Health: {peer_character_data['health']}")

    skill_index = int(data['s_hero1_skill']) if int(data['s_hero1_skill']) < 99 else int(data['s_hero2_skill'])
    display_skill_effect(character_data['x'], character_data['y'], peer_character_data['x'], peer_character_data['y'],
                         skill_index)

    if character_data['health'] == 0:
        game_over(f"{peer_character_data['name']} wins!")
        # canvas.itemconfig(character['head'], fill='gray')
    if peer_character_data['health'] == 0:
        game_over(f"{character_data['name']} wins!")
        # canvas.itemconfig(peer_character['head'], fill='gray')


def display_skill_effect(x, y, peer_x, peer_y, skill_index):
    """
    Display skill effects visually on the canvas.

    Args:
        x (int): Local hero X position.
        y (int): Local hero Y position.
        peer_x (int): Peer hero X position.
        peer_y (int): Peer hero Y position.
        skill_index (int): Index of the skill.

    Returns:
        None
    """
    global canvas
    colors = ["red", "blue", "green", "purple", "orange", "yellow"]
    effects = []

    if skill_index == 0:
        # Triangle
        for color in colors:
            points = [x, y - 100, x - 100, y + 100, x + 100, y + 100]
            effect = canvas.create_polygon(points, outline=color, fill='', width=3)
            effects.append(effect)
            points_peer = [peer_x, peer_y - 50, peer_x - 50, peer_y + 50, peer_x + 50, peer_y + 50]
            effect_peer = canvas.create_polygon(points_peer, outline=color, fill='', width=3)
            effects.append(effect_peer)
    elif skill_index == 1:
        # Circle
        for color in colors:
            effect = canvas.create_oval(x - 100, y - 100, x + 100, y + 100, outline=color, width=3)
            effects.append(effect)
            effect = canvas.create_oval(peer_x - 50, peer_y - 50, peer_x + 50, peer_y + 50, outline=color, width=3)
            effects.append(effect)
    elif skill_index == 2:
        # Rectangle
        for color in colors:
            effect = canvas.create_rectangle(x - 80, y - 80, x + 80, y + 80, outline=color, width=3)
            effects.append(effect)
            effect = canvas.create_rectangle(peer_x - 50, peer_y - 50, peer_x + 50, peer_y + 50, outline=color, width=3)
            effects.append(effect)

    def remove_effects():
        for effect in effects:
            canvas.delete(effect)

    canvas.after(500, remove_effects)


def send_health_update(client_socket, health):
    """Send health update data to the server."""
    try:
        health_data = json.dumps({'health_update': {'health': health}}).encode('utf-8')
        client_socket.send(health_data)
    except Exception as e:
        print(f"Error sending health data: {e}")


def send_name_update(client_socket, name):
    """Send name update data to the server."""
    try:
        name_data = json.dumps({'name': name}).encode('utf-8')
        client_socket.send(name_data)
    except Exception as e:
        print(f"Error sending name data: {e}")


def move_character2(character, dx, dy, canvas, client_socket, character_data, health_text):
    """
    Move character on the canvas and notify the server.

    Args:
        character (dict): Character drawing elements.
        dx (int): X offset.
        dy (int): Y offset.
        canvas (tk.Canvas): Tkinter canvas object.
        client_socket (socket.socket): Client socket.
        character_data (dict): Local character data.
        health_text (int): Health text element.

    Returns:
        None
    """
    character_data['x'] += dx
    character_data['y'] += dy
    canvas.move(character['head'], dx, dy)
    canvas.move(character['body'], dx, dy)
    canvas.move(character['left_arm'], dx, dy)
    canvas.move(character['right_arm'], dx, dy)
    canvas.move(character['left_leg'], dx, dy)
    canvas.move(character['right_leg'], dx, dy)
    canvas.move(health_text, dx, dy)
    send_position(client_socket, character_data['x'], character_data['y'])


def move_character(character, dx, dy, canvas, client_socket, character_data, health_text):
    """
    Move the hero sprite on the canvas and notify the server.

    Args:
        character (dict): Dict containing 'sprite' canvas item id.
        dx (int): Delta X.
        dy (int): Delta Y.
        canvas (tk.Canvas): Canvas object.
        client_socket (socket.socket): Connected socket.
        character_data (dict): Local hero data.
        health_text (int): Canvas text item id for HP.

    Returns:
        None
    """
    character_data['x'] += dx
    character_data['y'] += dy
    canvas.move(character['sprite'], dx, dy)
    canvas.move(health_text, dx, dy)
    send_position(client_socket, character_data['x'], character_data['y'])


def game_over(winner):
    """
    Display game over dialog.

    Args:
        winner (str): Winner message.

    Returns:
        None
    """
    game_over_window = tk.Toplevel()
    game_over_window.title("Game Over")
    game_over_label = tk.Label(game_over_window, text=f"Game Over! {winner} wins!", font=("Arial", 24))
    game_over_label.pack(padx=20, pady=20)
    close_button = tk.Button(game_over_window, text="Close", command=game_over_window.destroy, font=("Arial", 14))
    close_button.pack(pady=10)


def start_client():
    """
    Start client, connect to server, initialize heroes and UI.

    Returns:
        None
    """
    global character_data, peer_character_data, client_socket, canvas, character, peer_character
    heroes = load_heroes()
    # hero_name = select_hero(heroes)  # Select hero name using command
    # hero_name = select_hero_ui(heroes)
    hero_name = show_welcome_screen(heroes)  # <-- New: GUI home + hero selection

    character_data = load_character_data(hero_name)

    # Get the peer hero name
    peer_name = None
    for hero in heroes:
        if hero['name'] != hero_name:
            peer_name = hero['name']
            break

    if peer_name is None:
        raise ValueError("Peer hero name not found")

    initialize_peer_character(peer_name)  # Initialize peer character

    # client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # client_socket.connect((SERVER_HOST, SERVER_PORT))  # Ensure port matches server
    client_socket = connect_to_server_with_ui(SERVER_HOST, SERVER_PORT)

    send_login_data(client_socket, hero_name)

    root = tk.Tk()
    root.title(f"{hero_name} Control Panel")

    # Handle window close (X) → close socket and exit
    def on_close():
        from tkinter import messagebox
        if messagebox.askokcancel("Exit Game", "Disconnect and exit the game?"):
            shutdown_client(root=root, sock=client_socket, exit_code=0)

    root.protocol("WM_DELETE_WINDOW", on_close)  # bind close button

    canvas = tk.Canvas(root, width=800, height=400, bg="white")
    canvas.pack()

    # Draw grass patches
    for i in range(5):
        x = random.randint(100, 700)
        y = random.randint(50, 350)
        canvas.create_oval(x - 20, y - 10, x + 20, y + 10, outline="green", fill="green")

    # Draw middle line
    canvas.create_line(50, 200, 750, 200, fill="black", width=3)

    '''
    # Draw local character
    character = {
        'head': canvas.create_oval(character_data['x'] - 10, character_data['y'] - 10, character_data['x'] + 10,
                                   character_data['y'] + 10, fill="red"),
        'body': canvas.create_line(character_data['x'], character_data['y'] + 10, character_data['x'],
                                   character_data['y'] + 50, fill="red", width=2),
        'left_arm': canvas.create_line(character_data['x'], character_data['y'] + 20, character_data['x'] - 15,
                                       character_data['y'] + 30, fill="red", width=2),
        'right_arm': canvas.create_line(character_data['x'], character_data['y'] + 20, character_data['x'] + 15,
                                        character_data['y'] + 30, fill="red", width=2),
        'left_leg': canvas.create_line(character_data['x'], character_data['y'] + 50, character_data['x'] - 15,
                                       character_data['y'] + 70, fill="red", width=2),
        'right_leg': canvas.create_line(character_data['x'], character_data['y'] + 50, character_data['x'] + 15,
                                        character_data['y'] + 70, fill="red", width=2)
    }

    health_text = canvas.create_text(character_data['x'], character_data['y'] - 20,
                                     text=f"{character_data['name']} Health: {character_data['health']}", fill="green")

    # Draw peer character
    peer_character = {
        'head': canvas.create_oval(peer_character_data['x'] - 10, peer_character_data['y'] - 10, peer_character_data['x'] + 10,
                                   peer_character_data['y'] + 10, fill="blue"),
        'body': canvas.create_line(peer_character_data['x'], peer_character_data['y'] + 10, peer_character_data['x'],
                                   peer_character_data['y'] + 50, fill="blue", width=2),
        'left_arm': canvas.create_line(peer_character_data['x'], peer_character_data['y'] + 20, peer_character_data['x'] - 15,
                                       peer_character_data['y'] + 30, fill="blue", width=2),
        'right_arm': canvas.create_line(peer_character_data['x'], peer_character_data['y'] + 20, peer_character_data['x'] + 15,
                                        peer_character_data['y'] + 30, fill="blue", width=2),
        'left_leg': canvas.create_line(peer_character_data['x'], peer_character_data['y'] + 50, peer_character_data['x'] - 15,
                                       peer_character_data['y'] + 70, fill="blue", width=2),
        'right_leg': canvas.create_line(peer_character_data['x'], peer_character_data['y'] + 50, peer_character_data['x'] + 15,
                                        peer_character_data['y'] + 70, fill="blue", width=2)
    }

    peer_health_text = canvas.create_text(peer_character_data['x'], 80,
                                          text=f"{peer_character_data['name']} Health: {peer_character_data['health']}",
                                          fill="green")
    '''

    # ---- Draw local hero as sprite ----
    try:
        hero_img = load_sprite_image(character_data['name'])
    except Exception as e:
        from tkinter import messagebox
        messagebox.showwarning("Sprite Missing",
                               f"Cannot load sprite for {character_data['name']}:\n{e}\nFallback to red circle.")
        hero_img = None
    if hero_img:
        SPRITE_REFS.append(hero_img)  # keep reference
        character = {
            'sprite': canvas.create_image(
                character_data['x'], character_data['y'],
                image=hero_img, anchor=SPRITE_ANCHOR
            )
        }
        sprite_hh = SPRITE_SIZE[1] // 2  # half height for health text offset
    else:
        # Fallback：一个小圆当头像
        character = {
            'sprite': canvas.create_oval(
                character_data['x'] - 10, character_data['y'] - 10,
                character_data['x'] + 10, character_data['y'] + 10,
                fill="red"
            )
        }
        sprite_hh = 10

    health_text = canvas.create_text(
        character_data['x'], character_data['y'] - (sprite_hh + 10),
        text=f"{character_data['name']} Health: {character_data['health']}",
        fill="green"
    )

    # ---- Draw peer hero as sprite ----
    try:
        peer_img = load_sprite_image(peer_character_data['name'])
    except Exception as e:
        from tkinter import messagebox
        messagebox.showwarning("Sprite Missing",
                               f"Cannot load sprite for {peer_character_data['name']}:\n{e}\nFallback to blue circle.")
        peer_img = None
    if peer_img:
        SPRITE_REFS.append(peer_img)
        peer_character = {
            'sprite': canvas.create_image(
                peer_character_data['x'], peer_character_data['y'],
                image=peer_img, anchor=SPRITE_ANCHOR
            )
        }
        peer_sprite_hh = SPRITE_SIZE[1] // 2
    else:
        peer_character = {
            'sprite': canvas.create_oval(
                peer_character_data['x'] - 10, peer_character_data['y'] - 10,
                peer_character_data['x'] + 10, peer_character_data['y'] + 10,
                fill="blue"
            )
        }
        peer_sprite_hh = 10

    peer_health_text = canvas.create_text(
        peer_character_data['x'], peer_character_data['y'] - (peer_sprite_hh + 10),
        text=f"{peer_character_data['name']} Health: {peer_character_data['health']}",
        fill="green"
    )

    # Key bindings
    root.bind("<Left>",
              lambda event: move_character(character, -10, 0, canvas, client_socket, character_data, health_text))
    root.bind("<Right>",
              lambda event: move_character(character, 10, 0, canvas, client_socket, character_data, health_text))
    root.bind("<Up>",
              lambda event: move_character(character, 0, -10, canvas, client_socket, character_data, health_text))
    root.bind("<Down>",
              lambda event: move_character(character, 0, 10, canvas, client_socket, character_data, health_text))
    root.bind("1", lambda event: send_skill(client_socket, 0))
    root.bind("2", lambda event: send_skill(client_socket, 1))
    root.bind("3", lambda event: send_skill(client_socket, 2))

    threading.Thread(target=receive_data,
                     args=(client_socket, canvas, peer_character, peer_health_text, health_text),
                     daemon=True).start()

    root.mainloop()


if __name__ == "__main__":
    start_client()
