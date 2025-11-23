import json
import random
import socket
import threading
import select
import time
# 放到文件顶部附近（clientC.py / server_run.py 都建议加）
import os, sys
from pathlib import Path

def resource_path(rel_path: str) -> str:
    """
    兼容 PyInstaller 的资源定位：
    1) 打包后优先从 _MEIPASS 临时目录找
    2) 否则从脚本所在目录找
    3) 最后从当前工作目录找（兜底）
    """
    # 1) _MEIPASS（onefile 解包目录）
    base = getattr(sys, "_MEIPASS", None)
    if base:
        p = Path(base) / rel_path
        if p.exists():
            return str(p)

    # 2) 脚本/可执行文件所在目录
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).parent
    else:
        base = Path(__file__).resolve().parent
    p = base / rel_path
    if p.exists():
        return str(p)

    # 3) 当前工作目录兜底
    return rel_path

# =========================
# Server configuration
# =========================
SERVER_HOST = "127.0.0.1"
SERVER_PORT = 1212  # Default port for the server, can be changed if needed




class Hero:
    def __init__(self, name, base_health, physical_attack, skills):
        self.name = name
        self.base_health = base_health
        self.physical_attack = physical_attack
        self.skills = skills

    @staticmethod
    def load_from_file(file_path='property.json'):
        """
        Load hero data from a JSON file and create Hero objects.

        Args:
            file_path (str): Path to the JSON file.

        Returns:
            dict: A dictionary containing all hero objects.
        """
        # with open(file_path, 'r', encoding='utf-8') as f:
        #with open(resource_path(file_path), 'r', encoding='utf-8') as f:

        # 原来：with open('property.json', 'r', encoding='utf-8') as f:
        # 改成：
        prop_file = resource_path('property.json')

        # 调试/自检：如果文件不存在或大小为0，提前给出更友好的错误
        if not Path(prop_file).exists() or Path(prop_file).stat().st_size == 0:
            raise FileNotFoundError(f"property.json 未找到或为空：{prop_file}")

        with open(prop_file, 'r', encoding='utf-8') as f:
            #data = json.load(f)
            heroes_data = json.load(f)
        heroes = {}
        for hero in heroes_data['heroes']:
            heroes[hero['name']] = Hero(hero['name'], hero['base_health'], hero['physical_attack'], hero['skills'])
        return heroes


def calculate_damage(skill, hero):
    """
    Calculate the damage dealt by a skill.

    Args:
        skill (dict): Skill data.
        hero (Hero): The hero using the skill.

    Returns:
        int: Randomized damage value.
    """
    base_damage = skill['base_damage']
    multiplier = skill['physical_damage_multiplier']
    physical_attack = hero.physical_attack
    damage = base_damage + physical_attack * multiplier
    return random.randint(damage - 20, damage + 20)


def resp(type, name, health, p_name, p_health, x, y, p_x, p_y, skill, p_skill, healthy):
    """
    Build the server response data.

    Args:
        type (str): Response type.
        name (str): Local hero name.
        health (int): Local hero health.
        p_name (str): Opponent hero name.
        p_health (int): Opponent hero health.
        x (str): Local hero X-coordinate.
        y (str): Local hero Y-coordinate.
        p_x (str): Opponent hero X-coordinate.
        p_y (str): Opponent hero Y-coordinate.
        skill (str): Local hero skill index.
        p_skill (str): Opponent hero skill index.
        healthy (bool): Alive/dead status flag.

    Returns:
        dict: Response data.
    """
    response = {
        "s_resp_type": type,
        "s_hero1_name": name,
        "s_hero1_health": health,
        "s_hero2_name": p_name,
        "s_hero2_health": p_health,
        "s_hero1_x": x,
        "s_hero1_y": y,
        "s_hero2_x": p_x,
        "s_hero2_y": p_y,
        "s_hero1_skill": skill,
        "s_hero2_skill": p_skill,
        "died": healthy
    }
    return response


def handle_client(client_socket, peer_socket, client_data, peer_client_data, heroes):
    """
    Handle client requests and communicate with the peer client.

    Args:
        client_socket (socket.socket): Current client socket.
        peer_socket (socket.socket): Peer client socket.
        client_data (dict): Current client data.
        peer_client_data (dict): Peer client data.
        heroes (dict): All hero data.

    Returns:
        None
    """
    global peer_hero_name, peer_flag, login_received
    buffer = ""
    peer_buffer = ""
    client_login_data = None
    peer_login_data = None

    while True:
        ready_sockets, _, _ = select.select([client_socket, peer_socket], [], [])

        for sock in ready_sockets:
            if sock == client_socket:
                request = client_socket.recv(4096)
                if request:
                    buffer += request.decode('utf-8')

                    try:
                        data, index = json.JSONDecoder().raw_decode(buffer)
                        buffer = buffer[index:].strip()
                        print(f"Received data: {json.dumps(data, indent=4, ensure_ascii=False)}")

                        if data['opr_type'] == "0":  # Login
                            client_login_data = data
                            if peer_login_data:
                                process_data(client_login_data, peer_login_data, client_socket, peer_socket,
                                             client_data, peer_client_data, heroes)
                                login_received = True
                        elif login_received:
                            process_data(data, None, client_socket, peer_socket, client_data, peer_client_data, heroes)
                    except json.JSONDecodeError:
                        continue
                else:
                    break
            elif sock == peer_socket:
                peer_request = peer_socket.recv(4096)
                if peer_request:
                    peer_buffer += peer_request.decode('utf-8')

                    try:
                        peer_data, peer_index = json.JSONDecoder().raw_decode(peer_buffer)
                        peer_buffer = peer_buffer[peer_index:].strip()
                        print(f"Received peer data: {json.dumps(peer_data, indent=4, ensure_ascii=False)}")

                        if peer_data['opr_type'] == "0":  # Peer login
                            peer_login_data = peer_data
                            if client_login_data:
                                process_data(client_login_data, peer_login_data, client_socket, peer_socket,
                                             client_data, peer_client_data, heroes)
                                login_received = True
                        elif login_received:
                            process_data(None, peer_data, client_socket, peer_socket, client_data, peer_client_data,
                                         heroes)
                    except json.JSONDecodeError:
                        continue
                else:
                    break

def process_data(data, peer_data, client_socket, peer_socket, client_data, peer_client_data, heroes):
    """
    Process received data and perform corresponding actions.

    Args:
        data (dict): Current client data.
        peer_data (dict): Peer client data.
        client_socket (socket.socket): Current client socket.
        peer_socket (socket.socket): Peer client socket.
        client_data (dict): Current client data.
        peer_client_data (dict): Peer client data.
        heroes (dict): All hero data.

    Returns:
        None
    """
    global peer_hero_name, peer_flag
    global hero_health, peer_health
    global healthy_flag

    healthy_flag = False
    peer_opr_type = -1
    opr_type = -1
    response = {}
    peer_response = {}

    if data is not None and 'opr_type' in data:
        opr_type = data['opr_type']
        hero_name = data['hero_name']
    if peer_data is not None and 'opr_type' in peer_data:
        peer_opr_type = peer_data['opr_type']
        peer_hero_name = peer_data['hero_name']

    if opr_type == "0":  # Login
        start_time = time.time()
        while not peer_hero_name and time.time() - start_time < 5:
            time.sleep(0.1)  # Short sleep to avoid busy waiting

        peer_health = heroes[peer_hero_name].base_health
        hero_health = heroes[hero_name].base_health
        response = resp("0", hero_name, heroes[hero_name].base_health, peer_hero_name,
                        heroes[peer_hero_name].base_health, "", "", "", "", "", "", "")
        peer_response = resp("0", peer_hero_name, heroes[peer_hero_name].base_health, hero_name,
                             heroes[hero_name].base_health, "", "", "", "", "", "", "")
        print(f"Send to first client: {json.dumps(response, indent=4, ensure_ascii=False)}")
        client_socket.send(json.dumps(response, ensure_ascii=False).encode('utf-8'))
        print(f"Send to second client: {json.dumps(peer_response, indent=4, ensure_ascii=False)}")
        peer_socket.send(json.dumps(peer_response, ensure_ascii=False).encode('utf-8'))

    if opr_type == "1":  # Movement update
        response = resp("1", hero_name, "", "peer_hero_name",
                        "", data['hero_x'], data['hero_y'], "", "", "", "", "")
        peer_response = resp("1", "peer_hero_name", "", hero_name,
                             "", "", "", data['hero_x'], data['hero_y'], "", "", "")
        print(f"Send movement info: {json.dumps(response, indent=4, ensure_ascii=False)}")
        client_socket.send(json.dumps(response, ensure_ascii=False).encode('utf-8'))
        print(f"Send movement info to peer: {json.dumps(peer_response, indent=4, ensure_ascii=False)}")
        peer_socket.send(json.dumps(peer_response, ensure_ascii=False).encode('utf-8'))

    if peer_opr_type == "1":  # Peer movement update
        peer_response = resp("1", "hero_name", "", peer_hero_name,
                             "", peer_data['hero_x'], peer_data['hero_y'], "", "", "", "", "")
        response = resp("1", "peer_hero_name", "", "hero_name",
                        "", "", "", peer_data['hero_x'], peer_data['hero_y'], "", "", "")
        print(f"Send movement info: {json.dumps(response, indent=4, ensure_ascii=False)}")
        client_socket.send(json.dumps(response, ensure_ascii=False).encode('utf-8'))
        print(f"Send movement info to peer: {json.dumps(peer_response, indent=4, ensure_ascii=False)}")
        peer_socket.send(json.dumps(peer_response, ensure_ascii=False).encode('utf-8'))

    if peer_opr_type == "2":  # Peer attack
        skill_index = int(peer_data['hero_skill']) if peer_data['hero_skill'] else 0
        hero = heroes[peer_hero_name]
        skill = hero.skills[skill_index]
        damage = calculate_damage(skill, hero)
        hero_health -= damage
        if hero_health <= 0:
            healthy_flag = True
            response = resp("2", "111", "0", peer_hero_name,
                            peer_health, "", "", "", "", str(skill_index),
                            "99", healthy_flag)
            peer_response = resp("2", peer_hero_name, peer_health, "111",
                                 "0", "", "", "", "", str(skill_index),
                                 "99", "")
        else:
            response = resp("2", "111", hero_health, peer_hero_name,
                            peer_health, "", "", "", "", str(skill_index),
                            "99", healthy_flag)
            peer_response = resp("2", peer_hero_name, peer_health, "111",
                                 hero_health, "", "", "", "", str(skill_index),
                                 "99", "")
        client_socket.send(json.dumps(response, ensure_ascii=False).encode('utf-8'))
        peer_socket.send(json.dumps(peer_response, ensure_ascii=False).encode('utf-8'))

    if opr_type == "2":  # Attack
        skill_index = int(data['hero_skill']) if data['hero_skill'] else 0
        hero = heroes[hero_name]
        skill = hero.skills[skill_index]
        damage = calculate_damage(skill, hero)
        peer_health -= damage
        if peer_health <= 0:
            healthy_flag = True
            response = resp("2", hero_name, hero_health, peer_hero_name,
                            "0", "", "", "", "", str(skill_index),
                            "99", "")
            peer_response = resp("2", peer_hero_name, "0", hero_name,
                                 hero_health, "", "", "", "", str(skill_index),
                                 "99", healthy_flag)
        else:
            response = resp("2", hero_name, hero_health, peer_hero_name,
                            peer_health, "", "", "", "", str(skill_index),
                            "99", healthy_flag)
            peer_response = resp("2", peer_hero_name, peer_health, hero_name,
                                 hero_health, "", "", "", "", str(skill_index),
                                 "99", healthy_flag)
        client_socket.send(json.dumps(response, ensure_ascii=False).encode('utf-8'))
        peer_socket.send(json.dumps(peer_response, ensure_ascii=False).encode('utf-8'))


def start_server():
    """
    Start the server, wait for client connections, and handle requests.

    Returns:
        None
    """
    heroes = Hero.load_from_file()
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # server.bind(('0.0.0.0', 1212))
    server.bind((SERVER_HOST, SERVER_PORT))
    server.listen(2)

    print(f"Server started on {SERVER_HOST}:{SERVER_PORT}, waiting for connections...")

    client1_socket, addr1 = server.accept()
    print(f"Client 1 connected from: {addr1}")

    client2_socket, addr2 = server.accept()
    print(f"Client 2 connected from: {addr2}")

    client_data = {}
    peer_client_data = {}

    threading.Thread(target=handle_client,
                     args=(client1_socket, client2_socket, client_data, peer_client_data, heroes)).start()


if __name__ == "__main__":
    start_server()
